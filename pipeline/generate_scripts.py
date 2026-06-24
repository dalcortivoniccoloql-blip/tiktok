"""
Genera automaticamente nuovi script di curiosita' con l'API di Claude,
quando quelli esistenti stanno per finire.

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
FACTS_EACH    = 5
LOW_THRESHOLD = 12     # genera se restano meno di N script non ancora usati
MODEL         = "claude-sonnet-4-6"   # accurato sui fatti


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
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY non impostata: salto la generazione.")
        return 0

    remaining = _remaining_count()
    if not force and remaining > LOW_THRESHOLD:
        print(f"Restano ancora {remaining} script: non serve generarne di nuovi.")
        return 0

    print(f"Restano {remaining} script. Genero {NEW_SCRIPTS} nuovi script...")

    try:
        import anthropic
    except ImportError:
        print("Pacchetto 'anthropic' non installato: pip install anthropic")
        return 1

    existing = _load_existing()
    existing_facts = {_norm(f) for s in existing for f in s["facts"]}
    # campione di fatti esistenti da passare al modello per evitare doppioni
    sample = [f for s in existing for f in s["facts"]]

    client = anthropic.Anthropic(api_key=key)

    prompt = (
        f"Generate exactly {NEW_SCRIPTS} groups of {FACTS_EACH} short, surprising, "
        "TRUE facts each, for a 'absurd facts' YouTube Shorts channel.\n"
        "Rules:\n"
        "- Each fact must be a single sentence, under 110 characters, in English.\n"
        "- Facts must be genuinely true and verifiable, surprising, and easy to understand.\n"
        "- Cover varied topics: animals, space, human body, history, food, geography, science.\n"
        "- Do NOT repeat or paraphrase any of the existing facts listed below.\n"
        "- Output ONLY a JSON array, no commentary. Format:\n"
        '  [{"facts": ["fact1","fact2","fact3","fact4","fact5"]}, ...]\n\n'
        "Existing facts to avoid:\n" + "\n".join(f"- {f}" for f in sample)
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    # estrai il JSON anche se incapsulato in ```json ... ```
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        print("Risposta non in formato JSON. Annullo.")
        print(text[:500])
        return 1
    new_scripts = json.loads(m.group(0))

    # dedup contro gli esistenti e tra loro
    clean = []
    for s in new_scripts:
        facts = [f.strip() for f in s.get("facts", []) if f.strip()]
        facts = [f for f in facts if _norm(f) not in existing_facts]
        for f in facts:
            existing_facts.add(_norm(f))
        if len(facts) >= FACTS_EACH:
            clean.append({"facts": facts[:FACTS_EACH]})

    if not clean:
        print("Nessun nuovo fatto unico generato.")
        return 0

    out_path = PIPE / f"english_scripts_{_next_file_index()}.json"
    out_path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    print(f"Creato {out_path.name} con {len(clean)} nuovi script.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Genera anche se ci sono ancora molti script")
    args = parser.parse_args()
    sys.exit(generate(force=args.force))
