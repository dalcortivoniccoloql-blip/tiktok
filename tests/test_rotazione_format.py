# Verifica la rotazione dei format in cloud_publish.py senza rete e senza render.
# - rotazione SPENTA: si pubblica absurd come prima, il quiz non viene toccato
# - rotazione ACCESA, slot quiz: si pubblica il quiz, avanza solo formats.quiz.next
# - coda quiz finita: si ricade su absurd
# - fasce orarie: ritardi del cron (07->09, 12->14, 17->19) restano nello slot giusto
import json
import os
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipeline"))

CALLS = []


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


def _touch(p):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_bytes(b"finto")


_stub("docx", Document=object)
_stub("generate_audio", generate_audio_for_script=lambda s, p, overwrite=False: (CALLS.append("absurd_audio"), _touch(p)))
_stub("generate_video", create_video=lambda s, a, p, overwrite=False: (CALLS.append("absurd_video"), _touch(p)))
_stub("upload_youtube", upload_script_video=lambda s, p, publish_at=None: CALLS.append("yt:" + str(s.get("format", "?"))) or "ID")
_stub("upload_instagram", upload_script_reel=lambda s, p: None)

QUEUE = [{"format": "quiz", "kind": "flag", "id": 1, "questions": []},
         {"format": "quiz", "kind": "capital", "id": 2, "questions": []}]
_stub("formats")
_stub("formats.quiz", load_queue=lambda: QUEUE, render=lambda item, out: (CALLS.append(f"quiz_render:{item['id']}"), _touch(out)))
sys.modules["formats"].quiz = sys.modules["formats.quiz"]

import cloud_publish as cp  # noqa: E402

STATE = REPO / "state.json"
orig = STATE.read_text(encoding="utf-8")
fails = 0


def check(cond, msg):
    global fails
    print(("OK   " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


def run(state, rotation, slot):
    CALLS.clear()
    STATE.write_text(json.dumps(state), encoding="utf-8")
    os.environ["PUBLISH_ENABLED"] = "true"
    os.environ["FORMAT_ROTATION"] = "true" if rotation else ""
    cp.slot_format = (lambda h=None: slot)
    rc = cp.main()
    return rc, json.loads(STATE.read_text(encoding="utf-8"))


real_slot = cp.slot_format
try:
    for h, exp in [(7, "quiz"), (9, "quiz"), (12, "data"), (14, "data"), (17, "absurd"), (19, "absurd"), (23, "absurd")]:
        check(real_slot(h) == exp, f"ora {h} UTC -> {exp}")

    rc, st = run({"next": 430}, rotation=False, slot="quiz")
    check(rc == 0 and st == {"next": 431} and "absurd_video" in CALLS and not any("quiz" in c for c in CALLS),
          "rotazione spenta: absurd come prima, state.json senza chiavi nuove")

    rc, st = run({"next": 430}, rotation=True, slot="quiz")
    check(rc == 0 and st["next"] == 430 and st["formats"]["quiz"]["next"] == 2 and "quiz_render:1" in CALLS
          and "yt:quiz" in CALLS and "absurd_video" not in CALLS, "slot quiz: pubblica quiz #1, absurd fermo")

    rc, st = run({"next": 430, "formats": {"quiz": {"next": 2}}}, rotation=True, slot="quiz")
    check(st["formats"]["quiz"]["next"] == 3 and "quiz_render:2" in CALLS, "quiz successivo: #2")

    rc, st = run({"next": 430, "formats": {"quiz": {"next": 3}}}, rotation=True, slot="quiz")
    check(rc == 0 and st["next"] == 431 and st["formats"]["quiz"]["next"] == 3 and "absurd_video" in CALLS,
          "coda quiz finita: ricade su absurd")

    for slot in ("data", "absurd"):
        rc, st = run({"next": 430, "formats": {"quiz": {"next": 1}}}, rotation=True, slot=slot)
        check(rc == 0 and st["next"] == 431 and st["formats"]["quiz"]["next"] == 1, f"slot {slot}: absurd")
finally:
    STATE.write_text(orig, encoding="utf-8")
    for k in ("PUBLISH_ENABLED", "FORMAT_ROTATION"):
        os.environ.pop(k, None)

print("\nTUTTI I CONTROLLI PASSATI." if not fails else f"\n{fails} CONTROLLI FALLITI")
sys.exit(1 if fails else 0)
