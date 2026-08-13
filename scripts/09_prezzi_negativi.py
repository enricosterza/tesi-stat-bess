"""
Diagnostica dei prezzi di equilibrio negativi.

A che cosa serve
----------------
Il modello della batteria, a ciclo chiuso e con prezzi positivi, dipende solo dal
PRODOTTO dei rendimenti di carica e scarica: come la perdita di ciclo sia ripartita
fra le due direzioni non cambia nulla. La ripartizione conta invece quando il prezzo
e' NEGATIVO nelle ore di carica, perche' li' prelevare energia e' remunerato e i due
rendimenti entrano separatamente nella funzione obiettivo.

Questo script misura quanto il caso sia frequente e dove si collochi, cosi' da
decidere con i numeri se la convenzione adottata (perdita ripartita in parti uguali,
`config.rendimenti_da_ciclo`, D-32) tocchi i risultati oppure no.

E' solo diagnostica: non modifica la logica dell'efficienza ne' alcun risultato.

Uso
---
    # su una serie gia' prodotta da 03_valida_mese.py
    .\.venv\Scripts\python.exe scripts\09_prezzi_negativi.py --serie 202501

    # su piu' serie insieme (per esempio il trimestre a quarto d'ora)
    .\.venv\Scripts\python.exe scripts\09_prezzi_negativi.py --serie 202510,202511,202512

    # sui prezzi ufficiali invece che sui ricostruiti
    .\.venv\Scripts\python.exe scripts\09_prezzi_negativi.py --serie 202501 --colonna prezzo_ufficiale
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp import config, curve  # noqa: E402


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def carica_serie(etichette: list[str]) -> pd.DataFrame:
    """
    Legge e concatena le serie per periodo prodotte dalla validazione.

    Il file atteso e' `data/processed/validazione_<etichetta>_NORD.csv`, che contiene
    una riga per asta con il prezzo ricostruito, quello ufficiale e la granularita'.
    """
    pezzi = []
    for etichetta in etichette:
        percorso = config.PROCESSED_DIR / f"validazione_{etichetta}_NORD.csv"
        if not percorso.exists():
            raise FileNotFoundError(
                f"Serie non trovata: {percorso}. Va prodotta prima con "
                f"scripts/03_valida_mese.py --mese {etichetta}"
            )
        pezzi.append(pd.read_csv(percorso, dtype={"data": str}))
    return pd.concat(pezzi, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serie", default="202501",
                        help="etichette delle serie di validazione, separate da virgola")
    parser.add_argument("--colonna", default="prezzo",
                        choices=["prezzo", "prezzo_ufficiale"],
                        help="prezzi da esaminare: ricostruiti (default) o ufficiali")
    parser.add_argument("--etichetta", help="nome per il file prodotto")
    args = parser.parse_args()

    etichette = args.serie.split(",")
    nome = args.etichetta or "_".join(etichette)

    config.assicura_cartelle()
    pd.set_option("display.width", 140)
    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo, flush=True)
        buffer.write(testo + "\n")

    serie = carica_serie(etichette)
    esito = curve.prezzi_negativi(serie, colonna=args.colonna)

    out(_sezione(f"PREZZI NEGATIVI — serie {', '.join(etichette)} "
                 f"(colonna: {args.colonna})"))
    out("Con prezzi positivi e ciclo chiuso conta solo il prodotto dei rendimenti, quindi")
    out("la ripartizione della perdita fra carica e scarica e' irrilevante. Diventa")
    out("rilevante con prezzi negativi nelle ore di carica, dove prelevare e' remunerato.")

    out(f"\nPeriodi esaminati        : {esito['n_periodi']}")
    out(f"Periodi a prezzo negativo: {esito['n_negativi']} "
        f"({esito['quota_negativi']:.2f}%)")
    out(f"Giornate                 : {esito['n_giorni']}, di cui con almeno un "
        f"periodo negativo: {esito['n_giorni_con_negativi']}")
    out(f"Prezzo minimo osservato  : {esito['prezzo_minimo']:.2f} €/MWh")

    if esito["n_negativi"] == 0:
        out("\nNessun prezzo negativo nel campione: la ripartizione della perdita di ciclo")
        out("non tocca questi risultati. Resta una verifica da rifare sull'estensione del")
        out("campione, dove i mesi centrali dell'anno possono comportarsi diversamente.")
    else:
        out(_sezione("DOVE SI COLLOCANO"))
        out("Per ora del giorno (solo le ore con almeno un periodo negativo):")
        per_ora = esito["per_ora"]
        out(per_ora[per_ora["negativi"] > 0].round(2).to_string())
        out("\nPer mese:")
        out(esito["per_mese"].round(2).to_string())
        out("\nPer stagione:")
        out(esito["per_stagione"].round(2).to_string())
        out("\nSe si concentrano nelle ore centrali della giornata l'interpretazione e' la")
        out("produzione fotovoltaica in eccesso, ed e' il caso in cui la ripartizione della")
        out("perdita di ciclo va discussa (vedi diario, D-32).")

    percorso = config.TABLE_DIR / f"09_prezzi_negativi_{nome}.txt"
    percorso.write_text(buffer.getvalue(), encoding="utf-8")
    out(_sezione("FILE PRODOTTI"))
    out(f"  {percorso}")


if __name__ == "__main__":
    main()
