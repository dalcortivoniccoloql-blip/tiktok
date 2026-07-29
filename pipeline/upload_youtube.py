# Durata: LEGATO-A:P09
"""
Upload automatico su YouTube Shorts.

Auth tramite OAuth Playground (metodo semplice, nessuna verifica app richiesta).
Vedi istruzioni: py pipeline\auth_youtube.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config import USERNAME, BG_CREDIT_LINE

# ── path ──────────────────────────────────────────────────────────────────────

_BASE = Path(__file__).parent.parent
SECRETS_PATH     = _BASE / "client_secrets.json"
YT_TOKEN_PATH    = _BASE / "yt_token.json"   # refresh token da OAuth Playground

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# ── auth ──────────────────────────────────────────────────────────────────────

def _get_credentials() -> Credentials:
    """
    Carica le credenziali da yt_token.json (refresh token ottenuto via OAuth Playground).
    Le rinnova automaticamente se scadute.
    """
    if not YT_TOKEN_PATH.exists():
        raise FileNotFoundError(
            "\n"
            "  yt_token.json non trovato.\n"
            "  Esegui prima: py pipeline\\auth_youtube.py\n"
        )

    with open(YT_TOKEN_PATH) as f:
        data = json.load(f)

    creds = Credentials(
        token         = data.get("access_token"),
        refresh_token = data["refresh_token"],
        token_uri     = "https://oauth2.googleapis.com/token",
        client_id     = data["client_id"],
        client_secret = data["client_secret"],
        scopes        = SCOPES,
    )

    if not creds.valid:
        creds.refresh(Request())
        # aggiorna il file con il nuovo access_token
        data["access_token"] = creds.token
        with open(YT_TOKEN_PATH, "w") as f:
            json.dump(data, f, indent=2)

    return creds


def _check_secrets():
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(
            "\n"
            "════════════════════════════════════════════════════════\n"
            "  client_secrets.json non trovato!\n"
            "\n"
            "  Per ottenerlo (5 minuti):\n"
            "  1. Vai su https://console.cloud.google.com\n"
            "  2. Crea un nuovo progetto (es. 'tiktok-pipeline')\n"
            "  3. Menu laterale: API e servizi > Libreria\n"
            "     Cerca 'YouTube Data API v3' e abilitala\n"
            "  4. API e servizi > Credenziali > Crea credenziali\n"
            "     Scegli 'ID client OAuth 2.0' > Tipo: 'App desktop'\n"
            "  5. Scarica il JSON e rinominalo 'client_secrets.json'\n"
            f"     Mettilo qui: {SECRETS_PATH}\n"
            "  6. API e servizi > Schermata consenso OAuth:\n"
            "     Aggiungi il tuo email come 'Utente di test'\n"
            "════════════════════════════════════════════════════════\n"
        )


def build_service():
    """Crea e ritorna il client YouTube autenticato."""
    return build("youtube", "v3", credentials=_get_credentials())


# ── metadata helpers ──────────────────────────────────────────────────────────

def _hook_from_fact(fact: str, max_len: int) -> str:
    """Accorcia il primo fatto a un hook da titolo, tagliando su un confine di parola."""
    hook = fact.strip().rstrip(".!?")
    if len(hook) <= max_len:
        return hook
    cut = hook[:max_len].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "..."


# Rotazione per numero di script: mai due video con lo stesso titolo
# (il titolo statico uguale per tutti era pessimo per ricerca e sembrava spam).
_TITLE_TEMPLATES = [
    "{hook} - and 4 more ABSURD facts #Shorts",
    "Did you know? {hook} #Shorts",
    "{hook}... wait for the LAST one #Shorts",
]


def build_title(script: dict) -> str:
    """Titolo YouTube dinamico: hook dal primo fatto + template a rotazione.
    #Shorts nel titolo e meno di 100 caratteri = classificazione garantita come Short."""
    template = _TITLE_TEMPLATES[script.get("number", 0) % len(_TITLE_TEMPLATES)]
    room = 100 - len(template.format(hook=""))
    hook = _hook_from_fact(script["facts"][0], room)
    return template.format(hook=hook)


