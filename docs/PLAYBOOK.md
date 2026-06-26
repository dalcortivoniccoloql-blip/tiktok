# Playbook — Faceless Shorts Factory (automazione completa)

Guida completa e riutilizzabile per costruire un canale **faceless** che genera e
pubblica **Short verticali in automatico** (YouTube Shorts, replicabile su TikTok/Reels).

Questo documento ripercorre tutto ciò che è stato fatto per il canale `@5absurdfacts`,
con problemi incontrati e soluzioni, così da poterlo riapplicare ad altri progetti.

---

## 1. Il concetto

Un "faceless content channel" pubblica video senza volto né voce reale:
- **Contenuto**: testo (es. 5 curiosità) → voce sintetica (TTS) → video verticale
- **Stile retention**: gameplay di sottofondo (Minecraft parkour) + sottotitoli centrati
- **Volume**: tanti video, pubblicati con costanza (qui 3/giorno)
- **Automazione**: la macchina genera e pubblica da sola, anche a PC spento (cloud)

### Modello di monetizzazione (idee)
- YouTube Shorts / Creativity Program (richiede soglie di iscritti/views)
- Cross-posting dello stesso video su TikTok + Instagram Reels (3-4× le entrate)
- Affiliate link in bio, ebook, vendita del canale a maturità
- Multi-nicchia: stesso sistema clonato (psychology facts, money facts, ecc.)

---

## 2. Architettura finale

```
Script (JSON)  ──►  TTS (edge-tts)  ──►  Video (MoviePy + PIL)  ──►  Upload (YouTube API)
   contenuto         voce inglese         Minecraft + caption          come Short
                                                                            │
        GitHub Actions (cron 3×/giorno)  ───────────────────────────────────┘
        + auto-generazione contenuti (Claude API, opzionale)
```

### Stack tecnico
| Componente | Tecnologia | Costo |
|---|---|---|
| Generazione voce | `edge-tts` (Microsoft) | Gratis |
| Montaggio video | `moviepy` 2.x + `Pillow` + `numpy` | Gratis |
| Sfondo gameplay | `yt-dlp` (download no-copyright) | Gratis |
| Upload | YouTube Data API v3 | Gratis (quota 10k/giorno) |
| Hosting automazione | GitHub Actions | Gratis (repo privato, 2000 min/mese) |
| Auto-contenuti | Claude API (`claude-sonnet-4-6`) | ~1$/mese (opzionale) |

---

## 3. Struttura dei file

```
progetto/
├── pipeline/                  # tutto il codice
│   ├── config.py              # impostazioni centrali (lingua, voce, colori, orari)
│   ├── english_scripts.json   # contenuti batch 1
│   ├── english_scripts_2.json # contenuti batch 2 (estendibile: _3, _4, ...)
│   ├── english_scripts_3.json # contenuti batch 3
│   ├── extract_scripts.py     # carica e unisce/rinumera tutti gli script
│   ├── generate_audio.py      # testo → mp3 (TTS)
│   ├── generate_video.py      # mp3 + sfondo → mp4 1080×1920 con sottotitoli
│   ├── upload_youtube.py      # upload + metadati (#Shorts) + auth
│   ├── auth_youtube.py        # wizard una-tantum per il token OAuth
│   ├── generate_scripts.py    # auto-generazione nuovi contenuti (Claude API)
│   └── main.py                # orchestratore CLI (uso locale)
├── docs/                      # documentazione
│   ├── PLAYBOOK.md            # questo file
│   └── SETUP_CLOUD.md         # istruzioni utente per il setup cloud
├── assets/
│   └── backgrounds/
│       └── minecraft_parkour.mp4   # video di sfondo in loop (committato)
├── local/                     # automazione PC locale (alternativa al cloud)
│   ├── auto_run.bat           # script eseguito dal Task Scheduler
│   ├── setup_scheduler.ps1    # registra il task Windows (da admin)
│   └── setup.bat              # installa le dipendenze
├── archive/                   # materiale legacy (gitignored)
│   └── legacy_it/             # vecchi contenuti italiani (docx) + note txt
├── output/                    # video generati (gitignored, rigenerati al volo)
├── audio/                     # mp3 generati (gitignored)
├── logs/                      # log delle run locali (gitignored)
├── cloud_publish.py           # runner per il cloud (pubblica 1, avanza stato)
├── state.json                 # {"next": N} = prossimo script da pubblicare
├── .github/workflows/
│   ├── publish.yml            # cron 3×/giorno → pubblica
│   └── topup.yml              # settimanale → genera nuovi contenuti
├── .gitignore                 # esclude segreti e file grandi
├── requirements.txt
└── yt_token.json / client_secrets.json   # segreti (gitignored)
```

