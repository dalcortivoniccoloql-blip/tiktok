from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

AUDIO_DIR  = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"
BACKGROUNDS_DIR = BASE_DIR / "assets" / "backgrounds"

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

# ── stile caption (testo bianco + bordo nero su video a tutto schermo) ──
CAPTION_FILL    = (255, 255, 255)   # bianco
CAPTION_STROKE  = (0, 0, 0)         # bordo nero
STROKE_WIDTH    = 8                 # spessore bordo
CAPTION_FONT_SIZE = 64
BG_DARKEN       = 0.78              # quanto scurire il video di sfondo (1 = originale)

# Testo intro/outro
INTRO_TEXT_EN = "5 absurd facts that will leave you speechless"
OUTRO_TEXT_EN = "Follow for more absurd facts!"
INTRO_TEXT_IT = "5 curiosita' assurde che ti lasceranno senza parole!"
OUTRO_TEXT_IT = "Seguici per altre curiosita' assurde!"

INTRO_TEXT = INTRO_TEXT_EN if LANGUAGE == "en" else INTRO_TEXT_IT
OUTRO_TEXT = OUTRO_TEXT_EN if LANGUAGE == "en" else OUTRO_TEXT_IT

# Account
USERNAME = "@5absurdfacts"

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
