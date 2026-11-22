"""Cerca e scarica clip GTA 6 da Twitch, SOLO dagli streamer confermati in whitelist.

Fase 1 del canale GTA (vedi piano 2026-11-22): lo script porta le clip candidate
in una cartella "inbox" sul PC; la scelta resta manuale.

Uso:
    py -3 -m gta.fetch                 # ultime 48h, max 5 clip per streamer
    py -3 -m gta.fetch --ore 24 --per-streamer 3 --min-views 50
    py -3 -m gta.fetch --dry-run       # elenca senza scaricare

Credenziali (app su dev.twitch.tv, flusso client-credentials):
    TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET come variabili d'ambiente,
    oppure nel file gta/twitch.env (ignorato da git: *.env) come righe CHIAVE=valore.

Output (default output/gta/, ignorato da git; override con env GTA_DIR):
    inbox/<streamer>_<clip_id>.mp4   la clip
    inbox/<streamer>_<clip_id>.json  metadati + riga di credito pronta
    seen_clips.json                  clip gia' viste: non vengono riscaricate

Nota: scaricare clip Twitch fuori dalle funzioni native e' tecnicamente contro i
ToS Twitch. Rischio basso ma noto; per questo si scarica solo da streamer che
permettono esplicitamente il riuso.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WHITELIST = HERE / "whitelist.json"
ENV_FILE = HERE / "twitch.env"
GAME_NAME = "Grand Theft Auto VI"

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"


def gta_dir() -> Path:
    return Path(os.environ.get("GTA_DIR", str(REPO / "output" / "gta")))


# ── whitelist ────────────────────────────────────────────────────────────────

def load_whitelist(path: Path = WHITELIST) -> list[str]:
    """Login (minuscoli) degli streamer CONFERMATI. Le voci non confermate o
    senza prova del permesso vengono ignorate: e' la regola del canale."""
    data = json.loads(path.read_text(encoding="utf-8"))
    logins = []
    for s in data.get("streamer", []):
        login = (s.get("login") or "").strip().lower()
        if login and s.get("confermato") is True and (s.get("prova_permesso") or "").strip():
            logins.append(login)
    return sorted(set(logins))


# ── credenziali ──────────────────────────────────────────────────────────────

def load_credentials(env_file: Path = ENV_FILE) -> tuple[str, str]:
    vals = {}
    if env_file.exists():
        for riga in env_file.read_text(encoding="utf-8").splitlines():
            riga = riga.strip()
            if riga and not riga.startswith("#") and "=" in riga:
                k, v = riga.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    cid = os.environ.get("TWITCH_CLIENT_ID") or vals.get("TWITCH_CLIENT_ID")
    sec = os.environ.get("TWITCH_CLIENT_SECRET") or vals.get("TWITCH_CLIENT_SECRET")
    if not cid or not sec:
        raise SystemExit(
            "Credenziali Twitch mancanti.\n"
            "  1. Vai su https://dev.twitch.tv/console/apps e registra un'app\n"
            "     (OAuth redirect: http://localhost, categoria: Application Integration)\n"
            "  2. Copia Client ID e genera un Client Secret\n"
            f"  3. Mettili in {env_file} come:\n"
            "       TWITCH_CLIENT_ID=...\n"
            "       TWITCH_CLIENT_SECRET=...\n"
        )
    return cid, sec


# ── client Twitch ────────────────────────────────────────────────────────────

class TwitchClient:
    """Wrapper minimo di Helix. `session` e' un requests.Session (o un finto nei test)."""

    def __init__(self, client_id: str, client_secret: str, session=None):
        if session is None:
            import requests
            session = requests.Session()
        self.s = session
        self.client_id = client_id
        r = self.s.post(TOKEN_URL, params={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }, timeout=30)
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _get(self, path: str, params) -> dict:
        r = self.s.get(f"{HELIX}/{path}", params=params, timeout=30, headers={
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self.token}",
        })
        r.raise_for_status()
        return r.json()

    def game_id(self, name: str = GAME_NAME) -> str:
        data = self._get("games", {"name": name}).get("data", [])
        if not data:
            raise SystemExit(f"Gioco '{name}' non trovato su Twitch.")
        return data[0]["id"]

    def user_ids(self, logins: list[str]) -> dict[str, str]:
        out = {}
        for i in range(0, len(logins), 100):
            chunk = logins[i:i + 100]
            for u in self._get("users", [("login", l) for l in chunk]).get("data", []):
                out[u["login"].lower()] = u["id"]
        return out

    def clips(self, broadcaster_id: str, started_at: datetime, ended_at: datetime,
              first: int = 100) -> list[dict]:
        """Clip del broadcaster nel periodo, ordinate per view_count (ordine di Helix)."""
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        return self._get("clips", {
            "broadcaster_id": broadcaster_id,
            "started_at": started_at.strftime(fmt),
            "ended_at": ended_at.strftime(fmt),
            "first": min(first, 100),
        }).get("data", [])


