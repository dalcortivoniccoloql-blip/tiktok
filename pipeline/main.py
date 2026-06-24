"""
Pipeline TikTok - genera audio, video e carica su YouTube Shorts.

Uso rapido:
  cd tiktok
  py pipeline/main.py --list
  py pipeline/main.py --count 5
  py pipeline/main.py --script 13 --count 23 --video-only
  py pipeline/main.py --count 5 --upload-youtube --from-date 2025-10-01
  py pipeline/main.py --upload-youtube --video-only --script 36 --count 4 --from-date 2025-10-01
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    AUDIO_DIR, OUTPUT_DIR,
    DEFAULT_VOICE, POSTS_PER_DAY, POST_TIMES_UTC,
)
from extract_scripts import load_scripts
from generate_audio import generate_audio_for_script
from generate_video import create_video


def _schedule_date(index: int, start: datetime) -> datetime:
    """Solo per il nome file: distribuisce a POSTS_PER_DAY al giorno."""
    return start + timedelta(days=index // POSTS_PER_DAY)


def _schedule_date_utc(index: int, start: datetime) -> datetime:
    """
    Data/ora di pubblicazione YouTube (UTC), distribuendo POSTS_PER_DAY post
    al giorno agli orari di POST_TIMES_UTC.
    Es: index 0,1,2 -> giorno 0 alle 07/12/17; index 3,4,5 -> giorno 1, ecc.
    """
    day_offset = index // POSTS_PER_DAY
    slot       = index %  POSTS_PER_DAY
    hour       = POST_TIMES_UTC[slot]
    base       = start + timedelta(days=day_offset)
    return datetime(
        base.year, base.month, base.day,
        hour, 0, 0, tzinfo=timezone.utc,
    )


def _find_script(scripts: list[dict], number: int) -> dict | None:
    for s in scripts:
        if s["number"] == number:
            return s
    return None


def _auto_start_script(scripts: list[dict]) -> int:
    """Primo script senza video prodotto."""
    existing = {
        int(p.stem.split("_")[1])
        for p in OUTPUT_DIR.glob("00-video_*.mp4")
        if len(p.stem.split("_")) >= 2 and p.stem.split("_")[1].isdigit()
    }
    for s in scripts:
        if s["number"] not in existing:
            return s["number"]
    return scripts[-1]["number"] + 1 if scripts else 1


def run(
    script_start: int,
    count: int,
    audio_only: bool,
    video_only: bool,
    upload_youtube: bool,
    start_date: datetime,
    overwrite: bool,
    voice: str,
    publish_now: bool = False,
) -> None:
    print("\nCaricamento script...")
    scripts = load_scripts()
    if not scripts:
        print("Nessuno script trovato.")
        return

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # importa uploader solo se serve (evita errori se google non installato)
    uploader = None
    if upload_youtube:
        try:
            from upload_youtube import upload_script_video
            uploader = upload_script_video
        except ImportError as e:
            print(f"Errore import uploader YouTube: {e}")
            print("Esegui: py -m pip install google-api-python-client google-auth-oauthlib")
            return

    produced   = 0
    uploaded   = 0
    yt_results = []

    for i in range(count):
        script_num = script_start + i
        script = _find_script(scripts, script_num)
        if script is None:
            idx = script_start - 1 + i
            if idx < len(scripts):
                script = scripts[idx]
                script_num = script["number"]
            else:
                print(f"\nNessun altro script disponibile dopo #{script_num - 1}.")
                break

        date    = _schedule_date(i, start_date)
        ds      = date.strftime("%d-%m")
        audio_p = AUDIO_DIR / f"{script_num}.mp3"
        video_p = OUTPUT_DIR / f"00-video_{script_num}_{ds}.mp4"

        print(f"\n[{i+1}/{count}] Script #{script_num} -> {video_p.name}")

        # 1. Audio
        if not video_only:
            generate_audio_for_script(script, audio_p, voice=voice, overwrite=overwrite)

        # 2. Video
        if not audio_only:
            if not audio_p.exists():
                print(f"  SKIP video: audio mancante ({audio_p.name})")
                continue
            create_video(script, audio_p, video_p, overwrite=overwrite)

        produced += 1

        # 3. Upload YouTube
        if upload_youtube and uploader and not audio_only:
            if not video_p.exists():
                print(f"  SKIP YouTube upload: video non trovato")
                continue
            publish_at = None if publish_now else _schedule_date_utc(i, start_date)
            print(f"  Caricamento su YouTube...")
            try:
                video_id = uploader(script, video_p, publish_at=publish_at)
                yt_results.append((script_num, video_id, publish_at))
                uploaded += 1
            except Exception as e:
                print(f"  ERRORE upload YouTube: {e}")

    print(f"\nCompletato: {produced}/{count} video prodotti")
    if upload_youtube:
        print(f"YouTube upload: {uploaded}/{produced}")
        if yt_results:
            print("\nVideo caricati:")
            for num, vid_id, pub in yt_results:
                pub_str = pub.strftime("%d/%m/%Y %H:%M UTC") if pub else "immediato"
                print(f"  Script #{num:>3}  https://youtu.be/{vid_id}  ({pub_str})")


def cmd_list(scripts: list[dict]) -> None:
    existing_audio = {p.stem for p in AUDIO_DIR.glob("*.mp3")}
    existing_video = {
        p.stem.split("_")[1]
        for p in OUTPUT_DIR.glob("00-video_*.mp4")
        if len(p.stem.split("_")) >= 2
    }

    print(f"\n{'#':>4}  {'Audio':5}  {'Video':5}  Anteprima primo fatto")
    print("-" * 75)
    for s in scripts:
        n      = str(s["number"])
        a_mark = "OK" if n in existing_audio else "--"
        v_mark = "OK" if n in existing_video else "--"
        preview = s["facts"][0][:55] + "..." if len(s["facts"][0]) > 55 else s["facts"][0]
        print(f"  {n:>3}  [{a_mark}]    [{v_mark}]    {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline TikTok: script -> audio -> video -> YouTube Shorts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--list",            action="store_true", help="Elenca tutti gli script")
    parser.add_argument("--script",          type=int,  default=None,         help="Script da cui partire (default: auto)")
    parser.add_argument("--count",           type=int,  default=1,            help="Quanti video generare (default: 1)")
    parser.add_argument("--audio-only",      action="store_true",             help="Solo audio, salta video")
    parser.add_argument("--video-only",      action="store_true",             help="Solo video, audio deve esistere")
    parser.add_argument("--upload-youtube",  action="store_true",             help="Carica su YouTube Shorts dopo la generazione")
    parser.add_argument("--from-date",       type=str,  default=None,         help="Data primo upload YYYY-MM-DD (default: oggi)")
    parser.add_argument("--publish-now",     action="store_true",             help="Pubblica subito invece di programmare")
    parser.add_argument("--overwrite",       action="store_true",             help="Sovrascrive file esistenti")
    parser.add_argument("--voice",           type=str,  default=DEFAULT_VOICE, help=f"Voce TTS (default: {DEFAULT_VOICE})")
    args = parser.parse_args()

    scripts = load_scripts()

    if args.list:
        cmd_list(scripts)
        return

    if args.from_date:
        start_date = datetime.strptime(args.from_date, "%Y-%m-%d")
    elif args.publish_now:
        start_date = datetime.now()
    else:
        # programmazione: parti da domani cosi' nessuno slot e' nel passato
        start_date = datetime.now() + timedelta(days=1)

    script_start = args.script if args.script is not None else _auto_start_script(scripts)
    print(f"Script di partenza: #{script_start}")

    run(
        script_start   = script_start,
        count          = args.count,
        audio_only     = args.audio_only,
        video_only     = args.video_only,
        upload_youtube = args.upload_youtube,
        start_date     = start_date,
        overwrite      = args.overwrite,
        voice          = args.voice,
        publish_now    = args.publish_now,
    )


if __name__ == "__main__":
    main()
