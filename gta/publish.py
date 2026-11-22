"""Carica su YouTube gli Shorts GTA resi da gta.compose, programmati negli slot giornalieri.

Canale SEPARATO da @5absurdfacts: token proprio (gta/yt_token.json, ignorato da git)
e controllo del canale PRIMA di ogni upload (channels.list mine=true, scope
youtube.readonly). Diverso dall'uploader di 5absurdfacts, che puo' verificare il
canale solo DOPO l'upload: qui un token sbagliato non carica nulla.

Setup (una volta, dopo aver creato il canale GTA):
    py -3 -m gta.publish --auth              # istruzioni OAuth Playground
    py -3 -m gta.publish --token "1//..."    # salva token, stampa il canale collegato
    -> copia il channelId stampato in GTA_CHANNEL_ID qui sotto

Uso:
    py -3 -m gta.publish --dry-run           # mostra cosa caricherebbe e quando
    py -3 -m gta.publish                     # carica fino a --max video (default 6)

Coda: output/gta/render/<id>.mp4 + <id>.yt.json (da gta.compose), in ordine di id.
Registro: gta/published.json (versionato: e' la memoria di cosa e' gia' online).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from gta.fetch import gta_dir  # noqa: E402

TOKEN_PATH = HERE / "yt_token.json"
SECRETS_PATH = REPO / "client_secrets.json"
PUBLISHED = HERE / "published.json"

# channelId del canale GTA (stampato da --token). Vuoto = nessun upload possibile.
GTA_CHANNEL_ID = ""
# I canali di 5absurdfacts: un upload GTA li' sarebbe un danno, si blocca sempre.
VIETATI = {"UC98nOdXD_giA-xqs5CuBBLA", "UC_iHL7XJY4Wnes8BFycPuCQ"}

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
# Orari di pubblicazione (UTC). Pubblico inglese/USA: 17:00 UTC = 12:00 ET, 23:00 UTC = 18:00 ET.
SLOTS_UTC = ["17:00", "23:00"]
ANTICIPO_MIN = timedelta(hours=1)   # mai programmare a meno di 1h da adesso
TAGS = ["GTA 6", "GTA VI", "GTA 6 secrets", "GTA 6 easter eggs", "Grand Theft Auto VI",
        "gaming", "shorts"]
CATEGORY_GAMING = "20"


# ── pianificazione ───────────────────────────────────────────────────────────

def _slot_times(giorno: datetime) -> list[datetime]:
    out = []
    for s in SLOTS_UTC:
        h, m = map(int, s.split(":"))
        out.append(giorno.replace(hour=h, minute=m, second=0, microsecond=0))
    return out


def prossimi_slot(n: int, now: datetime, occupati: set[datetime]) -> list[datetime]:
    """I prossimi n slot liberi, almeno ANTICIPO_MIN dopo `now` e dopo l'ultimo gia' programmato.

    Dopo l'ultimo: se un video e' programmato fra 3 giorni, un nuovo upload non deve
    passargli davanti e lasciare buchi nei giorni in mezzo."""
    minimo = now + ANTICIPO_MIN
    futuri = [o for o in occupati if o > now]
    if futuri:
        minimo = max(minimo, max(futuri) + timedelta(seconds=1))
    out: list[datetime] = []
    giorno = minimo.replace(hour=0, minute=0, second=0, microsecond=0)
    while len(out) < n:
        for t in _slot_times(giorno):
            if t >= minimo and t not in occupati and len(out) < n:
                out.append(t)
        giorno += timedelta(days=1)
    return out


def load_published(path: Path = PUBLISHED) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_published(data: dict, path: Path = PUBLISHED) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def coda(render_dir: Path, published: dict) -> list[tuple[str, Path, dict]]:
    """Video resi e non ancora caricati, in ordine di id. Gli esempi ('_...') sono esclusi."""
    out = []
    for mp4 in sorted(render_dir.glob("*.mp4")):
        vid = mp4.stem
        meta_p = render_dir / f"{vid}.yt.json"
        if vid.startswith("_") or vid in published or not meta_p.exists():
            continue
        out.append((vid, mp4, json.loads(meta_p.read_text(encoding="utf-8"))))
    return out


def titolo(t: str) -> str:
    t = t.strip()
    if "#shorts" not in t.lower():
        t = f"{t} #Shorts"
    if len(t) > 100:
        t = t[:100 - len(" #Shorts")].rstrip() + " #Shorts"
    return t


# ── YouTube ──────────────────────────────────────────────────────────────────

class CanaleSbagliato(RuntimeError):
    pass


def _credenziali():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if not TOKEN_PATH.exists():
        raise SystemExit(f"Token GTA mancante ({TOKEN_PATH}). Esegui: py -3 -m gta.publish --auth")
    data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    creds = Credentials(token=data.get("access_token"), refresh_token=data["refresh_token"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=data["client_id"], client_secret=data["client_secret"],
                        scopes=SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        data["access_token"] = creds.token
        TOKEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return creds


def servizio():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_credenziali())


def canale_collegato(service) -> tuple[str, str]:
    items = service.channels().list(part="snippet", mine=True).execute().get("items", [])
    if len(items) != 1:
        raise CanaleSbagliato(f"il token vede {len(items)} canali invece di 1")
    return items[0]["id"], items[0]["snippet"]["title"]


def verifica_canale(service, atteso: str = None) -> str:
    atteso = GTA_CHANNEL_ID if atteso is None else atteso
    ch_id, nome = canale_collegato(service)
    if ch_id in VIETATI:
        raise CanaleSbagliato(f"il token GTA punta a 5absurdfacts ({nome}, {ch_id}): rifai --auth "
                              "scegliendo il canale GTA nel consenso")
    if not atteso:
        raise CanaleSbagliato(f"GTA_CHANNEL_ID vuoto in gta/publish.py: il token punta a "
                              f"'{nome}' ({ch_id}). Se e' il canale GTA, copia l'id li'.")
    if ch_id != atteso:
        raise CanaleSbagliato(f"token su '{nome}' ({ch_id}), atteso {atteso}")
    return nome


def carica(service, mp4: Path, meta: dict, quando: datetime) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {"title": titolo(meta["title"]), "description": meta["description"],
                    "tags": TAGS, "categoryId": CATEGORY_GAMING},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "publishAt": quando.strftime("%Y-%m-%dT%H:%M:%S.000Z")},
    }
    req = service.videos().insert(part="snippet,status", body=body,
                                  media_body=MediaFileUpload(str(mp4), mimetype="video/mp4",
                                                             resumable=True, chunksize=4 * 1024 * 1024))
    resp, tentativi = None, 0
    while resp is None:
        try:
            _, resp = req.next_chunk()
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and tentativi < 5:
                tentativi += 1
                time.sleep(2 ** tentativi)
            else:
                raise
    ch = (resp.get("snippet") or {}).get("channelId")
    if ch and GTA_CHANNEL_ID and ch != GTA_CHANNEL_ID:   # doppio controllo, dopo l'upload
        raise CanaleSbagliato(f"video {resp['id']} finito su {ch}: cancellalo da Studio")
    return resp["id"]


def pubblica(service, render_dir: Path, n_max: int, now: datetime, dry_run: bool,
             published_path: Path = PUBLISHED, upload=carica) -> list[str]:
    published = load_published(published_path)
    da_fare = coda(render_dir, published)[:n_max]
    if not da_fare:
        print("Niente da caricare: nessun video reso e non ancora pubblicato.")
        return []
    occupati = {datetime.fromisoformat(v["publish_at"]) for v in published.values()}
    slot = prossimi_slot(len(da_fare), now, occupati)

    if not dry_run:
        print(f"Canale verificato: {verifica_canale(service)}")
    caricati = []
    for (vid, mp4, meta), quando in zip(da_fare, slot):
        print(f"{vid}: {quando:%Y-%m-%d %H:%M} UTC  {titolo(meta['title'])}")
        if dry_run:
            continue
        yt_id = upload(service, mp4, meta, quando)
        published[vid] = {"youtube_id": yt_id, "publish_at": quando.isoformat(),
                          "title": meta["title"]}
        save_published(published, published_path)   # subito: mai ricaricare lo stesso video
        print(f"   caricato https://youtu.be/{yt_id}")
        caricati.append(yt_id)
    return caricati


# ── auth ─────────────────────────────────────────────────────────────────────

def _client() -> tuple[str, str]:
    cfg = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    cfg = cfg.get("installed") or cfg.get("web")
    return cfg["client_id"], cfg["client_secret"]


def auth_istruzioni() -> None:
    cid, sec = _client()
    print(f"""