---

## 4. I tre livelli di automazione (dal meno al più automatico)

| Modalità | Automatico | PC | Setup |
|---|---|---|---|
| **Manuale** | No, lanci tu un comando | Spento tra una volta e l'altra | Già pronto |
| **Task Scheduler locale** | Sì | Acceso o in sospensione (WakeToRun) | `local/setup_scheduler.ps1` |
| **Cloud (GitHub Actions)** | Sì | Totalmente spento | `docs/SETUP_CLOUD.md` |

> **Vincolo chiave**: la quota YouTube è ~6 upload/giorno. Quindi 3/giorno è sicuro.
> Non si possono pre-caricare settimane in un colpo solo senza aumento di quota.

---

## 5. Setup passo-passo (replicabile)

### 5.1 — Ambiente Python
```
py -m pip install python-docx edge-tts moviepy pillow numpy ^
  google-api-python-client google-auth-oauthlib google-auth-httplib2 yt-dlp
```
> Su Windows usare `py`, non `python` (spesso `python` apre lo Store).

### 5.2 — Procurarsi il video di sfondo
```
py -m yt_dlp "VIDEO_ID" -f 298 --download-sections "*0:00-3:00" ^
  --ffmpeg-location <cartella_ffmpeg> -o "assets/backgrounds/minecraft_parkour.%(ext)s"
```
- Cercare "minecraft parkour no copyright vertical" (formato 9:16, 720p+)
- ffmpeg è incluso in moviepy: trovarlo con
  `py -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"`
- yt-dlp cerca `ffmpeg.exe`: copiare il binario con quel nome esatto in una cartella

