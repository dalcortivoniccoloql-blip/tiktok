# Durata: LEGATO-A:P09 — verifica i 4 rami di cloud_publish.py senza rete e senza render
# (audio/video/upload sostituiti da finti: si testa la LOGICA di uscita, non ffmpeg)
import importlib
import io
import json
import os
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipeline"))

CHIAMATE = {"audio": 0, "video": 0, "upload": 0}


def _stub(nome, **attrs):
    m = types.ModuleType(nome)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[nome] = m


def _audio(script, path, overwrite=False):
    CHIAMATE["audio"] += 1
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(b"finto")


def _video(script, audio, path, overwrite=False):
    CHIAMATE["video"] += 1
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(b"finto")


def _upload(script, path, publish_at=None):
    CHIAMATE["upload"] += 1
    return "FINTO_VIDEO_ID"


_stub("docx", Document=object)
_stub("generate_audio", generate_audio_for_script=_audio)
_stub("generate_video", create_video=_video)
_stub("upload_youtube", upload_script_video=_upload, WrongChannelError=RuntimeError)
_stub("upload_instagram", upload_script_reel=lambda s, p: None)

import cloud_publish as cp  # noqa: E402

STATO = REPO / "state.json"
originale = STATO.read_text(encoding="utf-8")
TOTALE = len(cp.load_scripts())
print(f"script in archivio: {TOTALE}\n")


def prova(titolo, next_, publish, atteso_rc, attesi_in_output):
    STATO.write_text(json.dumps({"next": next_}), encoding="utf-8")
    if publish:
        os.environ["PUBLISH_ENABLED"] = "true"
    else:
        os.environ.pop("PUBLISH_ENABLED", None)
    for k in CHIAMATE:
        CHIAMATE[k] = 0
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cp.main()
    out = buf.getvalue()
    ok = rc == atteso_rc and all(a in out for a in attesi_in_output)
    print(f"[{'OK ' if ok else 'FALLITO'}] {titolo}")
    print(f"        exit={rc} (atteso {atteso_rc}) · upload effettuati={CHIAMATE['upload']}")
    if not ok:
        for a in attesi_in_output:
            if a not in out:
                print(f"        manca nell'output: {a!r}")
        print("        --- output ---")
        print("        " + out.replace("\n", "\n        "))
    return ok


risultati = [
    prova("coda piena + pubblicazione SPENTA -> verde, nessun upload",
          210, False, 0, ["CONTROLLO DI SALUTE", "Primo fatto:"]),
    prova("coda VUOTA + pubblicazione SPENTA -> verde, ma lo dice",
          TOTALE + 1, False, 0, ["CONTROLLO DI SALUTE", "la coda e' finita"]),
    prova("coda VUOTA + pubblicazione ACCESA -> ROSSO (era il bug del 26/08)",
          TOTALE + 1, True, 1, ["ERRORE", "La coda e' finita", "english_scripts_N.json"]),
    prova("coda piena + pubblicazione ACCESA -> pubblica e avanza",
          210, True, 0, ["PUBBLICATO", "Prossimo script: #211"]),
]

if CHIAMATE["upload"] != 1:
    print("ATTENZIONE: l'ultimo caso non ha chiamato l'upload")

STATO.write_text(originale, encoding="utf-8")
print(f"\nstate.json ripristinato a: {originale.strip()}")
print("TUTTI I RAMI OK" if all(risultati) else "CI SONO RAMI FALLITI")
sys.exit(0 if all(risultati) else 1)
