"""
Runner per GitHub Actions: pubblica UN Short e avanza lo stato.
Eseguito 3 volte al giorno dal workflow .github/workflows/publish.yml.

Lo stato (prossimo script da pubblicare) e' in state.json e viene
committato di nuovo nel repo dopo ogni esecuzione.
"""

import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE / "pipeline"))

from config import AUDIO_DIR, OUTPUT_DIR              # noqa: E402
from extract_scripts import load_scripts             # noqa: E402
from generate_audio import generate_audio_for_script  # noqa: E402
from generate_video import create_video              # noqa: E402

STATE_PATH = BASE / "state.json"

# ── interruttore di pubblicazione ─────────────────────────────────────────────
# Il cron e' ACCESO, ma pubblicare e' un'altra cosa: finche' l'audit YouTube non
# e' approvato ogni upload viene bloccato come privato e BRUCIA uno script (il
# contatore avanza, il video resta invisibile e va ricaricato da zero).
#
# Tenere il cron spento "per sicurezza" ha pero' un costo nascosto: nessuno ha
# mai visto questa automazione girare davvero nel cloud. Separando le due cose,
# il run gira ogni giorno come CONTROLLO DI SALUTE (checkout, dipendenze,
# ffmpeg, caricamento script) senza pubblicare nulla, e il giorno
# dell'approvazione basta cambiare UNA variabile: niente commit, niente push,
# nessuno scope 'workflow' richiesto.
#
#   Repo > Settings > Secrets and variables > Actions > Variables
#   > New repository variable > PUBLISH_ENABLED = true
_TRUTHY = {"1", "true", "yes", "on", "si", "sì"}


def publishing_enabled() -> bool:
    return os.environ.get("PUBLISH_ENABLED", "").strip().lower() in _TRUTHY


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"next": 1}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> int:
    scripts = load_scripts()
    total   = len(scripts)

    state = load_state()
    nxt   = int(state.get("next", 1))

    script = next((s for s in scripts if s["number"] == nxt), None)
    if script is None:
        print(f"Nessuno script #{nxt} (totale {total}). Niente da pubblicare.")
        print("Aggiungi un nuovo file english_scripts_N.json per continuare.")
        return 0  # uscita pulita, non un errore

    if not publishing_enabled():
        # CONTROLLO DI SALUTE: si e' arrivati fin qui, quindi checkout, Python,
        # dipendenze, ffmpeg e caricamento degli script funzionano. Non si tocca
        # nulla che pubblichi, non si sfiorano le credenziali, state.json resta
        # fermo. Un run "verde" qui significa: l'automazione e' viva e pronta.
        print("=== CONTROLLO DI SALUTE (pubblicazione DISATTIVATA) ===")
        print(f"Script caricati: {total}. Il prossimo sarebbe il #{nxt}.")
        print(f"Primo fatto: {script['facts'][0]}")
        print("")
        print("Non pubblico niente: PUBLISH_ENABLED non e' impostata.")
        print("E' voluto. Finche' l'audit YouTube non e' approvato ogni upload")
        print("viene bloccato come privato e BRUCIA lo script (il contatore")
        print("avanza, il video resta invisibile e va ricaricato da zero).")
        print("")
        print("Quando arriva l'email di approvazione, per accendere davvero:")
        print("  Repo > Settings > Secrets and variables > Actions > Variables")
        print("  > New repository variable > PUBLISH_ENABLED = true")
        print("Nessun commit e nessun push necessari.")
        return 0

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    audio_p = AUDIO_DIR / f"{nxt}.mp3"
    video_p = OUTPUT_DIR / f"00-video_{nxt}.mp4"

    print(f"=== Pubblicazione script #{nxt}/{total} ===")
    print(f"Primo fatto: {script['facts'][0]}")

    # 1. audio (sempre fresco, coerente coi sottotitoli)
    generate_audio_for_script(script, audio_p, overwrite=True)

    # 2. video
    create_video(script, audio_p, video_p, overwrite=True)

    # 3. upload immediato (il cron parte gia' all'orario di pubblicazione)
    from upload_youtube import upload_script_video
    video_id = upload_script_video(script, video_p, publish_at=None)
    print(f"PUBBLICATO: https://youtu.be/{video_id}")

    # 3b. Instagram Reels — best-effort: se i secret IG non sono configurati salta
    # con un messaggio; se fallisce logga ma NON blocca il run (YouTube e' gia' ok).
    try:
        from upload_instagram import upload_script_reel
        media_id = upload_script_reel(script, video_p)
        if media_id:
            print(f"PUBBLICATO SU INSTAGRAM: media {media_id}")
    except Exception as e:  # noqa: BLE001
        print(f"ATTENZIONE: upload Instagram fallito (YouTube ok): {e}")

    # 4. avanza lo stato
    state["next"] = nxt + 1
    save_state(state)
    print(f"Prossimo script: #{state['next']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
