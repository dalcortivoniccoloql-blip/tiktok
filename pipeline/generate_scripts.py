# Durata: LEGATO-A:P09
"""
Genera automaticamente nuovi script di curiosita' con l'API di Claude,
quando quelli esistenti stanno per finire.

FORMATO: dal 2026-08-31 genera nel formato "single" (1 curiosita' per Short:
hook + 3 beat), non piu' nel vecchio formato a 5 fatti. Non e' un dettaglio di
stile: uno script senza il campo "format": "single" viene renderizzato con la
vecchia timeline a 5 fatti, quindi un generatore rimasto al vecchio schema
riporta il canale indietro in silenzio, un video alla volta. Lo schema che
questo file deve produrre e' descritto in docs/FORMATO-SINGLE.md, sezione 3.

Si attiva SOLO se la variabile d'ambiente ANTHROPIC_API_KEY e' impostata.
Crea un nuovo file english_scripts_N.json con curiosita' nuove (deduplicate).

Uso:
    python pipeline/generate_scripts.py            # genera se i contenuti sono pochi
    python pipeline/generate_scripts.py --force    # genera comunque
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

PIPE = Path(__file__).parent

NEW_SCRIPTS   = 30     # quanti script generare per volta (30 = 10 giorni a 3/giorno)
BEATS_EACH    = 3      # beat per script nel formato single (il campo si chiama ancora "facts")
HOOK_MAX_WORDS = 9     # ~2,5 s di TTS: oltre, la promessa arriva dopo lo swipe
LOW_THRESHOLD = 12     # genera se restano meno di N script non ancora usati
MODEL         = "claude-opus-5"     # massima accuratezza sui fatti (costo comunque irrisorio: ~30 script/settimana)


def _all_script_files() -> list[Path]:
    return sorted(PIPE.glob("english_scripts*.json"))


def _load_existing() -> list[dict]:
    scripts = []
    for f in _all_script_files():
        scripts.extend(json.loads(f.read_text(encoding="utf-8")))
    return scripts


def _next_file_index() -> int:
    """Trova il prossimo suffisso libero: english_scripts_3.json, _4.json, ..."""
    max_n = 1
    for f in _all_script_files():
        m = re.search(r"english_scripts_(\d+)\.json$", f.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


# cifre e abbreviazioni che il TTS legge male ("km" -> "chi-emme"): il prompt le
# vieta gia', questo e' il controllo che non si fida della risposta del modello.
_BAD_FOR_TTS = re.compile(r"[0-9%#\u00b0]|\b(km|cm|mm|kg|kmh|deg|lbs|ft)\b", re.IGNORECASE)


def _norm(fact: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", fact.lower()).strip()


def _remaining_count() -> int:
    """Quanti script non ancora pubblicati restano (in base a state.json)."""
    total = len(_load_existing())
    state_path = PIPE.parent / "state.json"
    nxt = 1
    if state_path.exists():
        nxt = int(json.loads(state_path.read_text()).get("next", 1))
    return total - (nxt - 1)


def generate(force: bool = False) -> int:
    key       = os.environ.get("ANTHROPIC_API_KEY")
    remaining = _remaining_count()

    # Ordine voluto: prima si guarda QUANTI script restano, poi se c'e' la key.
    # Al contrario (com'era fino al 2026-08-31) un job senza key stampava una riga
    # e usciva VERDE anche a coda vuota: 5 run "success" di fila, zero script
    # generati dal 26/06, e il canale si e' fermato il 26/08 senza un solo allarme.
    if not force and remaining > LOW_THRESHOLD:
        print(f"Restano ancora {remaining} script: non serve generarne di nuovi.")
        if not key:
            print("(ANTHROPIC_API_KEY non impostata, ma per ora non serve.)")
        return 0

    if not key:
        # Qui la coda e' bassa E non possiamo rifornirla: e' un guasto, non una nota.
        # Il run deve diventare ROSSO, altrimenti nessuno lo scopre.
        print("ERRORE: restano solo "
              f"{remaining} script e ANTHROPIC_API_KEY non e' impostata.")
        print("Senza key non posso generarne di nuovi: quando la coda finisce, il")
        print("canale smette di pubblicare in silenzio (gia' successo il 2026-08-26).")
        print("Rimedio: repo > Settings > Secrets and variables > Actions > Secrets")
        print("> New repository secret > ANTHROPIC_API_KEY.")
        print("Oppure, subito: scrivere a mano un nuovo pipeline/english_scripts_N.json")
        print("nel formato single (schema in docs/FORMATO-SINGLE.md, sezione 3).")
        return 1

    print(f"Restano {remaining} script. Genero {NEW_SCRIPTS} nuovi script...")

    try:
        import anthropic
    except ImportError:
        print("Pacchetto 'anthropic' non installato: pip install anthropic")
        return 1

    existing = _load_existing()
    existing_facts = {_norm(f) for s in existing for f in s["facts"]}
    # anche gli hook gia' usati: dal formato single l'hook e' il titolo del video,
    # due video con lo stesso titolo si cannibalizzano nella ricerca
    existing_facts |= {_norm(s["hook"]) for s in existing if s.get("hook")}
    # campione di fatti esistenti da passare al modello per evitare doppioni
    sample = [f for s in existing for f in s["facts"]]

    client = anthropic.Anthropic(api_key=key)

    prompt = (
        f"Write exactly {NEW_SCRIPTS} scripts for a faceless YouTube Shorts channel "
        "about absurd but TRUE facts. Each script is ONE fact, told in a hook plus "
        f"{BEATS_EACH} beats. The text is read aloud by a text-to-speech voice over "
        "on-screen captions, so write for the ear.\n"
        "STRUCTURE of one script:\n"
        f"- hook: ONE sentence, at most {HOOK_MAX_WORDS} words. It is also the video "
        "title. It must state a single concrete claim that sounds impossible, and it "
        "must open a hole the viewer wants filled. Not a summary, not a question, not "
        "'you won't believe this'.\n"
        "- beat 1: where or what it is (the setting).\n"
        "- beat 2: the mechanism, the why or the how.\n"
        "- beat 3: the payoff, the most absurd detail of all. It goes LAST.\n"
        "Rules:\n"
        "- Facts must be genuinely true and verifiable. NO popular myths (e.g. goldfish "
        "3-second memory, humans use 10% of the brain, Great Wall visible from space).\n"
        "- SIMPLE ENGLISH. This is the most important rule. Most viewers are NOT native "
        "speakers: write at CEFR A2-B1 level, the English of a 12-year-old.\n"
        "  * Everyday words only: 'grow back' not 'regenerate', 'find' not 'detect', "
        "'tiny living things' not 'microbes', 'clear' not 'transparent'.\n"
        "  * If a hard word IS the fact (tittle, petrichor, axolotl), keep it but explain "
        "it in the same sentence.\n"
        "  * One idea per sentence. No subordinate clauses and no -ing clause hanging at "
        "the end.\n"
        "  * Active voice: 'A navy engineer invented the Slinky', not 'The Slinky was "
        "invented by a naval engineer'.\n"
        "  * NO idioms and no figurative language.\n"
        "- Each beat is a single sentence of 45 to 110 characters.\n"
        "- WRITE EVERY NUMBER AND UNIT OUT IN WORDS, because the voice reads the text "
        "literally: 'four hundred and fifty million years', 'about five centimeters', "
        "'ninety percent'. Never use digits, and never use 'km', 'km/h', 'cm', 'kg', "
        "'C', '%', '#'.\n"
        "- The last beat should, when possible, point back to the hook: the video loops.\n"
        "- Cover varied topics: animals, space, human body, history, food, geography, "
        "science. No two scripts on the same animal or the same object.\n"
        "- Do NOT repeat or paraphrase any of the existing facts listed below.\n"
        "- Output ONLY a JSON array, no commentary. Format:\n"
        '  [{"hook": "...", "facts": ["beat1","beat2","beat3"]}, ...]\n\n'
        "Existing facts to avoid:\n" + "\n".join(f"- {f}" for f in sample)
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,  # 30 gruppi x 5 fatti + margine per il thinking
        thinking={"type": "adaptive"},  # ragiona sulla veridicita' prima di scrivere
        messages=[{"role": "user", "content": prompt}],
    )
    # con l'adaptive thinking il primo blocco puo' essere di tipo "thinking": prendi solo il testo
    text = "".join(b.text for b in resp.content if b.type == "text").strip()

    # estrai il JSON anche se incapsulato in ```json ... ```
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        print("Risposta non in formato JSON. Annullo.")
        print(text[:500])
        return 1
    new_scripts = json.loads(m.group(0))

    # dedup contro gli esistenti e tra loro + controlli di formato.
    # Uno script che non passa viene SCARTATO, non aggiustato: meglio 24 script
    # buoni che 30 di cui 6 rompono il render o fanno leggere "km" al TTS.
    clean   = []
    scartati = []
    for cand in new_scripts:
        hook  = (cand.get("hook") or "").strip()
        beats = [b.strip() for b in cand.get("facts", []) if b and b.strip()]

        if not hook:
            scartati.append("senza hook")
            continue
        if len(hook.split()) > HOOK_MAX_WORDS:
            scartati.append(f"hook di {len(hook.split())} parole: {hook}")
            continue
        if _norm(hook) in existing_facts:
            scartati.append(f"hook gia' usato: {hook}")
            continue

        beats = [b for b in beats if _norm(b) not in existing_facts]
        if len(beats) < BEATS_EACH:
            scartati.append(f"solo {len(beats)} beat nuovi: {hook}")
            continue
        beats = beats[:BEATS_EACH]

        bad = next((t for t in [hook] + beats if _BAD_FOR_TTS.search(t)), None)
        if bad:
            scartati.append(f"cifre o abbreviazioni non leggibili dal TTS: {bad}")
            continue

        existing_facts.add(_norm(hook))
        for b in beats:
            existing_facts.add(_norm(b))
        clean.append({"format": "single", "hook": hook, "facts": beats, "cta": ""})

    for motivo in scartati:
        print(f"  scartato: {motivo}")

    if not clean:
        print("Nessuno script valido generato.")
        return 0

    out_path = PIPE / f"english_scripts_{_next_file_index()}.json"
    out_path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    print(f"Creato {out_path.name} con {len(clean)} nuovi script nel formato single.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Genera anche se ci sono ancora molti script")
    args = parser.parse_args()
    sys.exit(generate(force=args.force))
