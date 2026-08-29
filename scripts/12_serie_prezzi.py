"""
Estrae la serie storica oraria dei prezzi zonali ufficiali: il dato di ingresso della fase 1.

A che serve
-----------
L'impianto a due fasi chiede di prevedere, a D-1, il prezzo orario del giorno D. Il modello
previsivo si stima su una serie storica di prezzi **ufficiali GME**, che e' cio' che un
operatore reale osserva: prevedere la propria ricostruzione significherebbe prevedere anche
il proprio errore di ricostruzione, che non e' un fenomeno di mercato.

Il costo e' quasi tutto parsing degli XML — `AWARDED_PRICE_NO` sta sulle righe accettate del
file delle offerte, quindi il file va letto per intero. Si paga una volta sola: la cache
Parquet che si scrive qui e' la stessa che serve alla fase 2, quindi questo script scalda il
terreno per il run dell'erosione.

Nota per Windows
----------------
La chiamata parallela **deve** stare sotto `if __name__ == "__main__"`, come qui: su Windows
ogni processo figlio reimporta il modulo principale, e se questo non e' un file (per esempio
codice passato da stdin) il pool muore con `BrokenProcessPool`.

Esempi
------
    .\\.venv\\Scripts\\python.exe scripts\\12_serie_prezzi.py --da 20231001 --a 20240331
    .\\.venv\\Scripts\\python.exe scripts\\12_serie_prezzi.py --da 20230101 --a 20241231 --processi 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from mgp import config, parallelo  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--da", required=True, help="primo giorno, AAAAMMGG")
    ap.add_argument("--a", required=True, help="ultimo giorno, AAAAMMGG")
    ap.add_argument("--zona", default=config.ZONA_DEFAULT)
    ap.add_argument("--processi", type=int, default=8)
    ap.add_argument("--nome", default=None, help="nome del file prodotto")
    args = ap.parse_args()

    config.assicura_cartelle()
    giorni = [d.strftime("%Y%m%d") for d in pd.date_range(args.da, args.a)]
    print(f"Serie {args.zona} da {args.da} a {args.a}: {len(giorni)} giorni.", flush=True)

    serie = parallelo.serie_prezzi(giorni, zona=args.zona,
                                   processi=args.processi, avanzamento=print, ogni=40)

    nome = args.nome or f"serie_prezzi_{args.zona}_{args.da}_{args.a}.csv"
    destinazione = config.PROCESSED_DIR / nome
    serie.to_csv(destinazione, index=False)

    print("\n" + "=" * 76)
    print(f"{len(serie):,} osservazioni orarie salvate in {destinazione}")
    print("=" * 76)
    print(serie["prezzo"].describe().round(2).to_string())
    mancanti = serie["prezzo"].isna().sum()
    print(f"\nprezzi mancanti: {mancanti}")
    print(f"prezzi <= 0    : {int((serie['prezzo'] <= 0).sum())}")
    attese = len(giorni) * 24
    print(f"osservazioni attese {attese:,} (24 per giorno), ottenute {len(serie):,}")
    if len(serie) != attese:
        print("ATTENZIONE: conteggio diverso dall'atteso — controllare i giorni di "
              "cambio ora legale, che hanno 23 o 25 ore.")


if __name__ == "__main__":
    main()
