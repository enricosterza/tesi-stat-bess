"""
Sceglie l'ordine (p, q) del SARIMAX confrontando i candidati sull'anno di addestramento.

La selezione si fa **una volta sola** e l'ordine vincitore resta poi congelato per tutto il
periodo di valutazione: e' cio' che distingue un modello dichiarato da un iperparametro
riottimizzato a ogni passo. La parte stagionale (0,1,1)_24 non entra nel confronto, perche'
non e' una scelta ma una lettura del correlogramma (si veda `mgp.previsione`).

Esempio
-------
    .\\.venv\\Scripts\\python.exe scripts\\13_seleziona_ordine.py --addestramento 2023
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
    ap.add_argument("--addestramento", default="2023", help="anno di addestramento")
    ap.add_argument("--maxiter", type=int, default=50)
    args = ap.parse_args()

    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    grezza = pd.read_csv(config.PROCESSED_DIR / args.serie, dtype={"data": str})
    serie = pv.serie_regolare(grezza)

    out("=" * 84)
    out("SERIE REGOLARIZZATA")
    out("=" * 84)
    modificati = serie[serie["modificato"]]
    out(f"osservazioni: {len(serie):,}   giorni: {serie['data'].nunique()}")
    out(f"slot costruiti o fusi per il cambio dell'ora: {len(modificati)}")
    for _, r in modificati.iterrows():
        out(f"    {r['data']} slot {int(r['slot'])}  ->  {r['prezzo']:.2f} EUR/MWh")
    ore = serie.groupby("data").size()
    out(f"tutti i giorni hanno 24 slot: {bool((ore == 24).all())}")

    addestramento = serie[serie["data"].str.startswith(args.addestramento)]
    y = addestramento["prezzo"].to_numpy(dtype=float)
    esogene = pv.regressori(addestramento["istante"])
    out(f"\naddestramento {args.addestramento}: {len(y):,} ore, "
        f"{esogene.shape[1]} regressori esogeni ({', '.join(esogene.columns)})")

    out("\n" + "=" * 84)
    out(f"CONFRONTO DEI CANDIDATI — parte stagionale fissata a {pv.ORDINE_STAGIONALE}")
    out("=" * 84)
    out("L'AIC premia l'adattamento e penalizza i parametri. Il test di Ljung-Box sui")
    out("residui a lag 48 dice se resta autocorrelazione non modellata: p piccolo = resta.")
    out("")

    righe = []
    for p, q in pv.ORDINI_CANDIDATI:
        ordine = (p, 1, q)
        t0 = time.perf_counter()
        try:
            ris = pv.stima(y, esogene, ordine, maxiter=args.maxiter)
            durata = time.perf_counter() - t0
            from statsmodels.stats.diagnostic import acorr_ljungbox
            lb = acorr_ljungbox(ris.resid[48:], lags=[48], return_df=True)
            righe.append({
                "ordine": f"({p},1,{q})",
                "aic": float(ris.aic),
                "bic": float(ris.bic),
                "logL": float(ris.llf),
                "n_par": int(len(ris.params)),
                "sigma2": float(ris.params[-1]) if "sigma2" in ris.param_names[-1] else np.nan,
                "ljung_box_p": float(lb["lb_pvalue"].iloc[0]),
                "convergenza": bool(ris.mle_retvals.get("converged", False)),
                "secondi": durata,
            })
            out(f"  ({p},1,{q}) x {pv.ORDINE_STAGIONALE}   AIC {ris.aic:12.2f}   "
                f"BIC {ris.bic:12.2f}   {durata:6.1f} s   "
                f"convergenza {righe[-1]['convergenza']}")
        except Exception as errore:                          # noqa: BLE001
            out(f"  ({p},1,{q})  STIMA FALLITA: {type(errore).__name__}: {errore}")

    if not righe:
        out("\nNessun candidato stimato: fermarsi e capire perche'.")
        sys.exit(1)

    t = pd.DataFrame(righe).sort_values("aic").reset_index(drop=True)
    out("\n" + t.round(3).to_string(index=False))

    vincitore = t.iloc[0]
    out("\n" + "=" * 84)
    out(f"ORDINE SCELTO: {vincitore['ordine']} x {pv.ORDINE_STAGIONALE}")
    out("=" * 84)
    out(f"AIC {vincitore['aic']:.2f}, inferiore di {t['aic'].iloc[1] - vincitore['aic']:.2f} "
        f"al secondo classificato ({t['ordine'].iloc[1]}).")
    out(f"Ljung-Box a lag 48 sui residui: p = {vincitore['ljung_box_p']:.4f}")
    if vincitore["ljung_box_p"] < 0.05:
        out("  p sotto 0,05: resta autocorrelazione non modellata. Non e' di per se' un")
        out("  difetto fatale su 8.760 osservazioni, dove il test rifiuta per scostamenti")
        out("  minimi, ma va dichiarato e ripreso nell'analisi dei residui (fase 2 del")
        out("  disegno statistico, dove la struttura dell'errore e' l'oggetto e non il")
        out("  disturbo).")
    out("\nQuesto ordine va ora CONGELATO per tutto il periodo di valutazione.")

    destinazione = config.TABLE_DIR / "13_selezione_ordine.txt"
    destinazione.write_text(buffer.getvalue(), encoding="utf-8")
    t.to_csv(config.TABLE_DIR / "13_selezione_ordine.csv", index=False)
    print(f"\nReport salvato in {destinazione}")


if __name__ == "__main__":
    main()
