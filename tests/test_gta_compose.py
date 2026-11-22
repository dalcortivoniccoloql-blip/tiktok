# Test della logica di gta/compose.py (piano spezzoni, validazione job, descrizione).
# Niente render/rete: il render end-to-end si prova a mano con `py -3 -m gta.compose`.
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from gta import compose  # noqa: E402


def test_piano_spezzoni_brevi_e_rotazione():
    p = compose.piano_segmenti(13.4, [5.0, 0.0, 2.0], [30, 25, 20])
    assert [s.clip for s in p] == [0, 1, 2]
    assert all(compose.SEG_MIN <= s.fine - s.inizio <= compose.SEG_MAX for s in p)
    assert p[-1].fine == pytest.approx(13.4)
    assert p[0].src_start == 5.0


def test_piano_voce_lunga_ripassa_senza_ripetere_lo_spezzone():
    p = compose.piano_segmenti(24.0, [0.0, 10.0], [30, 30])
    assert all(s.fine - s.inizio <= compose.SEG_MAX + 1e-9 for s in p)
    seconda_volta = [s for s in p if s.clip == 0][1]
    lunghezza = p[0].fine - p[0].inizio
    assert seconda_volta.src_start == pytest.approx(lunghezza)  # prosegue dopo il primo pezzo


def test_piano_wrap_su_clip_corta():
    p = compose.piano_segmenti(20.0, [8.0, 0.0], [10, 30])
    assert all(0 <= s.src_start < 30 for s in p)
    assert [s for s in p if s.clip == 0][1].src_start < 10


def test_start_default_centro():
    assert compose.start_default(30, 6) == 12
    assert compose.start_default(4, 6) == 0


def _job(tmp_path, **over):
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    for n in ("a", "b"):
        (inbox / f"{n}.mp4").write_bytes(b"x")
        (inbox / f"{n}.json").write_text(json.dumps({"streamer": n.upper()}), encoding="utf-8")
    job = {"hook": "h", "facts": ["f1"], "fonte": "https://x", "clips": [{"file": "a.mp4"}, {"file": "b.mp4"}]}
    job.update(over)
    p = tmp_path / "v1.json"
    p.write_text(json.dumps(job), encoding="utf-8")
    return p, inbox


def test_job_valido(tmp_path):
    p, inbox = _job(tmp_path)
    job = compose.load_job(p, inbox)
    assert job["id"] == "v1"
    s = compose.narration_script(job)
    assert s["format"] == "single" and s["facts"] == ["f1"]


@pytest.mark.parametrize("over,msg", [
    ({"fonte": ""}, "fonte"),
    ({"hook": " "}, "hook"),
    ({"facts": []}, "facts"),
    ({"clips": [{"file": "a.mp4"}]}, "clips"),
    ({"clips": [{"file": "a.mp4"}, {"file": "manca.mp4"}]}, "non trovata"),
])
def test_job_invalido(tmp_path, over, msg):
    p, inbox = _job(tmp_path, **over)
    with pytest.raises(compose.JobError, match=msg):
        compose.load_job(p, inbox)


def test_job_senza_metadati_credito(tmp_path):
    p, inbox = _job(tmp_path)
    (inbox / "b.json").unlink()
    with pytest.raises(compose.JobError, match="credito"):
        compose.load_job(p, inbox)


def test_descrizione_crediti_unici_e_fonte():
    job = {"hook": "Hook.", "fonte": "https://fonte"}
    d = compose.descrizione(job, [{"streamer": "A"}, {"streamer": "B"}, {"streamer": "A"}])
    assert d.count("twitch.tv/A") == 1 and "twitch.tv/B" in d
    assert "Source: https://fonte" in d


def test_esempio_committato_e_ben_formato():
    job = json.loads((compose.VIDEOS_DIR / "_esempio.json").read_text(encoding="utf-8"))
    assert job["fonte"] and 2 <= len(job["clips"]) <= 4
