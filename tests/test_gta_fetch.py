# Test di gta/fetch.py con un finto Twitch: niente rete, niente credenziali.
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from gta import fetch  # noqa: E402

GTA = "999"
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


def clip(cid, views=100, game=GTA, dur=30.0, lang="en", who="Alpha"):
    return {"id": cid, "url": f"https://clips.twitch.tv/{cid}", "broadcaster_name": who,
            "game_id": game, "view_count": views, "duration": dur, "language": lang,
            "title": f"titolo {cid}", "created_at": "2026-11-21T10:00:00Z", "creator_name": "x"}


class Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, users, clips_by_id):
        self.users = users
        self.clips_by_id = clips_by_id
        self.calls = []

    def post(self, url, params=None, timeout=None):
        assert params["grant_type"] == "client_credentials"
        return Resp({"access_token": "tok"})

    def get(self, url, params=None, timeout=None, headers=None):
        assert headers["Authorization"] == "Bearer tok"
        self.calls.append((url, params))
        if url.endswith("/users"):
            logins = [v for k, v in params]
            return Resp({"data": [{"login": l, "id": self.users[l]} for l in logins if l in self.users]})
        if url.endswith("/clips"):
            return Resp({"data": self.clips_by_id.get(params["broadcaster_id"], [])})
        if url.endswith("/games"):
            return Resp({"data": [{"id": GTA}]})
        raise AssertionError(url)


def client(users, clips_by_id):
    return fetch.TwitchClient("cid", "sec", session=FakeSession(users, clips_by_id))


def test_whitelist_solo_confermati_con_prova(tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"streamer": [
        {"login": "Alpha", "prova_permesso": "https://x", "confermato": True},
        {"login": "beta", "prova_permesso": "https://x", "confermato": False},
        {"login": "gamma", "prova_permesso": "", "confermato": True},
        {"login": "delta", "prova_permesso": "https://x", "confermato": "true"},
    ]}), encoding="utf-8")
    assert fetch.load_whitelist(p) == ["alpha"]


def test_whitelist_reale_e_valida():
    # il file committato deve restare leggibile (e l'esempio non confermato)
    assert "esempio_streamer" not in fetch.load_whitelist()


def test_seleziona_filtri_e_ordine():
    f = fetch.Filtri(game_id=GTA, per_streamer=2, min_views=10)
    cl = [clip("a", 50), clip("b", 500), clip("c", 300), clip("altro", 9999, game="1"),
          clip("corta", 900, dur=5), clip("es", 900, lang="es"), clip("poche", 5), clip("vista", 800)]
    out = fetch.seleziona(cl, f, viste={"vista"})
    assert [c["id"] for c in out] == ["b", "c"]


def test_run_scarica_salva_meta_e_non_riscarica(tmp_path):
    c = client({"alpha": "1"}, {"1": [clip("a", 50), clip("b", 500)]})
    f = fetch.Filtri(game_id=GTA)
    scaricati = []

    def fake_dl(url, dest):
        scaricati.append(url)
        dest.write_bytes(b"mp4")

    out = fetch.run(c, ["alpha"], f, 48, tmp_path, download=fake_dl, now=NOW)
    assert [p.name for p in out] == ["alpha_b.mp4", "alpha_a.mp4"]
    meta = json.loads((tmp_path / "inbox" / "alpha_b.json").read_text(encoding="utf-8"))
    assert meta["credito"] == "Clip: twitch.tv/Alpha — https://clips.twitch.tv/b"
    assert meta["login"] == "alpha"

    # la finestra temporale passata a Helix e' quella richiesta
    _, params = [x for x in c.s.calls if x[0].endswith("/clips")][0]
    assert params["started_at"] == "2026-11-20T12:00:00Z"
    assert params["ended_at"] == "2026-11-22T12:00:00Z"

    # seconda esecuzione: niente di nuovo
    assert fetch.run(c, ["alpha"], f, 48, tmp_path, download=fake_dl, now=NOW) == []
    assert len(scaricati) == 2


def test_download_fallito_non_segna_vista_e_non_blocca(tmp_path):
    c = client({"alpha": "1"}, {"1": [clip("rotta", 900), clip("ok", 100)]})

    def dl(url, dest):
        if "rotta" in url:
            raise RuntimeError("boom")
        dest.write_bytes(b"mp4")

    out = fetch.run(c, ["alpha"], fetch.Filtri(game_id=GTA), 48, tmp_path, download=dl, now=NOW)
    assert [p.name for p in out] == ["alpha_ok.mp4"]
    assert fetch.load_seen(tmp_path / "seen_clips.json") == {"ok"}


def test_dry_run_non_scrive_nulla(tmp_path):
    c = client({"alpha": "1"}, {"1": [clip("a")]})

    def dl(url, dest):
        raise AssertionError("non deve scaricare")

    assert fetch.run(c, ["alpha"], fetch.Filtri(game_id=GTA), 48, tmp_path,
                     dry_run=True, download=dl, now=NOW) == []
    assert not (tmp_path / "inbox").exists()


def test_credenziali_mancanti_messaggio_chiaro(tmp_path, monkeypatch):
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)
    try:
        fetch.load_credentials(tmp_path / "manca.env")
    except SystemExit as e:
        assert "dev.twitch.tv" in str(e)
    else:
        raise AssertionError("doveva fermarsi")


def test_credenziali_da_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)
    p = tmp_path / "t.env"
    p.write_text("# commento\nTWITCH_CLIENT_ID=abc\nTWITCH_CLIENT_SECRET='xyz'\n", encoding="utf-8")
    assert fetch.load_credentials(p) == ("abc", "xyz")