def build_description(script: dict) -> str:
    """Descrizione YouTube dinamica: hook + i 5 fatti del video (keyword reali per il SEO)
    + hashtag puliti (niente doppioni, niente #fyp che su YouTube non serve)
    + CREDITO CC-BY obbligatorio dello sfondo (vedi docs/SFONDI-DIRITTI.md)."""
    facts = "\n".join(f"{i}) {fact}" for i, fact in enumerate(script["facts"], 1))
    return (
        "5 ABSURD facts that will leave you SPEECHLESS\U0001F636"
        " ... the last one will blow your mind!\U0001F92F\n\n"
        "In this Short:\n"
        f"{facts}\n\n"
        f"Follow {USERNAME} for daily absurd facts!\n\n"
        "#shorts #facts #didyouknow #amazingfacts #funfacts\n\n"
        f"{BG_CREDIT_LINE}"
    )


TAGS = [
    "absurd facts", "amazing facts", "fun facts", "did you know",
    "random facts", "interesting facts", "mind blowing facts",
    "facts shorts", "science facts", "animal facts", "space facts",
    "history facts",
]

# ── uploader ──────────────────────────────────────────────────────────────────

_RETRIABLE_EXCEPTIONS = (Exception,)
_MAX_RETRIES = 5


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    publish_at: datetime | None = None,
    category_id: str = "27",   # 27 = Education
) -> str:
    """
    Carica un video su YouTube come Short.

    Se publish_at è nel futuro, il video viene programmato (privato fino a quella data).
    Se publish_at è None o nel passato, viene pubblicato subito come pubblico.
    Ritorna l'ID del video caricato.
    """
    service = build_service()

    if tags is None:
        tags = TAGS

    # #Shorts nel titolo aiuta l'algoritmo
    if "#Shorts" not in title and "#shorts" not in title:
        title = f"{title} #Shorts"
    title = title[:100]  # limite YouTube

    now_utc = datetime.now(timezone.utc)
    schedule_future = (
        publish_at is not None
        and publish_at.tzinfo is not None
        and publish_at > now_utc
    )

    body: dict = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  category_id,
        },
        "status": {
            "selfDeclaredMadeForKids": False,
            "privacyStatus": "private" if schedule_future else "public",
        },
    }

    if schedule_future:
        body["status"]["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"    Programmato per: {publish_at.strftime('%d/%m/%Y %H:%M UTC')}")
    else:
        print(f"    Pubblicazione immediata")

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=4 * 1024 * 1024,  # 4 MB chunks
    )

    insert_request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    return _resumable_upload(insert_request, video_path.name)


def _resumable_upload(request, filename: str) -> str:
    """Esegue l'upload con retry automatico."""
    response = None
    retry = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"    Upload {filename}: {pct:>3}%", end="\r")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < _MAX_RETRIES:
                retry += 1
                wait = 2 ** retry
                print(f"    Errore {e.resp.status}, retry {retry}/{_MAX_RETRIES} tra {wait}s...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            if retry < _MAX_RETRIES:
                retry += 1
                wait = 2 ** retry
                print(f"    Errore: {e}, retry {retry}/{_MAX_RETRIES} tra {wait}s...")
                time.sleep(wait)
            else:
                raise

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    print(f"\n    Caricato: {url}")
    return video_id


# ── batch upload ──────────────────────────────────────────────────────────────

def upload_script_video(
    script: dict,
    video_path: Path,
    publish_at: datetime | None = None,
) -> str:
    """
    Carica il video di uno script su YouTube.
    Ritorna l'ID del video.
    """
    title       = build_title(script)
    description = build_description(script)

    return upload_video(
        video_path  = video_path,
        title       = title,
        description = description,
        publish_at  = publish_at,
    )
