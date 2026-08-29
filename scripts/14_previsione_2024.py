"""
Fase 1 sul 2024: previsione a origine mobile del prezzo orario, un giorno per volta.

Per ogni giorno D del 2024 si prevedono le 24 ore usando solo dati fino alla fine di D-1,
con l'ordine congelato (D-39). I coefficienti si ristimano all'inizio di ogni mese; negli
altri giorni lo stato assorbe il giorno appena osservato senza toccare i coefficienti.

Si salvano previsione puntuale, **errore standard** e intervallo di previsione ora per ora.
L'errore standard e' il dato piu' utile dei tre: da esso si ricava un intervallo a qualunque
livello, e soprattutto permette di confrontare l'errore che il modello **dichiara** con
quello che **realizza** — cioe' di stabilire se il SARIMAX sa quanto sbaglia.

Esempio
-------
    .\\.venv\\Scripts\\python.exe scripts\\14_previsione_2024.py
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mgp import config, previsione as pv  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serie", default="serie_prezzi_NORD_2023_2024.csv")
    ap.add_argument("--da", default="20240101")
    ap.add_argument("--a", default="20241231")
    ap.add_argument("--alpha", type=float, default=0.10,
                    help="0,10 da' un intervallo di previsione al 90%%")
    ap.add_argument("--nome", default="previsioni_NORD_2024.csv")
    args = ap.parse_args()

    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    grezza = pd.read_csv(config.PROCESSED_DIR / args.serie, dtype={"data": str})
    serie = pv.serie_regolare(grezza)

    out("=" * 84)
    out(f"PREVISIONE A ORIGINE MOBILE — {args.da} / {args.a}")
    out("=" * 84)
    out(f"ordine congelato: {pv.ORDINE_ADOTTATO} x {pv.ORDINE_STAGIONALE}")
    out(f"intervallo di previsione al {100 * (1 - args.alpha):.0f}%")
    out("")

    t0 = time.perf_counter()
    p = pv.previsioni_giornaliere(serie, da=args.da, a=args.a, alpha=args.alpha,
                                  avanzamento=out)
    durata = time.perf_counter() - t0

    destinazione = config.PROCESSED_DIR / args.nome
    p.to_csv(destinazione, index=False)

    out("\n" + "=" * 84)
    out("ESITO COMPLESSIVO")
    out("=" * 84)
    out(f"completato in {durata / 60:.1f} minuti — {len(p):,} ore previste, "
        f"{p['data'].nunique()} giorni, {int(p['ristimato'].sum() / 24)} ristime")
    e = p["errore"].to_numpy(dtype=float)
    out(f"\nErrore (prezzo reale meno previsione), EUR/MWh:")
    out(f"  RMSE                {np.sqrt(np.mean(e ** 2)):8.2f}")
    out(f"  MAE                 {np.mean(np.abs(e)):8.2f}")
    out(f"  bias medio          {np.mean(e):8.2f}")
    out(f"  mediana             {np.median(e):8.2f}")
    out(f"  dev. std            {np.std(e, ddof=1):8.2f}")
    out(f"  minimo / massimo    {e.min():8.2f} / {e.max():.2f}")

    out(f"\nCalibrazione dell'intervallo dichiarato:")
    copertura = float(p["dentro_ic"].mean())
    out(f"  copertura osservata {100 * copertura:6.1f}%   (nominale "
        f"{100 * (1 - args.alpha):.0f}%)")
    out(f"  ampiezza mediana    {p['ampiezza_ic'].median():8.2f} EUR/MWh")
    if copertura < (1 - args.alpha) - 0.05:
        out("  L'intervallo e' TROPPO STRETTO: il modello sottostima la propria incertezza.")
    elif copertura > (1 - args.alpha) + 0.05:
        out("  L'intervallo e' TROPPO LARGO: il modello sovrastima la propria incertezza.")
    else:
        out("  Calibrazione ragionevole.")

    out(f"\nErrore per orizzonte (media sull'anno):")
    per_h = p.groupby("orizzonte")["errore"].agg(
        rmse=lambda s: float(np.sqrt(np.mean(s ** 2))),
        mae=lambda s: float(np.mean(np.abs(s))),
        bias="mean")
    out(per_h.round(2).to_string())

    salvato = config.TABLE_DIR / "14_previsione_2024.txt"
    salvato.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"\nPrevisioni salvate in {destinazione}")
    print(f"Report salvato in {salvato}")


if __name__ == "__main__":
    main()