### 5.3 — Credenziali YouTube (la parte più delicata)
1. [console.cloud.google.com](https://console.cloud.google.com) → nuovo progetto
2. **API e servizi → Libreria** → abilita **YouTube Data API v3**
3. **Credenziali → Crea credenziali → ID client OAuth → Applicazione WEB**
   (⚠️ NON "Desktop": il tipo Web serve per OAuth Playground)
4. In **URI di reindirizzamento autorizzati** aggiungere:
   `https://developers.google.com/oauthplayground`
5. Scaricare il JSON → rinominarlo `client_secrets.json` nella cartella progetto
6. Ottenere il refresh token via OAuth Playground (vedi 5.4)

### 5.4 — Refresh token (OAuth Playground)
1. `py pipeline/auth_youtube.py` (apre il browser e mostra Client ID/Secret)
2. Su OAuth Playground: ingranaggio → "Use your own OAuth credentials" → incollare ID/Secret
3. Selezionare scope **YouTube Data API v3 → .../auth/youtube.upload**
4. "Authorize APIs" → login Google → "Exchange authorization code for tokens"
5. Copiare il **Refresh token** e salvarlo:
   `py pipeline/auth_youtube.py --token "1//xxxx..."`
6. Crea `yt_token.json` con client_id, client_secret, refresh_token, access_token

### 5.5 — Test locale
```
py pipeline/main.py --list                              # stato contenuti
py pipeline/main.py --script 1 --count 1 --upload-youtube --publish-now
```

### 5.6 — Cloud (GitHub Actions) → vedi docs/SETUP_CLOUD.md
1. GitHub Desktop → Add Existing Repository → Create → Publish (privato)
2. Settings → Secrets and variables → Actions → New secret:
   - `YT_TOKEN` = contenuto di `yt_token.json`
   - (opz.) `ANTHROPIC_API_KEY` = chiave Claude per auto-contenuti
3. Scheda **Actions** → abilita → Run workflow (test)

---

## 6. Problemi incontrati e soluzioni (lezioni apprese)

| Problema | Causa | Soluzione |
|---|---|---|
| `python` non trovato | Alias Windows Store | Usare `py` |
| `pip` non trovato | Non nel PATH | Usare `py -m pip` |
| `No module named moviepy.editor` | MoviePy 2.x ha cambiato API | `from moviepy import ...` |
| `set_fps` non esiste | MoviePy 2.x | Usare `with_fps`, `with_audio` |
| `UnicodeEncodeError` in console | cp1252 non stampa emoji/✓ | Usare ASCII nei print; gli emoji nei dati restano validi (UTF-8) |
| Doppia estensione `.json.json` | Windows nasconde le estensioni | Rinominare il file |
| `Access blocked: app invalid` | App non verificata + scope sensibile | Usare OAuth Playground invece del consent screen |
| `redirect_uri_mismatch` | Client di tipo Desktop | Creare client **Web** con redirect Playground |
| `insufficient authentication scopes` | Test su scope sbagliato | Usare solo `youtube.upload`, non leggere il canale |
| Audio non corrisponde ai sottotitoli | Riuso di vecchi mp3 con contenuti diversi | Rigenerare SEMPRE l'audio dai JSON correnti (`--audio-only --overwrite`) |
| Font assenti su Linux (cloud) | Path font Windows hardcoded | Aggiungere fallback DejaVu/Liberation per Linux |
| Stato perso tra run cloud | Niente disco persistente | `state.json` committato di nuovo dopo ogni run |
| File segreti su GitHub | — | `.gitignore` esclude `yt_token.json`, `client_secrets*.json` |

---

## 7. Dettagli che fanno la differenza

### Classificazione come Short (non video normale)
YouTube classifica come Short in automatico se il video è:
- **Verticale** (1080×1920 / 9:16)
- **≤ 60 secondi**
- Con **`#Shorts`** nel titolo o descrizione

Non esiste un endpoint API separato: è un upload normale che rispetta questi criteri.

### Stile video (retention)
- Sfondo gameplay a **tutto schermo**, leggermente scurito (`BG_DARKEN ≈ 0.78`)
- Sottotitolo **bianco con bordo nero** (`stroke_width`), **centrato** verticalmente
- Caption sincronizzata: intro 2.8s, fatti distribuiti, outro 2.2s
- Username in basso per il branding

### Scheduling 3/giorno
- `publishAt` permette di programmare: il PC serve solo all'upload, non alla pubblicazione
- Orari: 07/12/17 UTC = 09/14/19 ora italiana (estate, UTC+2)
- In cloud: 3 cron separati, ognuno pubblica immediatamente (l'ora del cron = ora del post)

### Contenuti estendibili e perpetui
- Più file `english_scripts*.json` uniti e rinumerati in automatico
- `generate_scripts.py` + Claude API generano nuovi script quando ne restano pochi
- Dedup dei fatti per evitare ripetizioni

---

## 8. Comandi di riferimento

```bash
# Stato di tutti gli script (audio/video presenti)
py pipeline/main.py --list

# Genera+pubblica subito N short
py pipeline/main.py --script 17 --count 6 --upload-youtube --publish-now

# Programma N short a 3/giorno (PC poi spegnibile)
py pipeline/main.py --script 17 --count 6 --upload-youtube

# Solo video / solo audio
py pipeline/main.py --script 17 --count 3 --video-only --overwrite
py pipeline/main.py --script 17 --count 3 --audio-only --overwrite

# Auto-generazione contenuti (richiede ANTHROPIC_API_KEY)
py pipeline/generate_scripts.py --force

# Cloud: pubblica 1 e avanza stato (lo fa il workflow)
python cloud_publish.py
```

---

## 9. Come replicare per un NUOVO progetto/nicchia

1. **Copia la cartella** e cambia in `config.py`:
   - `USERNAME`, `INTRO_TEXT`, `OUTRO_TEXT`
   - voce TTS (`VOICE_EN` / `VOICE_IT` / altre lingue)
   - orari di pubblicazione
2. **Sostituisci i contenuti**: nuovi `english_scripts*.json` per la nuova nicchia
   (es. psychology facts, money facts, history facts)
3. **Cambia lo sfondo**: nuovo video in `assets/backgrounds/`
4. **Nuove credenziali YouTube** per il nuovo canale (ripeti 5.3–5.4)
5. **Nuovo repo GitHub** con i suoi secret
6. Il resto della pipeline funziona identico

> Lo stesso sistema può alimentare più canali in parallelo: ogni nicchia cresce
> separatamente e può vendere prodotti diversi.

---

## 10. Cross-posting (moltiplicare le entrate)

Lo stesso `.mp4` generato può essere caricato anche su:
- **TikTok**: via tool di scheduling con API (Publer, Buffer) per non violare i ToS
- **Instagram Reels**: Meta Content Publishing API (richiede account Business)
- **Facebook Reels**

Stesso contenuto, più piattaforme = più monetizzazione a parità di lavoro.

---

## Riepilogo finale

Un sistema che, una volta configurato:
- genera video professionali in stile virale **da solo**
- li pubblica **3 volte al giorno** come Short
- **a PC spento** (gira su GitHub Actions)
- e può **generare nuovi contenuti all'infinito** (con Claude API)

Costo: **~0€** (gratis tutto; ~1$/mese solo se attivi l'auto-generazione).
