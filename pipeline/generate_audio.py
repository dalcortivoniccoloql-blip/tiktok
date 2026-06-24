import asyncio
from pathlib import Path

import edge_tts

from config import DEFAULT_VOICE, INTRO_TEXT, OUTRO_TEXT, LANGUAGE

_NUMBER_WORD = "Number" if LANGUAGE == "en" else "Numero"


def script_to_narration(script: dict, voice: str = DEFAULT_VOICE) -> str:
    """Costruisce il testo di narrazione completo dallo script."""
    parts = [INTRO_TEXT]
    for i, fact in enumerate(script["facts"], 1):
        parts.append(f"{_NUMBER_WORD} {i}. {fact}")
    parts.append(OUTRO_TEXT)
    return "  ".join(parts)


async def _tts_async(text: str, output_path: Path, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def generate_audio(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    """Genera un file MP3 dal testo dato. Ritorna il path del file creato."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_tts_async(text, output_path, voice))
    return output_path


def generate_audio_for_script(
    script: dict,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    overwrite: bool = False,
) -> Path:
    """Genera l'audio per uno script. Salta se il file esiste già (a meno che overwrite=True)."""
    output_path = Path(output_path)

    if output_path.exists() and not overwrite:
        print(f"    Audio già esistente, skip: {output_path.name}")
        return output_path

    narration = script_to_narration(script, voice)
    print(f"    Generazione audio ({voice})...")
    generate_audio(narration, output_path, voice)
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
