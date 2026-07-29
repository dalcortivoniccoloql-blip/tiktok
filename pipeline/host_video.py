# Durata: LEGATO-A:P09
"""
Hosting temporaneo del video a un URL pubblico.

Serve per Instagram: l'API di Meta NON accetta l'upload diretto del file,
scarica lei il video da un URL pubblico (`video_url` del container).
Qui usiamo una Release su un repo GitHub PUBBLICO "di transito":
carica asset -> ottieni URL pubblico -> (dopo la pubblicazione) cancella tutto.

Config via variabili d'ambiente (vedi docs/SETUP_INSTAGRAM.md):
  TRANSFER_REPO   es. "utente/shorts-transfer" (repo PUBBLICO, puo' essere vuoto)
  TRANSFER_TOKEN  PAT fine-grained limitato a quel repo (Contents: Read and write)

Nessuna dipendenza esterna: solo urllib della standard library.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_API = "https://api.github.com"
UPLOADS_API = "https://uploads.github.com"

TRANSFER_REPO = os.environ.get("TRANSFER_REPO", "")
TRANSFER_TOKEN = os.environ.get("TRANSFER_TOKEN", "")


def hosting_configured() -> bool:
    return bool(TRANSFER_REPO and TRANSFER_TOKEN)


def _gh(method: str, url: str, data: bytes | None = None,
        content_type: str = "application/json") -> dict:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TRANSFER_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("message", "")
        except Exception:
            err = ""
        raise RuntimeError(f"GitHub API {e.code} su {url}: {err}") from None


def host_on_github(video_path: Path, tag: str) -> tuple[str, int]:
    """Carica il video come asset di una release sul repo di transito.

    Ritorna (url_pubblico_diretto, release_id). Il chiamante DEVE poi
    chiamare delete_release() per ripulire (il transito non e' un archivio).
    """
    if not hosting_configured():
        raise RuntimeError("TRANSFER_REPO / TRANSFER_TOKEN non configurati")

    rel = _gh("POST", f"{GITHUB_API}/repos/{TRANSFER_REPO}/releases",
              json.dumps({
                  "tag_name": tag,
                  "name": f"transito {tag}",
                  "body": "File di transito per la pubblicazione Instagram. Auto-cancellato.",
                  "make_latest": "false",
              }).encode())
    release_id = rel["id"]

    name = video_path.name.replace(" ", "_")
    asset = _gh("POST",
                f"{UPLOADS_API}/repos/{TRANSFER_REPO}/releases/{release_id}/assets?name={name}",
                video_path.read_bytes(), content_type="video/mp4")
    url = asset["browser_download_url"]
    print(f"    Video in transito su: {url}")
    return url, release_id


def delete_release(release_id: int, tag: str) -> None:
    """Cancella release + tag di transito (best-effort: non deve mai far fallire il run)."""
    try:
        _gh("DELETE", f"{GITHUB_API}/repos/{TRANSFER_REPO}/releases/{release_id}")
        _gh("DELETE", f"{GITHUB_API}/repos/{TRANSFER_REPO}/git/refs/tags/{tag}")
        print("    Transito ripulito (release + tag cancellati)")
    except Exception as e:  # noqa: BLE001
        print(f"    Nota: pulizia transito non riuscita ({e}) - cancellare a mano dal repo")