# ── selezione ────────────────────────────────────────────────────────────────

@dataclass
class Filtri:
    game_id: str
    per_streamer: int = 5
    min_views: int = 0
    min_durata: float = 8.0      # sotto: non c'e' materiale per 3-5s puliti
    max_durata: float = 60.0
    lingue: tuple[str, ...] = ("en",)


def seleziona(clips: Iterable[dict], filtri: Filtri, viste: set[str]) -> list[dict]:
    scelte = [
        c for c in clips
        if c.get("game_id") == filtri.game_id
        and c["id"] not in viste
        and c.get("view_count", 0) >= filtri.min_views
        and filtri.min_durata <= float(c.get("duration", 0)) <= filtri.max_durata
        and (not filtri.lingue or c.get("language") in filtri.lingue)
    ]
    scelte.sort(key=lambda c: c.get("view_count", 0), reverse=True)
    return scelte[:filtri.per_streamer]


# ── stato + download ─────────────────────────────────────────────────────────

def load_seen(path: Path) -> set[str]:
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")))
    return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), indent=1), encoding="utf-8")


def ytdlp_download(url: str, dest: Path) -> None:
    import yt_dlp
    opts = {
        "outtmpl": str(dest),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "overwrites": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


def credito(c: dict) -> str:
    return f"Clip: twitch.tv/{c['broadcaster_name']} — {c['url']}"


def salva_meta(c: dict, path: Path, login: str) -> None:
    meta = {
        "clip_id": c["id"],
        "streamer": c["broadcaster_name"],
        "login": login,
        "titolo": c.get("title", ""),
        "url": c["url"],
        "views": c.get("view_count", 0),
        "durata": c.get("duration"),
        "lingua": c.get("language"),
        "creata": c.get("created_at"),
        "clippata_da": c.get("creator_name"),
        "credito": credito(c),
        "scaricata": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def run(client: TwitchClient, logins: list[str], filtri: Filtri, ore: int,
        base: Path, dry_run: bool = False,
        download: Callable[[str, Path], None] = ytdlp_download,
        now: datetime | None = None) -> list[Path]:
    now = now or datetime.now(timezone.utc)
    inizio = now - timedelta(hours=ore)
    inbox = base / "inbox"
    seen_path = base / "seen_clips.json"
    seen = load_seen(seen_path)

    ids = client.user_ids(logins)
    mancanti = [l for l in logins if l not in ids]
    if mancanti:
        print(f"[!] login non trovati su Twitch: {', '.join(mancanti)}")

    scaricate: list[Path] = []
    for login, uid in ids.items():
        scelte = seleziona(client.clips(uid, inizio, now), filtri, seen)
        print(f"{login}: {len(scelte)} clip nuove")
        for c in scelte:
            stem = f"{login}_{c['id']}"
            print(f"   {c.get('view_count', 0):>7} views  {float(c['duration']):4.0f}s  {c.get('title', '')[:60]}")
            if dry_run:
                continue
            inbox.mkdir(parents=True, exist_ok=True)
            mp4 = inbox / f"{stem}.mp4"
            try:
                download(c["url"], mp4)
            except Exception as e:  # una clip rotta non deve fermare le altre
                print(f"   [x] download fallito {c['id']}: {e}")
                continue
            salva_meta(c, inbox / f"{stem}.json", login)
            seen.add(c["id"])
            save_seen(seen_path, seen)   # salva subito: un crash a meta' non fa riscaricare
            scaricate.append(mp4)
    return scaricate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scarica clip GTA 6 dagli streamer in whitelist.")
    ap.add_argument("--ore", type=int, default=48, help="finestra di ricerca (default 48)")
    ap.add_argument("--per-streamer", type=int, default=5)
    ap.add_argument("--min-views", type=int, default=0)
    ap.add_argument("--lingue", default="en", help="codici separati da virgola; vuoto = tutte")
    ap.add_argument("--gioco", default=GAME_NAME)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    logins = load_whitelist()
    if not logins:
        print(f"Nessuno streamer confermato in {WHITELIST}.\n"
              "Aggiungi le voci e metti 'confermato': true dopo aver verificato la prova del permesso.")
        return 1

    client = TwitchClient(*load_credentials())
    filtri = Filtri(
        game_id=client.game_id(a.gioco),
        per_streamer=a.per_streamer,
        min_views=a.min_views,
        lingue=tuple(x.strip() for x in a.lingue.split(",") if x.strip()),
    )
    base = gta_dir()
    out = run(client, logins, filtri, a.ore, base, dry_run=a.dry_run)
    if not a.dry_run:
        print(f"\n{len(out)} clip scaricate in {base / 'inbox'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
