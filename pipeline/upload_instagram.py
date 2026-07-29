# Durata: LEGATO-A:P09
"""
Upload automatico su Instagram Reels (API ufficiale Meta, "Instagram Login").

Come funziona (flusso container, vedi docs/SETUP_INSTAGRAM.md per il setup):
  1. il video viene messo a un URL pubblico (host_video.py - Meta lo scarica lei);
  2. POST /media crea il "container" del Reel (video_url + caption);
  3. si fa polling dello stato finche' e' FINISHED (30s-2min);
  4. POST /media_publish pubblica. Immediato: niente scheduling lato API
     (la programmazione la fa gia' il cron di GitHub Actions).

Config via variabili d'ambiente (GitHub secrets in cloud, $env: in locale):
  IG_USER_ID       ID numerico dell'account Instagram Business
  IG_ACCESS_TOKEN  token long-lived (60 giorni; rinnovo: --refresh-token)
  + TRANSFER_REPO / TRANSFER_TOKEN per l'hosting (host_video.py)

Se le variabili mancano, upload_script_reel() salta con un messaggio e
ritorna None: la pipeline YouTube non si ferma mai per colpa di Instagram.

Limiti API verificati (2026-07-05): account Business (non Creator),
Reel 5-90 s, 100 post API / 24 h, token da rinnovare entro 60 giorni.

Nessuna dipendenza esterna: solo urllib della standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (  # noqa: E402
    IG_API_VERSION, IG_GRAPH_HOST, IG_HASHTAGS,
    IG_POLL_EVERY_S, IG_POLL_TIMEOUT_S, USERNAME, BG_CREDIT_LINE,
)

IG_USER_ID = os.environ.get("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")


def is_configured() -> bool:
    return bool(IG_USER_ID and IG_ACCESS_TOKEN)


# ── chiamate API (urllib, form-encoded) ───────────────────────────────────────

def _api(method: str, path: str, params: dict) -> dict:
    """Chiama la Graph API di Instagram. Solleva RuntimeError col messaggio Meta."""
    url = f"{IG_GRAPH_HOST}/{IG_API_VERSION}/{path}"
    query = urllib.parse.urlencode({**params, "access_token": IG_ACCESS_TOKEN})
    if method == "GET":
        req = urllib.request.Request(f"{url}?{query}")
    else:
        req = urllib.request.Request(url, data=query.encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("error", {})
        except Exception:
            err = {}
        msg = err.get("error_user_msg") or err.get("message") or str(e)
        raise RuntimeError(f"Instagram API {e.code}: {msg}") from None


# ── caption ───────────────────────────────────────────────────────────────────

def _hook_from_fact(fact: str, max_len: int = 80) -> str:
    """Hook dal primo fatto (stessa logica di upload_youtube, duplicata qui
    per non importare le librerie Google quando si pubblica solo su IG)."""
    hook = fact.strip().rstrip(".!?")
    if len(hook) <= max_len:
        return hook
    cut = hook[:max_len].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "..."


def build_caption(script: dict) -> str:
    """Caption IG: hook + i 5 fatti (testo reale, non solo hashtag) + hashtag
    + CREDITO CC-BY obbligatorio dello sfondo (vedi docs/SFONDI-DIRITTI.md)."""
    facts = "\n".join(f"{i}) {fact}" for i, fact in enumerate(script["facts"], 1))
    return (
        f"{_hook_from_fact(script['facts'][0])}... and 4 more ABSURD facts \U0001F92F\n\n"
        f"{facts}\n\n"
        f"Follow {USERNAME} for daily absurd facts!\n\n"
        f"{IG_HASHTAGS}\n\n"
        f"{BG_CREDIT_LINE}"
    )


# ── pubblicazione ─────────────────────────────────────────────────────────────

def publish_reel(video_url: str, caption: str) -> str:
    """Container -> poll fino a FINISHED -> publish. Ritorna l'id del media IG."""
    print("    Creazione container Reel...")
    container = _api("POST", f"{IG_USER_ID}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption[:2200],   # limite caption IG
        "share_to_feed": "true",
    })
    container_id = container["id"]

    # Meta scarica ed elabora il video: pubblicare prima di FINISHED da' errore.
    print("    Elaborazione lato Meta", end="", flush=True)
    waited = 0
    status = ""
    while waited < IG_POLL_TIMEOUT_S:
        time.sleep(IG_POLL_EVERY_S)
        waited += IG_POLL_EVERY_S
        status = _api("GET", container_id, {"fields": "status_code"}).get("status_code", "")
        if status == "FINISHED":
            print(" ok")
            break
        if status in ("ERROR", "EXPIRED"):
            detail = _api("GET", container_id, {"fields": "status"}).get("status", "")
            raise RuntimeError(f"Container {status}: {detail} "
                               "(cause tipiche: URL non raggiungibile da Meta, codec non H.264)")
        print(".", end="", flush=True)
    if status != "FINISHED":
        raise RuntimeError(f"Container non pronto dopo {IG_POLL_TIMEOUT_S}s (status: {status})")

    result = _api("POST", f"{IG_USER_ID}/media_publish", {"creation_id": container_id})
    media_id = result["id"]
    print(f"    Pubblicato su Instagram: media {media_id}")
    return media_id


