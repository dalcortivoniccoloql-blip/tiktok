"""Format QUIZ (fase 1 del piano "nuovi format", 2026-11-13).

Tre tipi di video, 3 domande ciascuno (facile -> media -> difficile):
  - "flag"    : di che paese e' questa bandiera? (4 opzioni)
  - "capital" : qual e' la capitale di X?        (4 opzioni)
  - "bigger"  : quale dei due paesi e' piu' grande? (2 bandiere)

Tutto e' generato da dati versionati nel repo (pipeline/formats/data/countries.json,
assets/flags/*.png): a pubblicazione NON si scarica niente.
La coda si pre-genera in pipeline/queues/quiz.json (rivedibile come gli script):
    py pipeline/formats/quiz.py build            # (ri)genera la coda
    py pipeline/formats/quiz.py render 1 2 3     # render locali di prova in output/quiz/

Regole di design (dai dati Studio del canale): niente intro, la domanda e l'immagine
sono a schermo dal frame 0; ~20-25 s; branding neutro (niente "absurd facts").
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

PIPE = Path(__file__).resolve().parent.parent
BASE = PIPE.parent
sys.path.insert(0, str(PIPE))

from config import WIDTH, HEIGHT, FPS, AUDIO_DIR, OUTPUT_DIR  # noqa: E402

DATA_P   = Path(__file__).parent / "data" / "countries.json"
FLAGS    = BASE / "assets" / "flags"
QUEUE_P  = PIPE / "queues" / "quiz.json"

VOICE        = "en-US-AndrewMultilingualNeural"  # voce diversa dagli absurd facts (Ava)
KINDS        = ["flag", "capital", "bigger"]
COUNTDOWN_S  = 3.0
NO_REPEAT_VIDEOS = 15                 # un paese non torna come risposta prima di 15 quiz
SEED         = 20261113

# Capitali contese o con doppia capitale: niente domanda (un canale di trivia neutro
# non deve "decidere" Gerusalemme, e Sucre/La Paz o Kotte/Colombo genera commenti "sbagliato").
NO_CAPITAL_Q = {"il", "bo", "lk", "ci", "bj", "my"}

# Bandiere quasi identiche: mai insieme tra le opzioni della stessa domanda.
CONFUSABLE = [{"au", "nz"}, {"nl", "lu"}, {"td", "ro"}, {"id", "mc"}, {"id", "pl"}, {"mc", "pl"},
              {"co", "ec"}, {"ie", "ci"}, {"sn", "ml"}, {"gn", "ml"}, {"si", "sk"}, {"sk", "ru"}, {"si", "ru"}]


def _confusable(a: str, b: str) -> bool:
    return {a, b} in CONFUSABLE

HEADERS = {"flag": "GUESS THE FLAG", "capital": "GUESS THE CAPITAL", "bigger": "WHICH IS BIGGER?"}
GRADIENTS = {  # (alto, basso) per tipo: ogni tipo si riconosce dal primo frame
    "flag":    ((37, 99, 235), (15, 23, 42)),
    "capital": ((13, 148, 136), (8, 30, 40)),
    "bigger":  ((234, 88, 12), (60, 10, 30)),
}
GREEN = (22, 163, 74)
WHITE = (255, 255, 255)
INK   = (17, 24, 39)

TITLES = {
    "flag":    ["Can you guess all 3 flags?", "Guess the flag in 3 seconds", "Only flag experts get all 3"],
    "capital": ["Can you name these 3 capitals?", "Guess the capital in 3 seconds", "Most people miss the last capital"],
    "bigger":  ["Which country is bigger?", "Guess the bigger country", "The last one surprises everyone"],
}


# ── numeri a parole (il TTS legge meglio "twenty" che "20") ───────────────────

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def num_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else "-" + _ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + ("" if not rest else " and " + num_words(rest))
    return str(n)


# ── dati ───────────────────────────────────────────────────────────────────────

def load_countries() -> list[dict]:
    cs = json.loads(DATA_P.read_text(encoding="utf-8"))
    cs = [c for c in cs if c["population"] and (FLAGS / f"{c['cca2']}.png").exists()]
    for c in cs:
        if c["cca2"] in NO_CAPITAL_Q:
            c["capital"] = None
    # difficolta' = notorieta' approssimata dalla popolazione
    ranked = sorted(cs, key=lambda c: -c["population"])
    for i, c in enumerate(ranked):
        c["tier"] = 0 if i < 50 else (1 if i < 110 else 2)
    return cs


def _pick_options(rng, answer, pool, n, key):
    """n-1 distrattori: stessa regione se possibile, mai doppioni di testo."""
    ok = [c for c in pool if c is not answer and c[key] and not _confusable(c["cca2"], answer["cca2"])]
    same = [c for c in ok if c["region"] == answer["region"]]
    other = list(ok)
    rng.shuffle(same)
    rng.shuffle(other)
    picked, seen, codes = [], {answer[key]}, [answer["cca2"]]
    for c in same + other:
        if c[key] not in seen and not any(_confusable(c["cca2"], x) for x in codes):
            picked.append(c[key])
            seen.add(c[key])
            codes.append(c["cca2"])
        if len(picked) == n - 1:
            break
    opts = picked + [answer[key]]
    rng.shuffle(opts)
    return opts, opts.index(answer[key])


def _q_flag(rng, cs, tier, used, i):
    cand = [c for c in cs if c["tier"] == tier and c["cca2"] not in used]
    a = rng.choice(cand)
    opts, ans = _pick_options(rng, a, cs, 4, "name")
    say_q = ["Can you name all three flags? First one.", "Second flag.", "Last one. This one is hard."][i]
    return {"show": [a["cca2"]], "options": opts, "answer": ans,
            "say_q": say_q, "say_a": f"It's {a['name']}!"}, [a["cca2"]]


def _q_capital(rng, cs, tier, used, i):
    cand = [c for c in cs if c["tier"] == tier and c["capital"] and c["cca2"] not in used]
    a = rng.choice(cand)
    opts, ans = _pick_options(rng, a, cs, 4, "capital")
    say_q = [f"Name all three capitals. What's the capital of {a['name']}?",
             f"The capital of {a['name']}?",
             f"Last one. The capital of {a['name']}?"][i]
    return {"show": [a["cca2"]], "country": a["name"], "options": opts, "answer": ans,
            "say_q": say_q, "say_a": f"{a['capital']}!"}, [a["cca2"]]


def _q_bigger(rng, cs, tier, used, i):
    # minimo 6%: sotto, la risposta dipende dalla fonte (acque interne, territori contesi)
    lo, hi = [(1.4, 3.0), (1.12, 1.4), (1.06, 1.2)][i]
    pool = [c for c in cs if c["tier"] <= max(tier, 1) and c["area_km2"] and c["cca2"] not in used]
    for _ in range(4000):
        a, b = rng.sample(pool, 2)
        big, small = (a, b) if a["area_km2"] >= b["area_km2"] else (b, a)
        r = big["area_km2"] / small["area_km2"]
        if not lo <= r <= hi:
            continue
        # l'ultima e' "a sorpresa": il piu' grande e' il MENO popoloso dei due
        if i == 2 and big["population"] > small["population"]:
            continue
        break
    else:
        raise RuntimeError("nessuna coppia valida")
    pair = [a, b]
    ans = pair.index(big)
    if r >= 1.95:
        tail = f"about {num_words(round(r))} times bigger!"
    else:
        tail = f"{num_words(round((r - 1) * 100))} percent bigger!"
    say_q = ["Which country is bigger?", "And these two?", "Last one. Which is bigger?"][i]
    return {"show": [a["cca2"], b["cca2"]], "options": [a["name"], b["name"]], "answer": ans,
            "areas": [round(a["area_km2"]), round(b["area_km2"])],
            "say_q": say_q, "say_a": f"{big['name']}, {tail}"}, [a["cca2"], b["cca2"]]


_BUILDERS = {"flag": _q_flag, "capital": _q_capital, "bigger": _q_bigger}


def build_queue(n_videos: int = 120) -> list[dict]:
    rng = random.Random(SEED)
    cs = load_countries()
    recent: list[list[str]] = []
    queue = []
    for k in range(n_videos):
        kind = KINDS[k % len(KINDS)]
        used = {c for v in recent[-NO_REPEAT_VIDEOS:] for c in v}
        qs, this = [], []
        for i, tier in enumerate((0, 1, 2)):
            q, codes = _BUILDERS[kind](rng, cs, tier, used | set(this), i)
            qs.append(q)
            this += codes
        recent.append(this)
        queue.append({"format": "quiz", "kind": kind, "id": k + 1,
                      "title_idx": (k // len(KINDS)) % 3, "questions": qs})
    _validate(queue, cs)
    return queue


def _validate(queue: list[dict], cs: list[dict]) -> None:
    """Fallisce la build se una regola di qualita' e' violata."""
    by_name = {c["name"]: c["cca2"] for c in cs}
    for it in queue:
        for q in it["questions"]:
            if it["kind"] == "flag":
                codes = [by_name[o] for o in q["options"]]
                for x in codes:
                    for y in codes:
                        assert not _confusable(x, y), f"quiz {it['id']}: bandiere gemelle {x}/{y}"
            if it["kind"] == "capital":
                assert q["show"][0] not in NO_CAPITAL_Q, f"quiz {it['id']}: capitale contesa"
                assert not ({"Jerusalem"} & set(q["options"])), f"quiz {it['id']}: Gerusalemme"
            if it["kind"] == "bigger":
                a, b = sorted(q["areas"])
                assert b / a >= 1.06, f"quiz {it['id']}: aree troppo vicine"
            assert len(set(q["options"])) == len(q["options"]), f"quiz {it['id']}: opzioni doppie"


def load_queue() -> list[dict]:
    return json.loads(QUEUE_P.read_text(encoding="utf-8")) if QUEUE_P.exists() else []


# ── metadati (titolo/descrizione/caption: neutri, niente "absurd facts") ──────

def title(item: dict) -> str:
    return TITLES[item["kind"]][item.get("title_idx", 0) % 3] + " #Shorts"


def description(item: dict) -> str:
    kind = item["kind"]
    if kind == "bigger":
        lines = [f"{q['options'][0]} vs {q['options'][1]}" for q in item["questions"]]
    elif kind == "capital":
        lines = [f"Capital of {q['country']}" for q in item["questions"]]
    else:
        lines = [f"Flag {i}" for i in range(1, 4)]
    return (
        f"{title(item).replace(' #Shorts', '')} Answer before the timer runs out!\n\n"
        + "\n".join(lines) + "\n\nHow many did you get? Comment your score!\n\n"
        "#shorts #quiz #geography #trivia #flags\n\n"
        "Flags: flagcdn.com (public domain). Country data: mledoze/countries (ODbL), World Bank."
    )


TAGS = ["geography quiz", "flag quiz", "guess the flag", "capital cities quiz",
        "trivia", "quiz shorts", "geography", "countries", "which is bigger"]


# ── audio ──────────────────────────────────────────────────────────────────────

SR = 44100


def _tone(freqs, dur, vol=0.35, decay=18.0):
    t = np.arange(int(SR * dur)) / SR
    w = sum(np.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
    return (w * np.exp(-decay * t) * vol).astype(np.float32)


TICK = _tone([1800, 2600], 0.06, 0.30, 70.0)
DING = np.concatenate([_tone([880], 0.12, 0.30, 8.0), _tone([1320], 0.35, 0.30, 6.0)])


def _tts_lines(lines: list[str], work: Path) -> list[Path]:
    """UNA sola richiesta TTS per video (il servizio Edge da 403 alle raffiche:
    7 richieste a video fallivano di continuo il 13/11/2026), poi l'mp3 viene
    tagliato frase per frase coi tempi parola (WordBoundary)."""
    import asyncio
    import time
    from moviepy import AudioFileClip
    from generate_audio import _tts_stream, _align_boundaries
    from config import VOICE_RATE

    outs = [work / f"line{i}.mp3" for i in range(len(lines))]
    if all(p.exists() for p in outs):
        return outs
    full = work / "full.mp3"
    narration = " ".join(lines)
    for attempt in range(6):
        try:
            bounds = asyncio.run(_tts_stream(narration, full, VOICE, VOICE_RATE))
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 5:
                raise
            wait = 3 * 2 ** attempt
            print(f"    TTS fallito ({type(e).__name__}), riprovo tra {wait}s")
            time.sleep(wait)
    parts = _align_boundaries([("line", t) for t in lines], narration, bounds)
    if not all(p["words"] for p in parts):
        raise RuntimeError("allineamento TTS fallito: una frase senza parole")
    src = AudioFileClip(str(full))
    for i, (p, out) in enumerate(zip(parts, outs)):
        t0 = max(p["words"][0]["t"] - 0.05, 0)
        nxt = parts[i + 1]["words"][0]["t"] if i + 1 < len(parts) else src.duration
        last = p["words"][-1]
        t1 = min(last["t"] + last["d"] + 0.25, nxt - 0.02, src.duration)
        src.subclipped(t0, t1).write_audiofile(str(out), fps=SR, logger=None)
    src.close()
    return outs


def build_timeline(item: dict, work: Path) -> tuple[list[dict], list[tuple[float, Path]], np.ndarray, float]:
    """Fasi del video + clip voce + traccia effetti. Una fase = (domanda i, 'ask'|'count'|'reveal'|'end')."""
    from moviepy import AudioFileClip
    work.mkdir(parents=True, exist_ok=True)
    lines = [x for q in item["questions"] for x in (q["say_q"], q["say_a"])] + ["How many did you get?"]
    paths = _tts_lines(lines, work)

    def dur(p):
        a = AudioFileClip(str(p)); d = a.duration; a.close(); return d

    phases, voice, fx_events = [], [], []
    t = 0.0
    for i, q in enumerate(item["questions"]):
        pq, pa = paths[2 * i], paths[2 * i + 1]
        voice.append((t, pq))
        t_end_q = t + dur(pq) + 0.1
        phases.append({"q": i, "mode": "ask", "t0": t, "t1": t_end_q})
        phases.append({"q": i, "mode": "count", "t0": t_end_q, "t1": t_end_q + COUNTDOWN_S})
        for s in range(3):
            fx_events.append((t_end_q + s, TICK))
        t = t_end_q + COUNTDOWN_S
        fx_events.append((t, DING))
        voice.append((t + 0.15, pa))
        t_end = t + 0.15 + dur(pa) + 0.45
        phases.append({"q": i, "mode": "reveal", "t0": t, "t1": t_end})
        t = t_end
    pc = paths[-1]
    voice.append((t, pc))
    t_end = t + dur(pc) + 0.6
    phases.append({"q": len(item["questions"]) - 1, "mode": "end", "t0": t, "t1": t_end})
    total = t_end

    fx = np.zeros(int(SR * (total + 1)), dtype=np.float32)
    for st, snd in fx_events:
        a = int(st * SR)
        fx[a:a + len(snd)] += snd[: len(fx) - a]
    return phases, voice, fx, total


# ── grafica ────────────────────────────────────────────────────────────────────

def _font(size):
    from generate_video import _font as f
    return f(size)


def _gradient(kind):
    top, bot = GRADIENTS[kind]
    y = np.linspace(0, 1, HEIGHT)[:, None, None]
    arr = (np.array(top)[None, None, :] * (1 - y) + np.array(bot)[None, None, :] * y)
    arr = np.repeat(arr, WIDTH, axis=1).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _text_c(draw, cx, cy, text, size, fill=WHITE, stroke=6, stroke_fill=(0, 0, 0), max_w=None):
    f = _font(size)
    while max_w and draw.textlength(text, font=f) > max_w and size > 30:
        size -= 4
        f = _font(size)
    bb = draw.textbbox((0, 0), text, font=f, stroke_width=stroke)
    draw.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2), text, font=f,
              fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)


def _flag(code, max_w, max_h):
    im = Image.open(FLAGS / f"{code}.png").convert("RGBA")
    s = min(max_w / im.width, max_h / im.height)
    return im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)


def _paste_flag(img, code, cx, cy, max_w, max_h, border=None):
    fl = _flag(code, max_w, max_h)
    x, y = int(cx - fl.width / 2), int(cy - fl.height / 2)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((x + 10, y + 16, x + fl.width + 10, y + fl.height + 16), fill=(0, 0, 0, 120))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
    b = border or (WHITE, 8)
    ImageDraw.Draw(img).rectangle((x - b[1], y - b[1], x + fl.width + b[1] - 1, y + fl.height + b[1] - 1), fill=b[0])
    img.alpha_composite(fl, (x, y))
    return (x, y, x + fl.width, y + fl.height)


def _option_box(draw, box, letter, text, state):
    """state: 'idle' | 'right' | 'wrong'."""
    fill, tcol = {"idle": (WHITE, INK), "right": (GREEN, WHITE), "wrong": ((55, 65, 81), (156, 163, 175))}[state]
    draw.rounded_rectangle(box, radius=30, fill=fill, outline=(0, 0, 0), width=4)
    x0, y0, x1, y1 = box
    cy = (y0 + y1) / 2
    draw.ellipse((x0 + 18, cy - 30, x0 + 78, cy + 30), fill=INK if state != "right" else WHITE)
    _text_c(draw, x0 + 48, cy, letter, 36, fill=WHITE if state != "right" else GREEN, stroke=0)
    _text_c(draw, (x0 + 90 + x1 - 16) / 2, cy, text, 46, fill=tcol, stroke=0, max_w=x1 - x0 - 120)


def _base(item, qi, mode):
    """Immagine statica di una fase (tutto tranne il countdown animato)."""
    kind = item["kind"]
    q = item["questions"][qi]
    img = _gradient(kind).convert("RGBA")
    d = ImageDraw.Draw(img)
    _text_c(d, WIDTH / 2, 215, HEADERS[kind], 88, stroke=8, max_w=980)
    # progresso: 3 pallini
    for k in range(3):
        cx = WIDTH / 2 + (k - 1) * 70
        if k <= qi:
            d.ellipse((cx - 20, 300, cx + 20, 340), fill=WHITE, outline=(0, 0, 0), width=3)
        else:
            d.ellipse((cx - 20, 300, cx + 20, 340), outline=WHITE, width=5)
    revealed = mode in ("reveal", "end")

    if kind == "flag":
        _paste_flag(img, q["show"][0], WIDTH / 2, 640, 860, 500)
    elif kind == "capital":
        _paste_flag(img, q["show"][0], WIDTH / 2, 590, 640, 380)
        _text_c(d, WIDTH / 2, 870, q["country"].upper(), 84, stroke=8, max_w=980)
    if kind in ("flag", "capital"):
        boxes = [(70, 1060, 520, 1200), (560, 1060, 1010, 1200),
                 (70, 1230, 520, 1370), (560, 1230, 1010, 1370)]
        for k, (box, opt) in enumerate(zip(boxes, q["options"])):
            st = "idle" if not revealed else ("right" if k == q["answer"] else "wrong")
            _option_box(d, box, "ABCD"[k], opt, st)
    else:  # bigger: due bandiere affiancate, il nome sotto, l'area alla rivelazione
        for k, code in enumerate(q["show"]):
            cx = WIDTH / 2 + (k * 2 - 1) * 265
            win = revealed and k == q["answer"]
            border = (GREEN, 16) if win else ((WHITE, 8) if not revealed else ((75, 85, 99), 8))
            _, _, _, yb = _paste_flag(img, code, cx, 660, 380, 290, border)
            _text_c(d, cx, yb + 70, q["options"][k].upper(), 56, stroke=6, max_w=440)
            if revealed:
                area = f"{q['areas'][k]:,} km²"
                _text_c(d, cx, yb + 145, area, 48, fill=(253, 224, 71) if win else (209, 213, 219), stroke=5)
        _text_c(d, WIDTH / 2, 660, "VS", 72, fill=(253, 224, 71), stroke=8)
    if mode == "end":
        _text_c(d, WIDTH / 2, 1560, "COMMENT YOUR SCORE!", 70, fill=(253, 224, 71), stroke=8, max_w=980)
    return img


def _ring(img, cy, remaining, frac):
    """Countdown: anello che si svuota + numero grande."""
    d = ImageDraw.Draw(img)
    cx, r = WIDTH / 2, 92
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 150))
    d.arc((cx - r, cy - r, cx + r, cy + r), start=-90, end=-90 + 360 * frac, fill=(253, 224, 71), width=16)
    _text_c(d, cx, cy, str(remaining), 110, stroke=6)


def render(item: dict, out: Path) -> Path:
    from moviepy import AudioArrayClip, AudioFileClip, CompositeAudioClip, VideoClip
    work = AUDIO_DIR / f"quiz_{item['id']}"
    phases, voice, fx, total = build_timeline(item, work)
    cache: dict = {}
    ring_y = {"flag": 1480, "capital": 1480, "bigger": 1230}[item["kind"]]
    starts = [p["t0"] for p in phases]

    def frame(t):
        import bisect
        p = phases[max(bisect.bisect_right(starts, t) - 1, 0)]
        mode = "ask" if p["mode"] == "count" else p["mode"]
        key = (p["q"], mode)
        if key not in cache:
            cache.clear()
            cache[key] = _base(item, p["q"], mode)
        img = cache[key]
        if p["mode"] == "count":
            img = img.copy()
            el = t - p["t0"]
            _ring(img, ring_y, max(1, math.ceil(COUNTDOWN_S - el)), 1 - el / COUNTDOWN_S)
        return np.array(img.convert("RGB"))

    clips = [AudioFileClip(str(p)).with_start(st) for st, p in voice]
    fx_clip = AudioArrayClip(np.stack([fx, fx], axis=1), fps=SR)
    audio = CompositeAudioClip([fx_clip] + clips).with_duration(total)
    out.parent.mkdir(parents=True, exist_ok=True)
    VideoClip(frame, duration=total).with_fps(FPS).with_audio(audio).write_videofile(
        str(out), fps=FPS, codec="libx264", audio_codec="aac", preset="fast",
        ffmpeg_params=["-crf", "23"], logger=None)
    for c in clips:
        c.close()
    print(f"    Quiz #{item['id']} ({item['kind']}) -> {out.name}, {total:.1f}s")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        q = build_queue()
        QUEUE_P.parent.mkdir(parents=True, exist_ok=True)
        QUEUE_P.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(q)} quiz -> {QUEUE_P}")
    elif cmd == "render":
        items = {i["id"]: i for i in load_queue()}
        for n in map(int, sys.argv[2:]):
            render(items[n], OUTPUT_DIR / "quiz" / f"quiz_{n}.mp4")
    else:
        print(__doc__)