OAuth Playground per il canale GTA (stesso progetto Google di 5absurdfacts):
  1. Ingranaggio in alto a destra > 'Use your own OAuth credentials'
       Client ID:     {cid}
       Client Secret: {sec}
  2. A sinistra, in 'YouTube Data API v3', spunta ENTRAMBI:
       .../auth/youtube.upload
       .../auth/youtube.readonly
  3. 'Authorize APIs' e, nella scelta account/canale, seleziona il canale GTA
     (NON 5AbsurdFacts)
  4. 'Exchange authorization code for tokens' e copia il Refresh token
  5. py -3 -m gta.publish --token "INCOLLA_QUI"
""")
    webbrowser.open("https://developers.google.com/oauthplayground/")


def salva_token(refresh: str) -> None:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    cid, sec = _client()
    creds = Credentials(token=None, refresh_token=refresh, token_uri="https://oauth2.googleapis.com/token",
                        client_id=cid, client_secret=sec, scopes=SCOPES)
    creds.refresh(Request())
    ch_id, nome = canale_collegato(build("youtube", "v3", credentials=creds))
    if ch_id in VIETATI:
        raise SystemExit(f"Questo token e' di 5absurdfacts ({nome}). Rifai il consenso scegliendo il canale GTA.")
    TOKEN_PATH.write_text(json.dumps({"client_id": cid, "client_secret": sec, "refresh_token": refresh,
                                      "access_token": creds.token}, indent=2), encoding="utf-8")
    print(f"Token salvato in {TOKEN_PATH}\nCanale collegato: {nome}\nchannelId: {ch_id}")
    if ch_id != GTA_CHANNEL_ID:
        print(f"-> metti GTA_CHANNEL_ID = \"{ch_id}\" in gta/publish.py")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Carica gli Shorts GTA programmati negli slot.")
    ap.add_argument("--auth", action="store_true")
    ap.add_argument("--token")
    ap.add_argument("--max", type=int, default=6, help="video da caricare in questo giro (default 6 = 3 giorni)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.auth:
        auth_istruzioni()
        return 0
    if a.token:
        salva_token(a.token.strip())
        return 0
    try:
        pubblica(None if a.dry_run else servizio(), gta_dir() / "render", a.max,
                 datetime.now(timezone.utc), a.dry_run)
    except CanaleSbagliato as e:
        print(f"[STOP] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
