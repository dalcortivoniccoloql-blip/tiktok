# Durata: LEGATO-A:P09
"""
Voce (TTS) + tempi parola-per-parola.

v2 (2026-07-04):
- ELIMINATO il "Number X." prima di ogni fatto: la narrazione scorre fluida.
- L'audio viene generato in streaming catturando i WordBoundary di edge-tts:
  accanto all'mp3 viene scritto un sidecar `<n>.timings.json` con i tempi esatti
  di ogni parola -> il video sincronizza i sottotitoli al parlato (niente stima).
- VOICE_RATE configurabile (default +8%: ritmo da Short).
"""

import asyncio
import json
from pathlib import Path

import edge_tts

from config import DEFAULT_VOICE, INTRO_TEXT, OUTRO_TEXT, VOICE_RATE, is_single


# ── narrazione ────────────────────────────────────────────────────────────────

def hook_text(script: dict) -> str:
    """L'hook parlato: quello dello script se c'e', altrimenti l'intro generica v2."""
    return (script.get("hook") or "").strip() or INTRO_TEXT


def cta_text(script: dict) -> str:
    """L'outro parlato. Nel formato single il default e' VUOTO: la coda rompe il loop
    (uno Short che riparte da capo pulito guadagna replay). Nel formato a 5 fatti
    resta l'outro storico."""
    cta = (script.get("cta") or "").strip()
    if cta:
        return cta
    return "" if is_single(script) else OUTRO_TEXT


def narration_parts(script: dict) -> list[tuple[str, str]]:
    """Le parti della narrazione, in ordine: hook, i fatti/beat, (outro solo se c'e').

    ⚠️ Una parte VUOTA non va mai emessa: `_align_boundaries` non le assegnerebbe
    nessuna parola e `_load_timeline` scarterebbe l'intero sidecar, facendo cadere
    il video sui sottotitoli "a stima" (desincronizzati) senza dire niente.
    Questa funzione e' la fonte unica della struttura: il video conta le parti da qui."""
    parts = [("intro", hook_text(script))]
    for fact in script["facts"]:
        parts.append(("fact", fact))
    outro = cta_text(script)
    if outro:
        parts.append(("outro", outro))
    return parts


def script_to_narration(script: dict, voice: str = DEFAULT_VOICE) -> str:
    """Testo di narrazione completo (le parti unite; ogni fatto termina gia' con '.')."""
    return " ".join(text for _, text in narration_parts(script))


def _timings_path(audio_path: Path) -> Path:
    return audio_path.parent / (audio_path.stem + ".timings.json")


# ── TTS con cattura dei tempi ─────────────────────────────────────────────────

async def _tts_stream(text: str, output_path: Path, voice: str, rate: str) -> list[dict]:
    """Genera l'audio e ritorna i WordBoundary (t/d in secondi, w = parola)."""
    try:
        # edge-tts >= 7 emette SentenceBoundary di default: i tempi parola vanno chiesti
        communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        # edge-tts < 7: niente kwarg `boundary`, WordBoundary era gia' il default
        communicate = edge_tts.Communicate(text, voice, rate=rate)
    boundaries: list[dict] = []
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                boundaries.append({
                    "t": chunk["offset"] / 1e7,    # ticks da 100ns -> secondi
                    "d": chunk["duration"] / 1e7,
                    "w": chunk["text"],
                })
    return boundaries


def _align_boundaries(parts: list[tuple[str, str]], narration: str,
                      boundaries: list[dict]) -> list[dict]:
    """Assegna ogni parola TTS alla parte (intro/fatto/outro) a cui appartiene,
    cercandola in ordine dentro il testo della narrazione."""
    # range di caratteri di ogni parte dentro la narrazione
    ranges: list[tuple[int, int]] = []
    pos = 0
    for _, text in parts:
        start = narration.find(text, pos)
        if start == -1:
            start = pos
        ranges.append((start, start + len(text)))
        pos = start + len(text)

    out = [{"kind": kind, "text": text, "words": []} for kind, text in parts]
    cursor = 0
    part_idx = 0
    for b in boundaries:
        found = narration.find(b["w"], cursor)
        if found == -1:
            found = cursor  # tokenizzazione TTS diversa dal testo: resta dove siamo
        else:
            cursor = found + len(b["w"])
        while part_idx < len(ranges) - 1 and found >= ranges[part_idx][1]:
            part_idx += 1
        out[part_idx]["words"].append(b)
    return out


# ── API pubblica ──────────────────────────────────────────────────────────────

def generate_audio(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    """Genera un file MP3 da un testo qualsiasi (senza sidecar dei tempi)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_tts_stream(text, output_path, voice, VOICE_RATE))
    return output_path


def generate_audio_for_script(
    script: dict,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    overwrite: bool = False,
) -> Path:
    """Genera l'audio di uno script + sidecar `.timings.json` per i sottotitoli sincronizzati.

    Skip solo se esistono SIA l'mp3 SIA il sidecar: un mp3 vecchio senza tempi
    (pipeline v1, col "Number X") viene rigenerato per non desincronizzare i sottotitoli.
    """
    output_path = Path(output_path)
    timings_p = _timings_path(output_path)

    if output_path.exists() and not overwrite:
        if timings_p.exists():
            print(f"    Audio gia' esistente, skip: {output_path.name}")
            return output_path
        print(f"    Audio v1 senza tempi: rigenero {output_path.name}")

    parts = narration_parts(script)
    narration = " ".join(text for _, text in parts)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"    Generazione audio ({voice}, rate {VOICE_RATE})...")
    boundaries = asyncio.run(_tts_stream(narration, output_path, voice, VOICE_RATE))

    aligned = _align_boundaries(parts, narration, boundaries)
    if boundaries and all(p["words"] for p in aligned):
        timings = {"version": 2, "voice": voice, "rate": VOICE_RATE, "parts": aligned}
        timings_p.write_text(json.dumps(timings, ensure_ascii=False), encoding="utf-8")
    else:
        # niente WordBoundary (o allineamento fallito): il video usera' il fallback a stima
        if timings_p.exists():
            timings_p.unlink()
        print("    Nota: tempi parola non disponibili -> sottotitoli in modalita' stima")

    size_kb = output_path.stat().st_size // 1024
    print(f"    Salvato: {output_path.name} ({size_kb} KB)")
    return output_path


def list_voices() -> None:
    """Elenca le voci TTS disponibili (richiede connessione internet)."""
    async def _list():
        voices = await edge_tts.list_voices()
        for v in sorted(voices, key=lambda x: x["ShortName"]):
            if v["Locale"].startswith("it") or v["Locale"].startswith("en-US"):
                print(f"  {v['ShortName']:40} {v['Gender']}")
    asyncio.run(_list())


if __name__ == "__main__":
    print("Voci disponibili (IT + EN-US):")
    list_voices()
