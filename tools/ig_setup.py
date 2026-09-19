# Durata: LEGATO-A:P09
"""
Collega (o ricollega) Instagram alla pipeline senza che il token passi dalla chat.

Da lanciare A MANO, dalla root del repo, in una finestra PowerShell:

    py -3 tools/ig_setup.py --script 206 --video C:\\percorso\\video.mp4
    py -3 tools/ig_setup.py --solo-secret     # rinnovo token (ogni ~60 giorni), senza Reel di prova

Cosa fa, in ordine (si ferma al primo problema):
  1. chiede il token Instagram in modo nascosto (non compare a schermo);
  2. GET /me -> stampa user_id, username, account_type e controlla che l'account
     sia BUSINESS e che lo username coincida con IG_USERNAME di config.py;
  3. pubblica 1 Reel di prova (hosting temporaneo sul repo di transito: se
     TRANSFER_TOKEN non e' gia' nell'env lo prende dal login `gh` di NdC171);
  4. SOLO dopo conferma esplicita [s/N] scrive i secret IG_USER_ID e
     IG_ACCESS_TOKEN sul repo GitHub. Da quel momento il cron pubblica anche su IG.

Il token non viene mai stampato ne' salvato su file. Setup completo della
parte Meta (app, tester, permessi): docs/SETUP_INSTAGRAM.md.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "dalcortivoniccoloql-blip/tiktok"
TRANSFER_REPO_DEFAULT = "NdC171/shorts-transfer"
TRANSFER_GH_USER = "NdC171"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))


def _me(token: str) -> dict:
    """Chi e' il proprietario del token. Gli errori non riportano mai l'URL
    (che contiene il token)."""
    from config import IG_API_VERSION, IG_GRAPH_HOST
    url = (f"{IG_GRAPH_HOST}/{IG_API_VERSION}/me"
           f"?fields=user_id,username,account_type&access_token={token}")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise SystemExit(f"STOP: token rifiutato da Instagram (HTTP {e.code}) {msg}")
    except Exception as e:
        raise SystemExit(f"STOP: Instagram non raggiungibile ({type(e).__name__})")


def _from_clipboard() -> str:
    """Token dagli appunti di Windows, senza mai stamparlo."""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                       capture_output=True, text=True)
    return "".join(r.stdout.split())   # via spazi/a-capo finiti nella copia


def _gh_secret(name: str, value: str) -> None:
    r = subprocess.run(["gh", "secret", "set", name, "--repo", REPO],
                       input=value, text=True, capture_output=True)
    if r.returncode:
        raise SystemExit(f"STOP: gh secret set {name} fallito: {r.stderr.strip()}")
    print(f"    secret {name} impostato su {REPO}")


def _publish_test(script_n: int, video: Path) -> None:
    os.environ.setdefault("TRANSFER_REPO", TRANSFER_REPO_DEFAULT)
    if not os.environ.get("TRANSFER_TOKEN"):
        r = subprocess.run(["gh", "auth", "token", "--user", TRANSFER_GH_USER],
                           capture_output=True, text=True)
        if r.returncode or not r.stdout.strip():
            raise SystemExit(f"STOP: nessun login gh per {TRANSFER_GH_USER} "
                             "(serve per il repo di transito)")
        os.environ["TRANSFER_TOKEN"] = r.stdout.strip()

    # import DOPO aver impostato l'env: questi moduli leggono le credenziali all'import
    from extract_scripts import load_scripts
    from upload_instagram import upload_script_reel

    script = next((s for s in load_scripts() if s["number"] == script_n), None)
    if script is None:
        raise SystemExit(f"STOP: script #{script_n} non trovato")
    if not video.is_file() or video.stat().st_size < 100_000:
        raise SystemExit(f"STOP: video mancante o vuoto: {video}")

    print(f"\n[3/4] Reel di prova: script #{script_n}, {video.name}")
    if not upload_script_reel(script, video):
        raise SystemExit("STOP: Reel non pubblicato (vedi messaggio sopra)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--script", type=int, help="numero script per la caption del Reel di prova")
    ap.add_argument("--video", type=str, help="video gia' renderizzato per il Reel di prova")
    ap.add_argument("--solo-secret", action="store_true",
                    help="niente Reel di prova: verifica il token e aggiorna i secret")
    args = ap.parse_args()
    if not args.solo_secret and not (args.script and args.video):
        ap.error("servono --script e --video (oppure --solo-secret)")

    print("[1/4] Copia il token da Meta (\"Genera token\"), poi premi SOLO Invio qui:\n"
          "      lo leggo dagli appunti. (In alternativa incollalo: non si vede, e' normale.)")
    token = getpass.getpass("      > ").strip() or _from_clipboard()
    if not token:
        raise SystemExit("STOP: nessun token (appunti vuoti?)")
    print(f"      token letto: {len(token)} caratteri"
          f"{'' if token.startswith('IG') else ' - ATTENZIONE: non inizia con IG, e dagli appunti?'}")

    info = _me(token)
    print(f"\n[2/4] Account del token: username={info.get('username')} "
          f"user_id={info.get('user_id')} account_type={info.get('account_type')}")

    from config import IG_USERNAME
    if info.get("account_type") != "BUSINESS":
        raise SystemExit("STOP: l'account non e' Business -> l'API non puo' pubblicare")
    if f"@{info.get('username')}" != IG_USERNAME:
        raise SystemExit(f"STOP: il token e' di @{info.get('username')}, "
                         f"ma config.py dice IG_USERNAME={IG_USERNAME}")
    print(f"    ok: coincide con IG_USERNAME ({IG_USERNAME}) ed e' Business")

    os.environ["IG_USER_ID"] = str(info["user_id"])
    os.environ["IG_ACCESS_TOKEN"] = token

    if not args.solo_secret:
        _publish_test(args.script, Path(args.video))
        print(f"    controlla il profilo: https://www.instagram.com/{info['username']}/")

    ans = input("\n[4/4] Scrivo i secret IG_USER_ID e IG_ACCESS_TOKEN su GitHub?\n"
                "      Da quel momento OGNI run del cron pubblica anche su Instagram. [s/N] ")
    if ans.strip().lower() not in ("s", "si", "sì", "y", "yes"):
        print("Secret NON impostati. Rilancia quando vuoi.")
        return
    _gh_secret("IG_USER_ID", str(info["user_id"]))
    _gh_secret("IG_ACCESS_TOKEN", token)
    print("\nFatto. Il token scade tra ~60 giorni. Per rinnovarlo: Meta for Developers ->\n"
          "  app -> API setup con Instagram Login -> Genera token -> copia ->\n"
          "  py -3 tools/ig_setup.py --solo-secret   (premi solo Invio: legge dagli appunti)")


if __name__ == "__main__":
    main()
