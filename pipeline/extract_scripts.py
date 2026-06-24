import json
import re
from pathlib import Path
from docx import Document


def load_english_scripts(json_path) -> list[dict]:
    """
    Carica gli script inglesi da tutti i file english_scripts*.json nella stessa
    cartella, in ordine alfabetico, e li rinumera in sequenza (1..N).
    Cosi' per aggiungere nuove curiosita' basta creare un nuovo file
    english_scripts_3.json, _4.json, ecc.
    """
    folder  = Path(json_path).parent
    files   = sorted(folder.glob("english_scripts*.json"))
    scripts: list[dict] = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            batch = json.load(fh)
        print(f"  + {len(batch)} script da {f.name}")
        scripts.extend(batch)

    # rinumera sequenzialmente
    for i, s in enumerate(scripts, 1):
        s["number"] = i

    print(f"  Totale: {len(scripts)} script inglesi")
    return scripts

_SCRIPT_HEADER = re.compile(r"^Script\s+(\d+)\s*$", re.IGNORECASE)
_NUMBERED_FACT = re.compile(r"^\d+\.\s+(.+)$")


def extract_scripts_from_docx(docx_path: Path) -> list[dict]:
    """
    Legge un docx e ritorna lista di {'number': int, 'facts': [str, ...]}.
    Funziona sia con fatti numerati ('1. testo') che non numerati.
    """
    doc = Document(str(docx_path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    scripts: list[dict] = []
    current_num: int | None = None
    current_facts: list[str] = []

    for para in paragraphs:
        m = _SCRIPT_HEADER.match(para)
        if m:
            # salva script precedente
            if current_num is not None and current_facts:
                scripts.append({"number": current_num, "facts": current_facts[:5]})
            current_num = int(m.group(1))
            current_facts = []
        elif current_num is not None and len(current_facts) < 5:
            # prova a rimuovere numerazione ("1. ", "2. " ecc.)
            numbered = _NUMBERED_FACT.match(para)
            fact = numbered.group(1) if numbered else para
            current_facts.append(fact)

    # salva l'ultimo script
    if current_num is not None and current_facts:
        scripts.append({"number": current_num, "facts": current_facts[:5]})

    return scripts


def load_all_scripts(docx_paths: list) -> list[dict]:
    """
    Carica script da più docx, rinumerando sequenzialmente per evitare conflitti.
    Es: primo file ha script 1-20, secondo file inizia da 21.
    """
    all_scripts: list[dict] = []
    global_offset = 0

    for path in docx_paths:
        if not Path(path).exists():
            print(f"  File non trovato: {path}")
            continue
        loaded = extract_scripts_from_docx(Path(path))
        # riassegna numeri sequenziali partendo dall'offset
        for i, s in enumerate(loaded):
            all_scripts.append({
                "number": global_offset + i + 1,
                "facts":  s["facts"],
            })
        print(f"  Caricati {len(loaded)} script da {Path(path).name} "
              f"(#{global_offset + 1}–#{global_offset + len(loaded)})")
        global_offset += len(loaded)

    return all_scripts


def load_scripts() -> list[dict]:
    """Carica gli script secondo la lingua configurata (en = JSON, it = docx)."""
    from config import LANGUAGE, ENGLISH_SCRIPTS, SCRIPTS_DOCX
    if LANGUAGE == "en":
        return load_english_scripts(ENGLISH_SCRIPTS)
    return load_all_scripts(SCRIPTS_DOCX)


def print_scripts_summary(scripts: list[dict]) -> None:
    print(f"\nScript totali: {len(scripts)}")
    for s in scripts:
        preview = s["facts"][0][:60] + "..." if len(s["facts"][0]) > 60 else s["facts"][0]
        print(f"  #{s['number']:>3}  {preview}")
