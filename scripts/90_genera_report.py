"""
Genera il documento Word del report settimanale per il relatore.

Il testo si scrive in Markdown dentro `docs/report/` (un file per settimana, nominato
`AAAA-MM-GG_report.md`); questo script lo converte in `.docx` dentro `output/report/`,
pronto da allegare all'email o da portare al ricevimento.

Esecuzione
----------
    # converte il report piu' recente presente in docs/report/
    .\\.venv\\Scripts\\python.exe scripts\\90_genera_report.py

    # converte una settimana specifica
    .\\.venv\\Scripts\\python.exe scripts\\90_genera_report.py --data 2026-08-03

    # converte tutti i report presenti
    .\\.venv\\Scripts\\python.exe scripts\\90_genera_report.py --tutti
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp import config, report  # noqa: E402

REPORT_DIR = config.DOCS_DIR / "report"
OUTPUT_REPORT_DIR = config.OUTPUT_DIR / "report"


def report_disponibili() -> list[Path]:
    """Elenca i report Markdown presenti, dal piu' vecchio al piu' recente."""
    return sorted(p for p in REPORT_DIR.glob("*_report.md") if not p.name.startswith("_"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", help="data del report da convertire, formato AAAA-MM-GG")
    parser.add_argument("--tutti", action="store_true", help="converte tutti i report presenti")
    args = parser.parse_args()

    disponibili = report_disponibili()
    if not disponibili:
        print(f"Nessun report trovato in {REPORT_DIR}.")
        print("Crea un file 'AAAA-MM-GG_report.md' partendo da '_modello.md'.")
        return

    if args.tutti:
        da_convertire = disponibili
    elif args.data:
        da_convertire = [p for p in disponibili if p.name.startswith(args.data)]
        if not da_convertire:
            print(f"Nessun report per la data {args.data}. Disponibili: "
                  f"{[p.name[:10] for p in disponibili]}")
            return
    else:
        da_convertire = [disponibili[-1]]

    for sorgente in da_convertire:
        destinazione = OUTPUT_REPORT_DIR / f"{sorgente.stem.replace('_report', '')}_Report_tesi.docx"
        report.markdown_to_docx(sorgente, destinazione)
        print(f"{sorgente.name}  ->  {destinazione}")


if __name__ == "__main__":
    main()
