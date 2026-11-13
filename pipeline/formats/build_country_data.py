"""Rigenera pipeline/formats/data/countries.json (uso raro, in locale).

Fonti (scaricate a mano, NON a ogni pubblicazione):
  - mledoze/countries (ODbL): nome, codice, capitale, superficie km2
    https://raw.githubusercontent.com/mledoze/countries/master/countries.json
  - World Bank SP.POP.TOTL, ultimo valore disponibile per paese
    https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=400&mrnev=1
Le bandiere stanno in assets/flags/<cca2>.png (flagcdn.com, w640, dominio pubblico).

Uso: py pipeline/formats/build_country_data.py <mledoze.json> <wbpop.json>
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "data" / "countries.json"


def main(mledoze_p: str, wb_p: str) -> None:
    m = json.loads(Path(mledoze_p).read_text(encoding="utf-8"))
    wb = json.loads(Path(wb_p).read_text(encoding="utf-8"))[1]
    pop = {r["countryiso3code"]: r["value"] for r in wb if r["value"]}
    out = []
    for c in m:
        if not c.get("unMember"):
            continue                       # solo i 193 stati ONU: niente territori ambigui
        caps = c.get("capital") or []
        out.append({
            "cca2": c["cca2"].lower(),
            "name": c["name"]["common"],
            "capital": caps[0] if len(caps) == 1 else None,   # piu' capitali = niente domanda
            "area_km2": c.get("area"),
            "population": pop.get(c["cca3"]),
            "region": c.get("region"),
        })
    out.sort(key=lambda x: x["name"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} paesi -> {OUT}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