def upload_script_reel(script: dict, video_path: Path) -> str | None:
    """Pubblica il video di uno script come Reel. Ritorna il media id, o None se saltato.

    Non solleva mai per configurazione mancante: stampa il motivo e salta
    (YouTube resta la piattaforma primaria, IG e' additivo).
    """
    if not is_configured():
        print("    Instagram: IG_USER_ID/IG_ACCESS_TOKEN non configurati -> salto (vedi docs/SETUP_INSTAGRAM.md)")
        return None

    from host_video import delete_release, host_on_github, hosting_configured
    if not hosting_configured():
        print("    Instagram: TRANSFER_REPO/TRANSFER_TOKEN non configurati -> salto (vedi docs/SETUP_INSTAGRAM.md)")
        return None

    tag = f"ig-{script.get('number', 0)}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    url, release_id = host_on_github(video_path, tag)
    try:
        return publish_reel(url, build_caption(script))
    finally:
        delete_release(release_id, tag)   # il transito si pulisce sempre, anche su errore


# ── rinnovo token (da fare almeno 1 volta ogni 60 giorni) ────────────────────

def refresh_token() -> None:
    """Rinnova il token long-lived (Instagram Login). Stampa il nuovo token:
    va incollato nel secret GitHub IG_ACCESS_TOKEN (e nell'env locale).
    Nota Meta: il token deve avere piu' di 24h di vita ed essere ancora valido."""
    data = _api("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"})
    days = data.get("expires_in", 0) // 86400
    print("Nuovo token (valido ~%d giorni) - aggiornare secret IG_ACCESS_TOKEN:\n" % days)
    print(data["access_token"])


# ── CLI (test manuale) ────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pubblica un Reel su Instagram (test manuale)")
    parser.add_argument("--script", type=int, help="Numero script (per caption + video in output/)")
    parser.add_argument("--video", type=str, help="Path del video (default: cerca in output/)")
    parser.add_argument("--video-url", type=str, help="Salta l'hosting: usa questo URL pubblico")
    parser.add_argument("--refresh-token", action="store_true", help="Rinnova il token long-lived")
    args = parser.parse_args()

    if args.refresh_token:
        refresh_token()
        return

    if not args.script:
        parser.error("--script N richiesto (o usa --refresh-token)")

    from extract_scripts import load_scripts
    script = next((s for s in load_scripts() if s["number"] == args.script), None)
    if script is None:
        raise SystemExit(f"Script #{args.script} non trovato")

    if args.video_url:
        publish_reel(args.video_url, build_caption(script))
        return

    if args.video:
        video_p = Path(args.video)
    else:
        from config import OUTPUT_DIR
        matches = sorted(OUTPUT_DIR.glob(f"00-video_{args.script}_*.mp4")) or \
                  sorted(OUTPUT_DIR.glob(f"00-video_{args.script}.mp4"))
        if not matches:
            raise SystemExit(f"Nessun video per lo script #{args.script} in {OUTPUT_DIR}")
        video_p = matches[-1]

    print(f"Video: {video_p}")
    upload_script_reel(script, video_p)


if __name__ == "__main__":
    main()
