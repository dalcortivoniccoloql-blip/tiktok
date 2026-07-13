# 5AbsurdFacts Publisher

A private, non-commercial Python pipeline built and used by a single individual
(the developer) to create and publish original short-form videos to the
developer's own YouTube channel:
**[youtube.com/@5AbsurdFacts](https://www.youtube.com/@5AbsurdFacts)**.

It is not a product: it has a single user (the developer), no website, no user
base, and no revenue.

## What it does

1. Reads a short educational script (fun facts / trivia) from a local JSON file
   (`pipeline/english_scripts*.json`).
2. Generates a text-to-speech voiceover (`edge-tts`) and renders a 1080×1920
   vertical video with synchronized captions over background gameplay footage
   (MoviePy + ffmpeg).
3. Uploads the finished video to the developer's own authenticated channel via
   the YouTube Data API v3, up to 3 videos per day (GitHub Actions cron →
   `cloud_publish.py`).

## YouTube API usage

- **Only OAuth scope used:** `https://www.googleapis.com/auth/youtube.upload`
- **Only endpoint called:** `videos.insert` (upload of the developer's own
  content to the developer's own channel)
- No YouTube API data is retrieved, stored, displayed, or shared. The Client
  never accesses third-party data or any other channel.
- OAuth credentials are kept out of the repository (`.gitignore`) and stored
  only on the developer's machine and as encrypted GitHub Actions secrets.

## Privacy policy

See [PRIVACY.md](PRIVACY.md).

## Layout

| Path | Contents |
|---|---|
| `cloud_publish.py` | GitHub Actions runner: renders and publishes the next script |
| `state.json` | Pointer to the next script to publish |
| `pipeline/` | Script loading, TTS, video rendering, YouTube upload |
| `docs/` | Playbook and cloud setup notes (Italian) |
| `assets/backgrounds/` | Background footage used by the renderer |
| `.github/workflows/` | Publishing cron and weekly script top-up |
