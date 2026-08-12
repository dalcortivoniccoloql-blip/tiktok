# Durata: LEGATO-A:P09
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# Override locali via env: gli asset pesanti (sfondi) e i render di prova stanno
# FUORI dal Drive condiviso (vedi import-nota.md). Senza env valgono i default
# del repo (es. GitHub Actions, dove lo sfondo e' committato).
AUDIO_DIR  = BASE_DIR / "audio"
OUTPUT_DIR = Path(os.environ.get("FS_OUTPUT_DIR", str(BASE_DIR / "output")))
BACKGROUNDS_DIR = Path(os.environ.get("FS_BACKGROUNDS_DIR", str(BASE_DIR / "assets" / "backgrounds")))

# Sorgente contenuti
ENGLISH_SCRIPTS = Path(__file__).parent / "english_scripts.json"
SCRIPTS_DOCX = [
    BASE_DIR / "archive" / "legacy_it" / "00_curiosita_tiktok_reali.docx",
    BASE_DIR / "archive" / "legacy_it" / "Curiosita_Virali_TikTok_100_Script.docx",
]

# Lingua: "en" usa english_scripts.json, "it" usa i docx
LANGUAGE = "en"

# Video
WIDTH  = 1080
HEIGHT = 1920
FPS    = 30

# TTS voices
VOICE_EN = "en-US-AvaNeural"       # inglese, naturale ed energica
VOICE_IT = "it-IT-ElsaNeural"      # italiano
DEFAULT_VOICE = VOICE_EN if LANGUAGE == "en" else VOICE_IT
VOICE_RATE = "+8%"                 # leggermente piu' veloce: ritmo da Short (formato edge-tts "+N%" / "-N%")

# ── stile caption (testo bianco + bordo nero su video a tutto schermo) ──
CAPTION_FILL    = (255, 255, 255)   # bianco
CAPTION_STROKE  = (0, 0, 0)         # bordo nero
STROKE_WIDTH    = 8                 # spessore bordo
CAPTION_FONT_SIZE = 64              # usato nel fallback "fatto intero" (senza sidecar tempi)
BG_DARKEN       = 0.78              # quanto scurire il video di sfondo (1 = originale)

# ── sottotitoli sincronizzati v2 (stile Shorts moderno) ──
# La voce genera un sidecar `<n>.timings.json` coi tempi parola-per-parola:
# il video mostra chunk brevi che seguono ESATTAMENTE il parlato.
CAPTION_MODE            = "chunks"  # "chunks" = 2-4 parole per volta | "fact" = fatto intero sincronizzato
CAPTION_CHUNK_WORDS     = 3         # parole per chunk
CAPTION_CHUNK_FONT_SIZE = 88        # font piu' grande: i chunk brevi devono riempire lo schermo
CAPTION_UPPERCASE       = True      # TUTTO MAIUSCOLO (standard dei faceless Shorts ad alta retention)

# Testo intro/outro
# Intro = hook con open loop ("the last one"): promette un payoff alla fine -> watch-through.
# Outro corto: meno coda = loop del video piu' pulito (gli Short ripartono da capo).
INTRO_TEXT_EN = "5 absurd facts. You won't believe the last one!"
OUTRO_TEXT_EN = "Follow for more!"
INTRO_TEXT_IT = "5 curiosita' assurde. L'ultima ti lascera' senza parole!"
OUTRO_TEXT_IT = "Seguici per altre!"

INTRO_TEXT = INTRO_TEXT_EN if LANGUAGE == "en" else INTRO_TEXT_IT
OUTRO_TEXT = OUTRO_TEXT_EN if LANGUAGE == "en" else OUTRO_TEXT_IT

# Account
# Handle REALE del canale: `@5AbsurdFacts-ql`. Cambiato dall'owner il 2026-08-12
# (prima era `-n5g`, prima ancora si scriveva `@5absurdfacts` nudo). Verificato lo
# stesso giorno leggendo la pagina: `-ql` risolve a UC98nOdXD_giA-xqs5CuBBLA, cioe'
# il canale di EXPECTED_CHANNEL_ID in upload_youtube.py (l'ID NON cambia quando
# cambia l'handle: la guardia anti-canale-sbagliato resta valida).
# Anche `-n5g` oggi rimanda ancora li', ma YouTube puo' liberare un handle dismesso
# in qualsiasi momento -> vale solo quello nuovo.
# ⚠️ `@5absurdfacts` nudo e' un ALTRO canale reale (UC_iHL7XJY4Wnes8BFycPuCQ,
# vuoto): non usarlo mai, YouTube auto-linka le menzioni @handle in descrizione.
# Questa costante finisce (a) impressa nel frame del video, in basso al centro
# (generate_video.py) e (b) in descrizione YouTube / caption IG ("Follow {USERNAME}").
USERNAME = "@5AbsurdFacts-ql"

# ── Attribuzione CC-BY degli sfondi (OBBLIGATORIA) ──
# I clip di sfondo sono CC-BY (vedi docs/SFONDI-DIRITTI.md): la licenza richiede
# il CREDITO autore nella descrizione/caption di OGNI video pubblicato.
# Riga combinata (attribuisce tutte le fonti in uso: sempre corretta).
# NB: DEVE restare allineata alla tabella provenienza di docs/SFONDI-DIRITTI.md
# e alla stessa costante nel canale story-shorts (stessi clip condivisi).
BG_CREDIT_LINE = (
    "Background gameplay (CC BY 3.0): Minecraft parkour by "
    '"Orbital - No Copyright Gameplay" (youtu.be/-lVgihPljuI, youtu.be/FXiYiLA1RR8) '
    'and "GameplaysForFree" (youtu.be/XBIaqOm0RKQ). '
    "License: https://creativecommons.org/licenses/by/3.0/"
)

# ── Instagram Reels (upload_instagram.py — setup in docs/SETUP_INSTAGRAM.md) ──
# Credenziali SOLO via env: IG_USER_ID, IG_ACCESS_TOKEN (+ TRANSFER_REPO/TRANSFER_TOKEN
# per l'hosting temporaneo del video). Mai credenziali in questo file / su Drive.
IG_GRAPH_HOST     = "https://graph.instagram.com"  # API "Instagram Login" (niente pagina Facebook)
IG_API_VERSION    = "v23.0"
IG_POLL_EVERY_S   = 5     # ogni quanti secondi controllare l'elaborazione del container
IG_POLL_TIMEOUT_S = 300   # attesa massima elaborazione lato Meta
IG_HASHTAGS = "#reels #facts #didyouknow #amazingfacts #funfacts"

# Quanti post al giorno e a che ora pubblicarli (orari UTC).
# 07/12/17 UTC = circa 09/14/19 ora italiana (estate).
POSTS_PER_DAY  = 3
POST_TIMES_UTC = [7, 12, 17]

# (legacy) giorni tra un post e il successivo, non piu' usato in modalita' 3/giorno
POST_INTERVAL_DAYS = 3

# ── legacy (non piu' usati con lo stile caption, mantenuti per compatibilita') ──
BG_TOP    = (10,  5,  25)
BG_BOTTOM = (40, 10,  60)
ACCENT    = (170, 90, 255)
TEXT      = (240, 240, 255)
DIM       = (100, 100, 130)
CARD_BG   = (55,  15,  85)
