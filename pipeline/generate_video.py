# Durata: LEGATO-A:P09
from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from moviepy import AudioFileClip, VideoClip, VideoFileClip

from config import (
    WIDTH, HEIGHT, FPS,
    BACKGROUNDS_DIR,
    CAPTION_FILL, CAPTION_STROKE, STROKE_WIDTH, CAPTION_FONT_SIZE,
    CAPTION_MODE, CAPTION_CHUNK_WORDS, CAPTION_CHUNK_FONT_SIZE, CAPTION_UPPERCASE,
    BG_DARKEN, INTRO_TEXT, OUTRO_TEXT, USERNAME,
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

def load_bg_clip(script_number: int = 0) -> VideoFileClip | None:
    """Sceglie lo sfondo per QUESTO script.

    v2: rotazione deterministica su TUTTI i video presenti in backgrounds/
    (script 1 -> video A, script 2 -> video B, ...): basta mettere piu' file
    nella cartella e ogni Short ha uno sfondo diverso, senza config.
    Deterministica = rigenerare lo stesso script rida' lo stesso sfondo.
    Con un solo file si comporta come prima. Ritorna None se la cartella e' vuota.
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
    chosen = videos[script_number % len(videos)]
    print(f"    Background: {chosen.name} ({len(videos)} disponibili)")
    return VideoFileClip(str(chosen))


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


# ── sottotitoli sincronizzati (sidecar .timings.json scritto da generate_audio) ──

def _load_timeline(audio_path: Path, facts: list[str]) -> list[tuple[float, str]] | None:
    """Costruisce la timeline [(inizio_sec, testo), ...] dai tempi parola-per-parola.
    Ogni sottotitolo resta visibile fino all'inizio del successivo (mai schermo vuoto).
    Ritorna None se il sidecar manca o non e' valido -> il video usa il fallback a stima."""
    timings_p = audio_path.parent / (audio_path.stem + ".timings.json")
    if not timings_p.exists():
        return None
    try:
        parts = json.loads(timings_p.read_text(encoding="utf-8"))["parts"]
    except (ValueError, KeyError, OSError):
        return None
    if len(parts) != len(facts) + 2 or not all(p.get("words") for p in parts):
        return None  # sidecar incoerente con lo script corrente

    timeline: list[tuple[float, str]] = []
    for part in parts:
        words = part["words"]
        if CAPTION_MODE == "chunks":
            chunks = [words[i:i + CAPTION_CHUNK_WORDS]
                      for i in range(0, len(words), CAPTION_CHUNK_WORDS)]
            # niente chunk orfano da 1 parola: si accorpa al precedente
            if len(chunks) > 1 and len(chunks[-1]) == 1:
                chunks[-2].extend(chunks.pop())
            for chunk in chunks:
                text = " ".join(w["w"] for w in chunk)
                if CAPTION_UPPERCASE:
                    text = text.upper()
                timeline.append((chunk[0]["t"], text))
        else:  # "fact": la parte intera, ma sincronizzata sul suo vero inizio
            timeline.append((words[0]["t"], part["text"]))

    if not timeline:
        return None
    timeline[0] = (0.0, timeline[0][1])  # il primo sottotitolo parte subito
    return timeline


# ── frame renderer ────────────────────────────────────────────────────────────

def _make_frame(t: float, facts: list[str], audio_duration: float,
                bg_clip: VideoFileClip | None,
                timeline: list[tuple[float, str]] | None = None,
                starts: list[float] | None = None,
                font_size: int = CAPTION_FONT_SIZE,
                bg_offset: float = 0.0) -> np.ndarray:

    # ── timing ──
    if timeline is not None and starts is not None:
        # sincronizzato: il sottotitolo attivo e' l'ultimo iniziato prima di t
        idx = max(bisect_right(starts, t) - 1, 0)
        caption = timeline[idx][1]
    else:
        # fallback a stima (nessun sidecar tempi): distribuzione uniforme dei fatti
        intro_dur = 2.8
        outro_dur = 1.2
        facts_dur = max(audio_duration - intro_dur - outro_dur, len(facts) * 2.0)
        per_fact  = facts_dur / len(facts)

        if t < intro_dur:
            caption = INTRO_TEXT
        elif t >= audio_duration - outro_dur:
            caption = OUTRO_TEXT
        else:
            idx = min(int((t - intro_dur) / per_fact), len(facts) - 1)
            caption = facts[idx]

    # ── background a tutto schermo ──
    if bg_clip is not None:
        # bg_offset varia il punto di partenza per script: anche con lo stesso
        # video di sfondo, due Short non mostrano mai lo stesso spezzone
        loop_t = (t + bg_offset) % bg_clip.duration
        frame  = Image.fromarray(bg_clip.get_frame(loop_t))
        frame  = _crop_fill(frame, WIDTH, HEIGHT)
        if BG_DARKEN < 1.0:
            frame = ImageEnhance.Brightness(frame).enhance(BG_DARKEN)
        img = frame.convert("RGB")
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), (15, 10, 30))

    draw = ImageDraw.Draw(img)

    # ── caption centrata ──
    _draw_caption(draw, caption, _font(font_size), center_y=HEIGHT // 2)

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
    script_n = script.get("number", 0)
    bg_clip  = load_bg_clip(script_n)

    # punto di partenza dello sfondo diverso per ogni script (37s = passo fisso
    # che sparpaglia bene i punti di inizio dentro il loop del video di sfondo)
    bg_offset = 0.0
    if bg_clip is not None and bg_clip.duration:
        bg_offset = (script_n * 37.0) % bg_clip.duration

    timeline  = _load_timeline(audio_path, facts)
    starts    = [s for s, _ in timeline] if timeline else None
    font_size = CAPTION_CHUNK_FONT_SIZE if (timeline and CAPTION_MODE == "chunks") else CAPTION_FONT_SIZE
    sync_mode = "sincronizzati" if timeline else "a stima (nessun sidecar tempi)"

    print(f"    Rendering {'(full-screen + caption)' if bg_clip else '(no background!)'} - sottotitoli {sync_mode}...")

    video = VideoClip(
        lambda t: _make_frame(t, facts, duration, bg_clip, timeline, starts, font_size, bg_offset),
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
