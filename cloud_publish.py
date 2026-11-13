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


# ── rotazione dei nuovi format (piano 2026-11-13) ─────────────────────────────
# Variabile di repository FORMAT_ROTATION (come PUBLISH_ENABLED). Se NON e' "true"
# il run pubblica solo absurd facts, esattamente come prima.
# Se e' accesa, il formato dipende dalla FASCIA oraria UTC, non dall'ora esatta:
# il cron di GitHub parte spesso 30-60+ minuti in ritardo.
#   < 10 UTC -> quiz      (cron delle 07)
#   10-14    -> dati      (cron delle 12; non ancora costruito -> absurd)
#   >= 15    -> absurd    (cron delle 17)
# Una coda vuota o un formato non ancora pronto ricadono sempre su absurd.
def rotation_enabled() -> bool:
    return os.environ.get("FORMAT_ROTATION", "").strip().lower() in _TRUTHY


def slot_format(hour_utc: int | None = None) -> str:
    if hour_utc is None:
        from datetime import datetime, timezone
        hour_utc = datetime.now(timezone.utc).hour
    if hour_utc < 10:
        return "quiz"
    if hour_utc < 15:
        return "data"
    return "absurd"


def publish_quiz(state: dict) -> int | None:
    """Pubblica il prossimo quiz. None = niente da pubblicare (si ricade su absurd)."""
    from formats import quiz
    fmt_state = state.setdefault("formats", {}).setdefault("quiz", {"next": 1})
    qn = int(fmt_state.get("next", 1))
    item = next((i for i in quiz.load_queue() if i["id"] == qn), None)
    if item is None:
        print(f"ATTENZIONE: coda quiz finita (#{qn}): pubblico un absurd fact al suo posto.")
        print("Rimedio: py pipeline/formats/quiz.py build con piu' video, poi commit.")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    video_p = OUTPUT_DIR / f"quiz_{qn}.mp4"
    print(f"=== Pubblicazione QUIZ #{qn} ({item['kind']}) ===")
    quiz.render(item, video_p)

    from upload_youtube import upload_script_video
    video_id = upload_script_video(item, video_p, publish_at=None)
    print(f"PUBBLICATO: https://youtu.be/{video_id}")
    try:
        from upload_instagram import upload_script_reel
        media_id = upload_script_reel(item, video_p)
        if media_id:
            print(f"PUBBLICATO SU INSTAGRAM: media {media_id}")
    except Exception as e:  # noqa: BLE001
        print(f"ATTENZIONE: upload Instagram fallito (YouTube ok): {e}")

    fmt_state["next"] = qn + 1
    save_state(state)
    print(f"Prossimo quiz: #{fmt_state['next']}")
    return 0


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

    if not publishing_enabled():
        # CONTROLLO DI SALUTE: si e' arrivati fin qui, quindi checkout, Python,
        # dipendenze, ffmpeg e caricamento degli script funzionano. Non si tocca
        # nulla che pubblichi, non si sfiorano le credenziali, state.json resta
        # fermo. Un run "verde" qui significa: l'automazione e' viva e pronta.
        print("=== CONTROLLO DI SALUTE (pubblicazione DISATTIVATA) ===")
        print(f"Script caricati: {total}. Il prossimo sarebbe il #{nxt}.")
        if script is None:
            print(f"ATTENZIONE: lo script #{nxt} non esiste: la coda e' finita.")
            print("Non e' urgente adesso perche' la pubblicazione e' spenta, ma va")
            print("rifornita prima di riaccenderla, o il primo run utile fallira'.")
        else:
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

    if rotation_enabled():
        fmt = slot_format()
        print(f"Rotazione format ACCESA: slot '{fmt}'")
        if fmt == "quiz":
            rc = publish_quiz(state)
            if rc is not None:
                return rc

    # ── coda esaurita: il run FALLISCE, non esce verde ───────────────────────────
    # Fino al 2026-08-31 qui c'era un "return 0  # uscita pulita, non un errore".
    # Conseguenza reale: il 26/08 e' finito lo script #209, l'ultimo, e da allora il
    # job ha girato 3 volte al giorno restando VERDE senza pubblicare niente. Nessuna
    # email, nessun log rosso, nessuno se ne e' accorto per cinque giorni: il canale
    # sembrava attivo e non lo era. Una coda vuota mentre la pubblicazione e' accesa
    # e' un guasto, e un guasto si vede.
    if script is None:
        print(f"ERRORE: lo script #{nxt} non esiste (in archivio ce ne sono {total}).")
        print("La coda e' finita: la pubblicazione e' accesa ma non c'e' piu' niente")
        print("da pubblicare, quindi questo run fallisce di proposito.")
        print("")
        print("Rimedio: aggiungere un nuovo pipeline/english_scripts_N.json nel formato")
        print("single (schema in docs/FORMATO-SINGLE.md, sezione 3). Il numero degli")
        print("script e' posizionale: i file si concatenano in ordine di numero, quindi")
        print("il nuovo file si accoda da solo dopo l'ultimo esistente.")
        print("Il rifornimento automatico e' il job 'Genera nuove curiosita'' e chiede")
        print("il secret ANTHROPIC_API_KEY: se non e' impostato, non genera niente.")
        return 1

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
