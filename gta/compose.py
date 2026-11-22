"""Monta uno Short GTA 6: 3-4 spezzoni brevi di clip Twitch + voce TTS + sottotitoli.

Ogni video e' descritto da un file in gta/videos/<id>.json (piccolo, versionato):

    {
      "id": "gta001",
      "hook": "This GTA 6 cop has a secret.",
      "facts": ["beat 1 ...", "beat 2 ...", "beat 3 ..."],
      "fonte": "https://... (dove e' verificato il fatto: OBBLIGATORIA)",
      "title": "titolo YouTube (opzionale)",
      "clips": [
        {"file": "alpha_AbcDef.mp4", "start": 12.0},
        {"file": "beta_XyZ.mp4"}
      ]
    }

- "clips": 2-4 file presi da output/gta/inbox/ (scaricati da gta.fetch). "start" e'
  il secondo da cui parte lo spezzone; se manca si usa il centro della clip.
- La voce riusa la pipeline esistente (edge-tts + tempi parola-per-parola) e i
  sottotitoli sincronizzati di generate_video.
- Layout "blur": la clip orizzontale intera al centro (con leggero zoom lento) su
  uno sfondo sfocato della stessa clip. Niente crop a 9:16, che taglierebbe 2/3
  dell'azione. Hook sopra, sottotitoli sotto, credito dello streamer sotto la clip.
- L'audio delle clip e' muto: la voce dello streamer non finisce nello Short.

Uso:
    py -3 -m gta.compose gta001            # rende output/gta/render/gta001.mp4
    py -3 -m gta.compose --tutti           # tutti i video non ancora resi
    py -3 -m gta.compose gta001 --forza    # rifa' anche se esiste
"""
from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "pipeline"))

from config import (  # noqa: E402
    WIDTH, HEIGHT, FPS, CAPTION_CHUNK_FONT_SIZE, HOOK_FONT_SIZE,
)
from gta.fetch import gta_dir  # noqa: E402

VIDEOS_DIR = HERE / "videos"

# Handle del canale GTA, scritto in basso nel video e in descrizione.
# Vuoto finche' il canale non esiste: in quel caso non si disegna nulla.
GTA_USERNAME = ""

SEG_MIN, SEG_MAX = 3.0, 5.0     # durata di ogni spezzone (decisione Q6)
ZOOM_MAX = 1.08                 # zoom lento dentro ogni spezzone (cambio visivo + trasformazione)
BG_BLUR_DARKEN = 0.45
CLIP_W = WIDTH                  # la clip 16:9 occupa tutta la larghezza
CLIP_H = round(WIDTH * 9 / 16)  # 608
CLIP_Y = (HEIGHT - CLIP_H) // 2
HOOK_Y = CLIP_Y // 2            # hook centrato nella fascia sopra la clip
CAPTION_Y = CLIP_Y + CLIP_H + (HEIGHT - CLIP_Y - CLIP_H) // 2 - 60
CREDIT_Y = CLIP_Y + CLIP_H + 18


# ── job ──────────────────────────────────────────────────────────────────────

class JobError(ValueError):
    pass


def load_job(path: Path, inbox: Path) -> dict:
    job = json.loads(path.read_text(encoding="utf-8"))
    job.setdefault("id", path.stem)
    errori = []
    if not (job.get("hook") or "").strip():
        errori.append("manca 'hook'")
    facts = job.get("facts") or []
    if not 1 <= len(facts) <= 4 or not all(str(f).strip() for f in facts):
        errori.append("'facts' deve avere 1-4 beat non vuoti")
    if not (job.get("fonte") or "").strip():
        errori.append("manca 'fonte' (regola del canale: nessun fatto senza fonte verificata)")
    clips = job.get("clips") or []
    if not 2 <= len(clips) <= 4:
        errori.append("'clips' deve avere 2-4 spezzoni")
    for c in clips:
        f = inbox / c.get("file", "")
        if not c.get("file") or not f.exists():
            errori.append(f"clip non trovata: {f}")
        elif not f.with_suffix(".json").exists():
            errori.append(f"metadati (credito) mancanti per {f.name}: rifai gta.fetch")
    if errori:
        raise JobError(f"{path.name}: " + "; ".join(errori))
    return job


def narration_script(job: dict) -> dict:
    """Lo script nel formato 'single' della pipeline: cosi' audio, tempi e
    sottotitoli (hook intero + chunk) funzionano senza modifiche."""
    return {"format": "single", "number": 0, "hook": job["hook"].strip(),
            "facts": [f.strip() for f in job["facts"]], "cta": job.get("cta", "")}


