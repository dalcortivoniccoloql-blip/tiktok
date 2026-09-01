# Durata: LEGATO-A:P09 — blocca l'invariante fra la soglia di rifornimento e i due cron.
#
# Perche' esiste: il 2026-08-26 il canale si e' fermato 5 giorni perche' la coda
# era finita e nessuno se n'era accorto. La riparazione del 31/08 ha reso VISIBILE
# la coda vuota (run rosso), ma non ha guardato il piano sopra: topup.yml girava
# UNA VOLTA A SETTIMANA con una soglia di 12, mentre publish.yml consuma 21 script
# a settimana. Con 13 script rimasti il lunedi', il job diceva "non serve" e la
# coda finiva il giovedi'. Stessa famiglia di guasto, un piano piu' su.
#
# L'invariante: al momento di un controllo, se il job decide di NON rifornire, la
# coda deve bastare fino al controllo successivo. Caso peggiore = soglia + 1
# script rimasti, quindi serve  soglia >= pubblicazioni_al_giorno * giorni_fra_controlli.
#
# Gira senza rete, senza dipendenze, senza chiave.
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipeline"))
WF = REPO / ".github" / "workflows"


def _cron(nome: str) -> list[list[str]]:
    testo = (WF / nome).read_text(encoding="utf-8")
    righe = re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', testo, re.MULTILINE)
    # Se i cron ci sono ma commentati, questo test sta girando dalla copia su
    # Drive, dove publish.yml tiene il cron commentato di proposito (divergenza
    # voluta, vedi P09/CLAUDE.md). Non e' un guasto: e' il posto sbagliato.
    assert righe, (
        f"nessun cron ATTIVO trovato in {nome}. "
        + ("Ci sono cron COMMENTATI: stai quasi certamente girando dalla copia su "
           "Drive, dove publish.yml tiene il cron disattivato di proposito "
           "(divergenza voluta, vedi P09/CLAUDE.md). Non e' un guasto, e' il posto "
           "sbagliato: lancia questo test dal repo git (dev/tiktok), che e' l'unica "
           "configurazione che gira davvero."
           if "cron:" in testo else
           "Il file non contiene nessuna riga cron: schedulazione rimossa?")
    )
    return [r.split() for r in righe]


def _ogni_quanti_giorni(campi: list[list[str]], nome: str) -> float:
    """Ogni quanti giorni gira il workflow. Riconosce solo le due forme in uso:
    giornaliero (dom='*' e dow='*') e settimanale (dow = un giorno singolo).
    Qualsiasi altra forma fa FALLIRE il test invece di passarlo a vuoto: una
    schedulazione che questo test non sa leggere non e' una schedulazione sicura."""
    giornalieri = settimanali = 0
    for c in campi:
        assert len(c) == 5, f"{nome}: cron con {len(c)} campi invece di 5: {' '.join(c)}"
        dom, mese, dow = c[2], c[3], c[4]
        assert mese == "*", f"{nome}: cron su un mese specifico, forma non gestita: {' '.join(c)}"
        if dom == "*" and dow == "*":
            giornalieri += 1
        elif dom == "*" and dow.isdigit():
            settimanali += 1
        else:
            raise AssertionError(
                f"{nome}: forma di cron non gestita da questo test: {' '.join(c)}. "
                "Aggiorna il test PRIMA di cambiare la schedulazione."
            )
    assert not (giornalieri and settimanali), f"{nome}: cron misti giornalieri+settimanali"
    if giornalieri:
        return 1 / giornalieri
    return 7 / settimanali


pub_ogni = _ogni_quanti_giorni(_cron("publish.yml"), "publish.yml")
top_ogni = _ogni_quanti_giorni(_cron("topup.yml"), "topup.yml")
pub_al_giorno = 1 / pub_ogni

import generate_scripts as g  # noqa: E402

servono = pub_al_giorno * top_ogni

print(f"publish.yml : {pub_al_giorno:g} pubblicazioni al giorno")
print(f"topup.yml   : un controllo ogni {top_ogni:g} giorni")
print(f"consumo fra due controlli : {servono:g} script")
print(f"LOW_THRESHOLD             : {g.LOW_THRESHOLD}")

assert g.LOW_THRESHOLD >= servono, (
    f"LOW_THRESHOLD={g.LOW_THRESHOLD} non copre i {servono:g} script consumati fra due "
    f"controlli di topup.yml: la coda puo' finire senza che nessun job provi a "
    f"rifornirla (guasto del 2026-08-26). Alza la soglia o infittisci il cron di topup."
)

margine = g.LOW_THRESHOLD / pub_al_giorno
print(f"\nOK: alla soglia restano {margine:g} giorni di pubblicazioni per rifornire.")
assert margine >= 2, f"solo {margine:g} giorni di margine: troppo poco per un retry"
print("TUTTI I CONTROLLI PASSATI.")
