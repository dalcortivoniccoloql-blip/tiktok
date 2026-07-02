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

def build_title(script: dict) -> str:
    """Titolo per-video: usa il primo fatto (l'hook) per un titolo UNICO e curioso.

    Titoli diversi per ogni Short = meno "templato" (policy) + CTR migliore.
    #Shorts nel titolo garantisce la classificazione come Short. Limite 100 caratteri.
    """
    hook   = script["facts"][0].strip().rstrip(".")
    suffix = " \U0001F92F #Shorts"
    max_len = 100 - len(suffix)
    if len(hook) > max_len:
        hook = hook[: max_len - 1].rstrip() + "…"
    return hook + suffix


def build_description(script: dict) -> str:
    """Descrizione per-video: elenca i fatti dello script (testo unico) + hashtag."""
    facts = "\n".join(f"• {f}" for f in script["facts"])
    return (
        "Absurd but TRUE facts \U0001F92F Which one surprised you most?\n\n"
        f"{facts}\n\n"
        "#Shorts #facts #didyouknow #curiosity #viral #amazingfacts"
    )


TAGS = [
    "curiosita", "fatti assurdi", "facts", "scienza", "natura",
    "animali", "spazio", "storia", "shorts", "viral",
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