def crediti(job: dict, inbox: Path) -> list[dict]:
    out = []
    for c in job["clips"]:
        meta = json.loads((inbox / c["file"]).with_suffix(".json").read_text(encoding="utf-8"))
        out.append(meta)
    return out


# ── piano degli spezzoni ─────────────────────────────────────────────────────

@dataclass
class Segmento:
    inizio: float        # tempo nello Short
    fine: float
    clip: int            # indice in job["clips"]
    src_start: float     # secondo della clip sorgente a cui corrisponde `inizio`


def piano_segmenti(durata: float, starts: list[float], durate_clip: list[float]) -> list[Segmento]:
    """Divide lo Short in spezzoni da 3-5s ruotando sulle clip.

    Se la voce dura piu' di n_clip * 5s si ripassa sulle clip, proseguendo DOPO
    il pezzo gia' mostrato (mai lo stesso spezzone due volte), con wrap sulla
    durata della clip sorgente."""
    n = len(starts)
    n_seg = max(n, int(np.ceil(durata / SEG_MAX)))
    seg = durata / n_seg
    if seg < SEG_MIN and n_seg > n:
        n_seg = max(n, int(durata // SEG_MIN))
        seg = durata / n_seg
    piano = []
    for k in range(n_seg):
        i = k % n
        giro = k // n
        src = (starts[i] + giro * seg) % max(durate_clip[i], 0.01)
        piano.append(Segmento(k * seg, (k + 1) * seg if k < n_seg - 1 else durata, i, src))
    return piano


def start_default(durata_clip: float, serve: float) -> float:
    """Centro della clip: nelle clip Twitch il momento saliente sta quasi sempre li'."""
    return max(0.0, (durata_clip - serve) / 2)


# ── frame ────────────────────────────────────────────────────────────────────

def _fit_width(img: Image.Image, w: int, h: int) -> Image.Image:
    """Ridimensiona/croppa a w x h (riempiendo). Per clip 16:9 non taglia quasi nulla."""
    sw, sh = img.size
    if sw / sh > w / h:
        nw = int(sh * w / h)
        img = img.crop(((sw - nw) // 2, 0, (sw + nw) // 2, sh))
    else:
        nh = int(sw * h / w)
        img = img.crop((0, (sh - nh) // 2, sw, (sh + nh) // 2))
    return img.resize((w, h), Image.LANCZOS)


def _zoom(img: Image.Image, z: float) -> Image.Image:
    if z <= 1.0001:
        return img
    w, h = img.size
    cw, ch = w / z, h / z
    x0, y0 = (w - cw) / 2, (h - ch) / 2
    return img.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def _sfondo_blur(frame: Image.Image) -> Image.Image:
    # blur su una copia piccola: a piena risoluzione costerebbe ~10x per frame
    small = _fit_width(frame, WIDTH // 8, HEIGHT // 8).filter(ImageFilter.GaussianBlur(4))
    big = small.resize((WIDTH, HEIGHT), Image.BILINEAR)
    return ImageEnhance.Brightness(big).enhance(BG_BLUR_DARKEN)


def _testo(draw: ImageDraw.ImageDraw, text: str, size: int, cy: int, font_fn, wrap_fn,
           stroke: int = 8) -> None:
    font = font_fn(size)
    lines = wrap_fn(text, font, WIDTH - 130, draw)
    asc, desc = font.getmetrics()
    lh = asc + desc + 10
    y = cy - lh * len(lines) // 2
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        x = (WIDTH - (bb[2] - bb[0])) // 2 - bb[0]
        draw.text((x, y), line, font=font, fill=(255, 255, 255),
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += lh


def render(job: dict, inbox: Path, out_dir: Path, overwrite: bool = False) -> Path:
    from moviepy import AudioFileClip, VideoClip, VideoFileClip
    from generate_audio import generate_audio_for_script
    from generate_video import _load_timeline, _font, _wrap

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{job['id']}.mp4"
    if out.exists() and not overwrite:
        print(f"  gia' reso, skip: {out.name}")
        return out

    script = narration_script(job)
    audio_p = out_dir / f"{job['id']}.mp3"
    generate_audio_for_script(script, audio_p, overwrite=overwrite)
    audio = AudioFileClip(str(audio_p))
    durata = audio.duration

    loaded = _load_timeline(audio_p, script)
    if not loaded:
        raise RuntimeError("tempi parola non disponibili: sottotitoli impossibili, rigenera l'audio")
    timeline, beats = loaded
    t_starts = [s for s, _ in timeline]
    hook_end = beats[0] if beats else 0.0

    sorgenti = [VideoFileClip(str(inbox / c["file"]), audio=False) for c in job["clips"]]
    durate = [s.duration for s in sorgenti]
    serve = durata / len(sorgenti)   # tempo totale in cui ogni clip resta a schermo
    starts = [float(c["start"]) if c.get("start") is not None else start_default(d, serve)
              for c, d in zip(job["clips"], durate)]
    piano = piano_segmenti(durata, starts, durate)
    inizi_seg = [s.inizio for s in piano]
    meta = crediti(job, inbox)

    def frame(t: float) -> np.ndarray:
        s = piano[max(bisect_right(inizi_seg, t) - 1, 0)]
        rel = t - s.inizio
        src_t = (s.src_start + rel) % max(durate[s.clip] - 0.05, 0.01)
        raw = Image.fromarray(sorgenti[s.clip].get_frame(src_t)).convert("RGB")

        img = _sfondo_blur(raw)
        z = 1.0 + (ZOOM_MAX - 1.0) * rel / max(s.fine - s.inizio, 0.01)
        img.paste(_zoom(_fit_width(raw, CLIP_W, CLIP_H), z), (0, CLIP_Y))
        draw = ImageDraw.Draw(img)

        idx = max(bisect_right(t_starts, t) - 1, 0)
        cap = timeline[idx][1]
        if t < hook_end:
            _testo(draw, cap, HOOK_FONT_SIZE, HOOK_Y, _font, _wrap)
        else:
            _testo(draw, cap, CAPTION_CHUNK_FONT_SIZE, CAPTION_Y, _font, _wrap)

        _testo(draw, f"twitch.tv/{meta[s.clip]['streamer']}", 34, CREDIT_Y + 20, _font, _wrap, stroke=4)
        if GTA_USERNAME:
            _testo(draw, GTA_USERNAME, 40, HEIGHT - 140, _font, _wrap, stroke=5)
        return np.array(img)

    print(f"  render {job['id']}: {durata:.1f}s, {len(piano)} spezzoni da {piano[0].fine:.1f}s, "
          f"{len(sorgenti)} clip")
    video = VideoClip(frame, duration=durata).with_fps(FPS).with_audio(audio)
    video.write_videofile(str(out), fps=FPS, codec="libx264", audio_codec="aac",
                          preset="fast", ffmpeg_params=["-crf", "23"], logger=None)
    video.close()
    audio.close()
    for s in sorgenti:
        s.close()

    (out_dir / f"{job['id']}.yt.json").write_text(json.dumps({
        "title": job.get("title") or job["hook"],
        "description": descrizione(job, meta),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  salvato {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def descrizione(job: dict, meta: list[dict]) -> str:
    righe = [job["hook"], ""]
    visti = []
    for m in meta:
        if m["streamer"] not in visti:
            visti.append(m["streamer"])
    righe.append("Clips used with permission from:")
    righe += [f"- twitch.tv/{s}" for s in visti]
    righe += ["", f"Source: {job['fonte']}", "", "#GTA6 #GTAVI #gaming #shorts"]
    if GTA_USERNAME:
        righe.insert(1, f"Follow {GTA_USERNAME} for more GTA 6 secrets!")
    return "\n".join(righe)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Monta Shorts GTA 6 da gta/videos/*.json")
    ap.add_argument("ids", nargs="*", help="id dei video (nome file senza .json)")
    ap.add_argument("--tutti", action="store_true")
    ap.add_argument("--forza", action="store_true", help="rifai anche se gia' reso")
    a = ap.parse_args(argv)

    base = gta_dir()
    inbox, out_dir = base / "inbox", base / "render"
    if a.tutti:
        paths = sorted(p for p in VIDEOS_DIR.glob("*.json") if not p.name.startswith("_"))
    else:
        paths = [VIDEOS_DIR / f"{i}.json" for i in a.ids]
    if a.tutti and not paths:
        print(f"Nessun video in {VIDEOS_DIR} (i file che iniziano con '_' sono esempi e vengono saltati).")
        return 0
    if not paths:
        ap.error("indica uno o piu' id, oppure --tutti")

    falliti = 0
    for p in paths:
        try:
            render(load_job(p, inbox), inbox, out_dir, overwrite=a.forza)
        except (JobError, FileNotFoundError) as e:
            print(f"[x] {e}")
            falliti += 1
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
