"""
Autenticazione YouTube via OAuth Playground.

Step 1 - apri il browser e mostra le istruzioni:
    py pipeline\auth_youtube.py

Step 2 - salva il token dopo averlo copiato dal browser:
    py pipeline\auth_youtube.py --token "1//xxxxx..."
"""

import json
import sys
import webbrowser
import argparse
from pathlib import Path

SECRETS_PATH  = Path(__file__).parent.parent / "client_secrets.json"
YT_TOKEN_PATH = Path(__file__).parent.parent / "yt_token.json"


def load_client_secrets():
    if not SECRETS_PATH.exists():
        print("ERRORE: client_secrets.json non trovato in", SECRETS_PATH.parent)
        sys.exit(1)
    with open(SECRETS_PATH) as f:
        data = json.load(f)
    cfg = data.get("installed") or data.get("web")
    return cfg["client_id"], cfg["client_secret"]


def step1_open_browser():
    client_id, client_secret = load_client_secrets()

    print()
    print("=" * 60)
    print("  STEP 1 — Ottieni il Refresh Token")
    print("=" * 60)
    print()
    print("*** FIX PERMANENTE (fallo UNA volta, evita la scadenza ogni 7 giorni) ***")
    print("Se il consent screen e' in 'Testing', i token scadono dopo 7 giorni.")
    print("Vai su https://console.cloud.google.com/auth/overview e clicca")
    print("'PUBBLICA APP' / 'Pubblica in produzione'. Poi rigenera il token qui sotto.")
    print("-" * 60)
    print()
    print("Si apre OAuth Playground nel browser.")
    print("Fai questi passi:")
    print()
    print("  1. Clicca l'icona INGRANAGGIO in alto a destra")
    print("  2. Spunta 'Use your own OAuth credentials'")
    print("  3. Incolla:")
    print(f"       Client ID:     {client_id}")
    print(f"       Client Secret: {client_secret}")
    print("  4. Chiudi il pannello (clicca fuori)")
    print("  5. A sinistra cerca 'YouTube Data API v3'")
    print("     Spunta: .../auth/youtube.upload")
    print("  6. Clicca 'Authorize APIs' e accedi con Google")
    print("     (se vedi avviso: clicca 'Avanzate' > 'Vai al sito')")
    print("  7. Clicca 'Exchange authorization code for tokens'")
    print("  8. Copia il 'Refresh token'")
    print()
    print("  Poi esegui:")
    print('  py pipeline\\auth_youtube.py --token "INCOLLA_QUI_IL_TOKEN"')
    print()
    print("Apertura browser...")
    webbrowser.open("https://developers.google.com/oauthplayground/")


def step2_save_token(refresh_token: str):
    client_id, client_secret = load_client_secrets()

    print("Verifico il token...")

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials(
        token         = None,
        refresh_token = refresh_token,
        token_uri     = "https://oauth2.googleapis.com/token",
        client_id     = client_id,
        client_secret = client_secret,
        scopes        = ["https://www.googleapis.com/auth/youtube.upload"],
    )

    try:
        creds.refresh(Request())
    except Exception as e:
        print(f"ERRORE: token non valido — {e}")
        print("Riprova step 1 e copia di nuovo il refresh token.")
        sys.exit(1)

    token_data = {
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "access_token":  creds.token,
    }
    with open(YT_TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)

    print()
    print("=" * 60)
    print("  Autenticazione completata! (file locale yt_token.json aggiornato)")
    print("=" * 60)
    print()
    print("!! IMPORTANTE — AGGIORNA ANCHE IL CLOUD !!")
    print("Il cloud (GitHub Actions) NON usa il file locale ma il secret 'YT_TOKEN'.")
    print("Se non lo aggiorni, gli Short continueranno a NON pubblicarsi.")
    print()
    print("1. Vai su: https://github.com/NdC171/tiktok/settings/secrets/actions")
    print("2. Apri 'YT_TOKEN' > Update secret")
    print("3. Incolla ESATTAMENTE questa riga come valore:")
    print()
    print("   " + json.dumps(token_data))
    print()
    print("Uso locale (facoltativo):")
    print("  py pipeline\\main.py --count 5 --upload-youtube --publish-now")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", type=str, default=None,
                        help="Refresh token copiato da OAuth Playground")
    args = parser.parse_args()

    if args.token:
        step2_save_token(args.token.strip())
    else:
        step1_open_browser()
