# Durata: LEGATO-A:P09 — verifica la validazione di generate_scripts.py senza chiamare l'API
# (inietta una risposta finta: stesso metodo usato il 2026-08-01 per il verdetto MATCH)
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipeline"))

RISPOSTA_FINTA = [
    # 1) buono
    {"hook": "A cloud can weigh more than a plane.",
     "facts": ["A white summer cloud is made of billions of tiny water drops.",
               "Each drop is light, but there are so many that the total gets heavy.",
               "A medium cloud can hold about five hundred thousand kilograms of water."]},
    # 2) hook troppo lungo -> scartato
    {"hook": "There is a very long hook here that keeps going and going past the limit.",
     "facts": ["beat uno abbastanza lungo da passare il controllo di lunghezza.",
               "beat due abbastanza lungo da passare il controllo di lunghezza.",
               "beat tre abbastanza lungo da passare il controllo di lunghezza."]},
    # 3) cifre e abbreviazioni -> scartato
    {"hook": "A snail can sleep for three years.",
     "facts": ["A snail can travel 50 cm in one hour when it is in a hurry.",
               "It seals itself inside the shell and waits for the rain to come back.",
               "Some snails have slept for three years and woken up as if it was normal."]},
    # 4) solo 2 beat -> scartato
    {"hook": "Wombats make cube shaped poop.",
     "facts": ["The last part of the gut has stiff and soft patches that shape it.",
               "The cubes do not roll away, so they stay where the wombat leaves them."]},
    # 5) hook duplicato di uno gia' pubblicato -> scartato
    {"hook": "Bananas are slightly radioactive.",
     "facts": ["Bananas hold a lot of potassium and part of it is radioactive.",
               "The amount is tiny, and scientists use it to explain radiation.",
               "You would have to eat millions in one day for it to hurt you."]},
    # 6) beat identico a uno gia' nel corpus -> resta con 2 beat -> scartato
    {"hook": "Butterflies have a strange way to taste.",
     "facts": ["Butterflies taste with their feet.",
               "The sensors sit on the legs and work like the tip of a tongue.",
               "Butterflies taste with their feet."]},
]


class _Blocco:
    type = "text"
    def __init__(self, text): self.text = text


class _Resp:
    def __init__(self, payload): self.content = [_Blocco(json.dumps(payload))]


class _Messages:
    def create(self, **kw):
        assert kw["model"] == "claude-opus-5", f"modello inatteso: {kw['model']}"
        assert kw["thinking"] == {"type": "adaptive"}, "thinking adattivo mancante"
        assert kw["max_tokens"] >= 16000, "max_tokens troppo basso"
        prompt = kw["messages"][0]["content"]
        for atteso in ['"hook"', "at most 9 words", "OUT IN WORDS", "beat 3"]:
            assert atteso in prompt, f"il prompt non chiede piu': {atteso}"
        assert "groups of 5" not in prompt, "il prompt chiede ancora 5 fatti"
        return _Resp(RISPOSTA_FINTA)


class _Client:
    def __init__(self, api_key=None): self.messages = _Messages()


sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=_Client)

import generate_scripts as g  # noqa: E402

g.NEW_SCRIPTS = len(RISPOSTA_FINTA)
uscita = REPO / "pipeline" / f"english_scripts_{g._next_file_index()}.json"
assert not uscita.exists(), f"{uscita.name} esiste gia': test annullato per non sovrascrivere"

import os  # noqa: E402
os.environ["ANTHROPIC_API_KEY"] = "test-non-usata"
rc = g.generate(force=True)
print(f"\nexit code: {rc}")

prodotti = json.loads(uscita.read_text(encoding="utf-8"))
uscita.unlink()  # test: non lasciare file dietro

print(f"script accettati: {len(prodotti)} su {len(RISPOSTA_FINTA)}")
assert rc == 0
assert len(prodotti) == 1, f"attesi 1 script valido, arrivati {len(prodotti)}"
s = prodotti[0]
assert s["format"] == "single", "campo format mancante: il render tornerebbe a 5 fatti"
assert s["hook"].startswith("A cloud"), s["hook"]
assert len(s["facts"]) == 3
assert s["cta"] == ""
print("\nTUTTI I CONTROLLI PASSATI: schema single, 5 script cattivi su 6 scartati,")
print("file di uscita rimosso dopo il test.")
