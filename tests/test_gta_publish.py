# Test di gta/publish.py: slot, coda, titoli, controllo canale. Niente rete.
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from gta import publish  # noqa: E402

UTC = timezone.utc


def dt(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=UTC)


def test_slot_dopo_anticipo():
    # alle 16:30 lo slot 17:00 e' a meno di 1h: si parte dalle 23:00
    assert publish.prossimi_slot(3, dt(22, 16, 30), set()) == [dt(22, 23), dt(23, 17), dt(23, 23)]


def test_slot_dopo_ultimo_programmato():
    occ = {dt(24, 17)}
    assert publish.prossimi_slot(2, dt(22, 8), occ) == [dt(24, 23), dt(25, 17)]


def test_slot_passati_non_contano():
    assert publish.prossimi_slot(1, dt(22, 8), {dt(20, 17)}) == [dt(22, 17)]


def test_titolo():
    assert publish.titolo("Hi") == "Hi #Shorts"
    assert publish.titolo("Hi #shorts") == "Hi #shorts"
    t = publish.titolo("x" * 150)
    assert len(t) <= 100 and t.endswith("#Shorts")


def _render(tmp_path, *ids):
    for i in ids:
        (tmp_path / f"{i}.mp4").write_bytes(b"x")
        (tmp_path / f"{i}.yt.json").write_text(json.dumps({"title": f"T{i}", "description": "d"}))
    return tmp_path


def test_coda_salta_pubblicati_esempi_e_senza_meta(tmp_path):
    r = _render(tmp_path, "gta002", "gta001", "_esempio", "gta003")
    (r / "gta004.mp4").write_bytes(b"x")   # senza .yt.json
    assert [v for v, _, _ in publish.coda(r, {"gta003": {}})] == ["gta001", "gta002"]


class FakeService:
    def __init__(self, ch_id, title="GTA Secrets"):
        self.items = [{"id": ch_id, "snippet": {"title": title}}]

    def channels(self):
        return self

    def list(self, **kw):
        assert kw["mine"] is True
        return self

    def execute(self):
        return {"items": self.items}


def test_verifica_canale():
    assert publish.verifica_canale(FakeService("UCgta"), atteso="UCgta") == "GTA Secrets"
    with pytest.raises(publish.CanaleSbagliato, match="5absurdfacts"):
        publish.verifica_canale(FakeService("UC98nOdXD_giA-xqs5CuBBLA"), atteso="UCgta")
    with pytest.raises(publish.CanaleSbagliato, match="vuoto"):
        publish.verifica_canale(FakeService("UCgta"), atteso="")
    with pytest.raises(publish.CanaleSbagliato, match="atteso"):
        publish.verifica_canale(FakeService("UCaltro"), atteso="UCgta")


def test_pubblica_registra_e_non_ricarica(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "GTA_CHANNEL_ID", "UCgta")
    (tmp_path / "r").mkdir()
    r = _render(tmp_path / "r", "gta001", "gta002")
    reg = tmp_path / "published.json"
    chiamate = []

    def up(service, mp4, meta, quando):
        chiamate.append((mp4.stem, quando))
        return f"yt_{mp4.stem}"

    out = publish.pubblica(FakeService("UCgta"), r, 5, dt(22, 8), False, reg, upload=up)
    assert out == ["yt_gta001", "yt_gta002"]
    assert chiamate == [("gta001", dt(22, 17)), ("gta002", dt(22, 23))]
    assert json.loads(reg.read_text())["gta001"]["youtube_id"] == "yt_gta001"

    # secondo giro: niente da caricare
    assert publish.pubblica(FakeService("UCgta"), r, 5, dt(22, 9), False, reg, upload=up) == []

    # un nuovo video va DOPO l'ultimo programmato
    _render(r, "gta003")
    publish.pubblica(FakeService("UCgta"), r, 5, dt(22, 9), False, reg, upload=up)
    assert chiamate[-1] == ("gta003", dt(23, 17))


def test_pubblica_canale_sbagliato_non_carica_nulla(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "GTA_CHANNEL_ID", "UCgta")
    r = _render(tmp_path, "gta001")

    def up(*a):
        raise AssertionError("non deve caricare")

    with pytest.raises(publish.CanaleSbagliato):
        publish.pubblica(FakeService("UC98nOdXD_giA-xqs5CuBBLA"), r, 5, dt(22, 8), False,
                         tmp_path / "p.json", upload=up)
    assert not (tmp_path / "p.json").exists()


def test_dry_run_non_tocca_registro(tmp_path):
    r = _render(tmp_path, "gta001")
    assert publish.pubblica(None, r, 5, dt(22, 8), True, tmp_path / "p.json") == []
    assert not (tmp_path / "p.json").exists()
