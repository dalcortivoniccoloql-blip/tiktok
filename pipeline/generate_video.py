from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from moviepy import AudioFileClip, VideoClip, VideoFileClip

from config import (
    WIDTH, HEIGHT, FPS,
    BACKGROUNDS_DIR,
    CAPTION_FILL, CAPTION_STROKE, STROKE_WIDTH, CAPTION_FONT_SIZE,
    BG_DARKEN, OUTRO_TEXT, USERNAME,
)

# ── font ─────────────────────────────────────────────────────────────────────

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


_FONT_CANDIDATES = (
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    # Linux (GitHub Actions / Ubuntu)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONT_CACHE:
        for path in _FONT_CANDIDATES:
            try:
                _FONT_CACHE[size] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        else:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


# ── background video ──────────────────────────────────────────────────────────

def load_bg_clip(rng: random.Random | None = None) -> VideoFileClip | None:
    """Carica un video di sfondo da backgrounds/.

    Se sono presenti piu' file, ne sceglie uno (a caso se `rng` e' fornito),
    cosi' aggiungendo altri spezzoni la varieta' aumenta automaticamente.
    """
    if not BACKGROUNDS_DIR.exists():
        return None
    videos = sorted(
        list(BACKGROUNDS_DIR.glob("*.mp4")) +
        list(BACKGROUNDS_DIR.glob("*.mov")) +
        list(BACKGROUNDS_DIR.glob("*.webm"))
    )
    if not videos:
        return None
    choice = rng.choice(videos) if rng else videos[0]
    print(f"    Background: {choice.name}")
    return VideoFileClip(str(choice))


def _crop_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    """Crop centrato per riempire esattamente w x h mantenendo le proporzioni."""
    sw, sh = img.size
    if sw / sh > w / h:
        new_w = int(sh * w / h)
        img = img.crop(((sw - new_w) // 2, 0, (sw + new_w) // 2, sh))
    else:
        new_h = int(sw * h / w)
        img = img.crop((0, (sh - new_h) // 2, sw, (sh + new_h) // 2))
    return img.resize((w, h), Image.LANCZOS)


# ── caption text ──────────────────────────────────────────────────────────────

def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int, draw: ImageDraw.Draw) -> list[str]:
    words, lines, cur = text.split(), [], []
    for word in words:
        bb = draw.textbbox((0, 0), " ".join(cur + [word]), font=font)
        if bb[2] - bb[0] <= max_w:
            cur.append(word)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines or [""]


def _draw_caption(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont,
                  center_y: int) -> None:
    """Disegna testo bianco con bordo nero, centrato orizzontalmente attorno a center_y."""
    max_w = WIDTH - 130
    lines = _wrap(text, font, max_w, draw)

    # altezza riga
    asc, desc = font.getmetrics()
    line_h = asc + desc + 12
    total_h = line_h * len(lines)
    y = center_y - total_h // 2

    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        lw = bb[2] - bb[0]
        x = (WIDTH - lw) // 2 - bb[0]
        draw.text(
            (x, y), line, font=font,
            fill=CAPTION_FILL,
            stroke_width=STROKE_WIDTH,
            stroke_fill=CAPTION_STROKE,
        )
        y += line_h


# ── frame renderer ────────────────────────────────────────────────────────────

def _make_frame(t: float, facts: list[str], audio_duration: float,
                bg_clip: VideoFileClip | None, bg_start: float = 0.0) -> np.ndarray:

    # ── timing (HOOK A FREDDO: i fatti partono da t=0, CTA in coda) ──
    outro_dur = 2.2
    facts_dur = max(audio_duration - outro_dur, len(facts) * 2.0)
    per_fact  = facts_dur / len(facts)

    if t >= audio_duration - outro_dur:
        caption = OUTRO_TEXT
    else:
        idx = min(int(t / per_fact), len(facts) - 1)
        caption = facts[idx]

    # ── background a tutto schermo ──
    if bg_clip is not None:
        loop_t = (bg_start + t) % bg_clip.duration
        frame  = Image.fromarray(bg_clip.get_frame(loop_t))
        frame  = _crop_fill(frame, WIDTH, HEIGHT)
        if BG_DARKEN < 1.0:
            frame = ImageEnhance.Brightness(frame).enhance(BG_DARKEN)
        img = frame.convert("RGB")
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), (15, 10, 30))

    draw = ImageDraw.Draw(img)

    # ── caption centrata ──
    _draw_caption(draw, caption, _font(CAPTION_FONT_SIZE), center_y=HEIGHT // 2)

    # ── username in basso ──
    foot_font = _font(40)
    bb = draw.textbbox((0, 0), USERNAME, font=foot_font)
    fx = (WIDTH - (bb[2] - bb[0])) // 2 - bb[0]
    draw.text(
        (fx, HEIGHT - 140), USERNAME, font=foot_font,
        fill=CAPTION_FILL, stroke_width=5, stroke_fill=CAPTION_STROKE,
    )

    return np.array(img)


# ── public API ────────────────────────────────────────────────────────────────

def create_video(script: dict, audio_path: Path, output_path: Path,
                 overwrite: bool = False) -> Path:
    output_path = Path(output_path)
    audio_path  = Path(audio_path)

    if output_path.exists() and not overwrite:
        print(f"    Video gia' esistente, skip: {output_path.name}")
        return output_path

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio non trovato: {audio_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio    = AudioFileClip(str(audio_path))
    duration = audio.duration
    facts    = script["facts"]

    # RNG deterministico per script: spezzone di sfondo diverso per ogni Short,
    # ma riproducibile se lo stesso script viene ri-renderizzato.
    rng      = random.Random(script.get("number", 0))
    bg_clip  = load_bg_clip(rng)

    # Parte da un punto casuale del video di sfondo (il modulo gestisce il loop).
    bg_start = 0.0
    if bg_clip is not None and bg_clip.duration > duration:
        bg_start = rng.uniform(0, bg_clip.duration - duration)
        print(f"    Spezzone sfondo: da ~{bg_start:.0f}s")

    print(f"    Rendering {'(full-screen + caption)' if bg_clip else '(no background!)'}...")

    video = VideoClip(
        lambda t: _make_frame(t, facts, duration, bg_clip, bg_start),
        duration=duration,
    ).with_fps(FPS).with_audio(audio)

    video.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        ffmpeg_params=["-crf", "23"],
        logger=None,
    )

    audio.close()
    video.close()
    if bg_clip:
        bg_clip.close()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"    Salvato: {output_path.name} ({size_mb:.1f} MB)")
    return output_path
