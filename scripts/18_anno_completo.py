"""
Pipeline completa di un anno: previsione, propagazione, soglia. Un anno per esecuzione.

Replica il percorso gia' seguito sul 2024, in un solo comando invece che in quattro, con
**una** differenza: la finestra di stima e' mobile invece che crescente.

Perche' la finestra mobile
--------------------------
Con finestra crescente il costo di ristima cresce lungo l'anno: sul 2024 la stima di dicembre
ha richiesto 33 minuti contro i 12 della prima, e la fase 1 e' costata 7h14. A finestra fissa
ogni ristima costa quanto la prima, e la fase 1 scende a circa 3,5 ore.

La lunghezza e' **365 giorni**, e non meno, per una ragione che non e' di costo: la specifica
contiene una stagionalita' a ritardo 24, due coppie di armoniche settimanali e tre indicatrici
di calendario. Una finestra piu' corta stimerebbe i coefficienti del ciclo settimanale e dei
festivi su pochi episodi --- i festivi italiani sono una decina all'anno. Dodici mesi e' il
minimo che copre un ciclo completo di tutte le componenti dichiarate.

E' anche piu' realistica: un operatore non ripondera anni di storia.

Che cosa NON cambia rispetto al 2024
------------------------------------
Ordine SARIMAX congelato (D-39), le stesse sette esogene, orizzonte h = 1...24 con origine
alla fine di D-1, ristima mensile, griglia a 132 capacita', erosione netta del pavimento di
discretezza (D-30), due varianti del piano, quantile 90, soglie 10% e 20%.

Esempio
-------
    .\\.venv\\Scripts\\python.exe scripts\\18_anno_completo.py --anno 2022 --processi 8
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

from mgp import batteria as bt  # noqa: E402
from mgp import config, parallelo, previsione as pv  # noqa: E402

FINESTRA_GIORNI = 365
SOGLIE = (0.10, 0.20)
QUANTILE = 0.90
ORIGINI = ("perfetta", "previsione")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anno", required=True, help="anno da elaborare, es. 2022")
    ap.add_argument("--serie", required=True,
                    help="CSV della serie prezzi che contiene l'anno e quello precedente")
    ap.add_argument("--processi", type=int, default=8)
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--salta-previsione", action="store_true",
                    help="riusa le previsioni gia' calcolate")
    ap.add_argument("--salta-propagazione", action="store_true",
                    help="riusa la tabella di propagazione gia' calcolata")
    args = ap.parse_args()

    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    anno = args.anno
    f_previsioni = config.PROCESSED_DIR / f"previsioni_NORD_{anno}.csv"
    f_propagazione = config.PROCESSED_DIR / f"propagazione_NORD_{anno}_completa.csv"
    t_avvio = time.perf_counter()

    out("=" * 88)
    out(f"ANNO {anno} — pipeline completa")
    out("=" * 88)
    out(f"ordine {pv.ORDINE_ADOTTATO} x {pv.ORDINE_STAGIONALE}, "
        f"finestra mobile {FINESTRA_GIORNI} giorni, {len(bt.GRIGLIA_CAPACITA_MW)} capacita'")

    # ------------------------------------------------------------------- fase 1
    if args.salta_previsione and f_previsioni.exists():
        p = pd.read_csv(f_previsioni, dtype={"data": str})
        out(f"\nPrevisioni rilette da {f_previsioni.name}: {len(p):,} ore.")
    else:
        out("\n" + "-" * 88)
        out("FASE 1 — previsione a origine mobile")
        out("-" * 88)
        grezza = pd.read_csv(config.PROCESSED_DIR / args.serie, dtype={"data": str})
        serie = pv.serie_regolare(grezza)
        t0 = time.perf_counter()
        p = pv.previsioni_giornaliere(serie, da=f"{anno}0101", a=f"{anno}1231",
                                      finestra_giorni=FINESTRA_GIORNI, avanzamento=out)
        p.to_csv(f_previsioni, index=False)
        out(f"Fase 1 completata in {(time.perf_counter() - t0)/3600:.2f} ore.")

    e = p["errore"].to_numpy(dtype=float)
    out(f"\n  RMSE {np.sqrt(np.mean(e**2)):.2f}  MAE {np.mean(np.abs(e)):.2f}  "
        f"bias {np.mean(e):+.3f} EUR/MWh   copertura al 90%: "
        f"{100*float(p['dentro_ic'].mean()):.1f}%")

    # ------------------------------------------------------------------- fase 2
    if args.salta_propagazione and f_propagazione.exists():
        t = pd.read_csv(f_propagazione, dtype={"data": str, "mese": str})
        out(f"\nPropagazione riletta da {f_propagazione.name}: {len(t):,} righe.")
    else:
        out("\n" + "-" * 88)
        out("FASE 2 — propagazione sulle curve reali, due varianti di piano")
        out("-" * 88)
        t0 = time.perf_counter()
        t = parallelo.propagazione_campione(p, bt.GRIGLIA_CAPACITA_MW,
                                            processi=args.processi, avanzamento=out, ogni=50)
        t.to_csv(f_propagazione, index=False)
        out(f"Fase 2 completata in {(time.perf_counter() - t0)/3600:.2f} ore.")

    # ------------------------------------------------------------ soglia e diagnostica
    out("\n" + "-" * 88)
    out("LA SOGLIA")
    out("-" * 88)
    netti, curve = {}, {}
    for origine in ORIGINI:
        fetta = t[t["origine"] == origine].copy()
        pav = fetta.loc[fetta["potenza_mw"] == fetta["potenza_mw"].min(), "erosione_relativa"]
        out(f"  pavimento {origine:11s}: mediana {pav.median():.2%}, "
            f"90° perc. {pav.quantile(0.9):.2%}, massimo {pav.max():.2%}")
        netti[origine] = bt.sottrai_pavimento(fetta)
        g = netti[origine].groupby("potenza_mw")["erosione_netta"]
        curve[origine] = pd.DataFrame({"mediana": g.median(), "q90": g.quantile(0.9)})

    out("\n  Verifica di non-monotonia nei ricampionamenti:")
    allarmi = []
    for origine in ORIGINI:
        for soglia in SOGLIE:
            d = bt.diagnostica_monotonia(netti[origine], soglia=soglia, quantile=QUANTILE,
                                         n_boot=args.n_boot, colonna_erosione="erosione_netta")
            grave = d["quota_multipli"] > 0.05 or d["scarto_primo_ultimo_medio"] > 5.0
            allarmi.append(grave)
            out(f"    {origine:11s} {soglia:.0%}: multipli {100*d['quota_multipli']:5.1f}%, "
                f"calo mediano {100*d['discesa_massima_mediana']:5.2f} pp, "
                f"scarto ultimo-primo {d['scarto_primo_ultimo_medio']:.2f} MW"
                + ("   <-- DA ESAMINARE" if grave else ""))
    if any(allarmi):
        out("\n  ATTENZIONE: la non-monotonia non e' trascurabile. Fermarsi e decidere la")
        out("  correzione prima di usare questi K*.")

    righe = []
    for origine in ORIGINI:
        for soglia in SOGLIE:
            r = bt.bootstrap_soglia(netti[origine], soglia=soglia, quantile=QUANTILE,
                                    n_boot=args.n_boot, colonna_erosione="erosione_netta")
            riga = r.iloc[0].to_dict()
            riga.update({"anno": anno, "origine": origine, "soglia": soglia})
            righe.append(riga)
    k = pd.DataFrame(righe)[["anno", "origine", "soglia", "K_stella", "K_inf", "K_sup"]]
    out("\n" + k.round(2).to_string(index=False))
    for soglia in SOGLIE:
        a = float(k[(k.origine == "perfetta") & (k.soglia == soglia)]["K_stella"].iloc[0])
        b = float(k[(k.origine == "previsione") & (k.soglia == soglia)]["K_stella"].iloc[0])
        out(f"  soglia {soglia:.0%}: da {a:.1f} a {b:.1f} MW  ({100*(b-a)/a:+.1f}%)")

    # ------------------------------------------------- il costo dell'incertezza, due pesi
    out("\n" + "-" * 88)
    out("IL COSTO DELL'INCERTEZZA INFORMATIVA")
    out("-" * 88)
    out("Si riportano due efficienze. Quella PESATA PER PROFITTO e' il rapporto fra le somme")
    out("annue: risponde alla domanda di un investitore, ma le giornate a differenziale ampio")
    out("vi pesano di piu'. Quella EQUIPESATA e' la media delle efficienze giornaliere:")
    out("descrive la giornata tipica. Sono due domande diverse e vanno riportate entrambe.")
    out("")
    disponibili = np.sort(t["potenza_mw"].unique())
    capacita = float(disponibili[np.argmin(np.abs(disponibili - 25.0))])
    pf = t[(t.origine == "perfetta") & (t.potenza_mw == capacita)].set_index("data")
    pv_ = t[(t.origine == "previsione") & (t.potenza_mw == capacita)].set_index("data")
    perfetto = pf["profitto_price_taker"]
    realizzato = pv_["profitto_price_taker"]
    atteso = pv_["profitto_atteso"]

    eff_peso = float(realizzato.sum() / perfetto.sum())
    validi = perfetto > 1.0
    eff_equi = float((realizzato[validi] / perfetto[validi]).mean())
    out(f"  letto a {capacita:.0f} MW (regime price taker)")
    out(f"  efficienza PESATA PER PROFITTO : {100*eff_peso:5.1f}%   "
        f"(perdita {perfetto.sum() - realizzato.sum():,.0f} EUR su {perfetto.sum():,.0f})")
    out(f"  efficienza EQUIPESATA          : {100*eff_equi:5.1f}%   "
        f"({int(validi.sum())} giornate su {len(perfetto)})")
    illusione = (atteso - realizzato)
    out(f"  illusione: totale {illusione.sum():+,.0f} EUR "
        f"({100*illusione.sum()/perfetto.sum():+.1f}%), "
        f"media assoluta giornaliera {illusione.abs().mean():,.0f} EUR")
    rango = pf["correlazione_rango"]
    out(f"  correlazione di rango previsione-realta': mediana {rango.median():.3f}, "
        f"quota sopra 0,9 {100*float((rango > 0.9).mean()):.1f}%")

    spread = pf["spread_reale"]
    out(f"\n  spread giornaliero (prezzi ricostruiti): medio {spread.mean():.2f}, "
        f"mediano {spread.median():.2f}, 10° perc. {spread.quantile(.1):.2f}, "
        f"90° perc. {spread.quantile(.9):.2f} EUR/MWh")

    sintesi = pd.DataFrame([{
        "anno": anno, "capacita_lettura_mw": capacita,
        "spread_medio": float(spread.mean()), "spread_mediano": float(spread.median()),
        "volatilita_media": float(pf["spread_reale"].std()),
        "rmse_previsione": float(np.sqrt(np.mean(e ** 2))),
        "rango_mediano": float(rango.median()),
        "efficienza_pesata": eff_peso, "efficienza_equipesata": eff_equi,
        "illusione_media_assoluta": float(illusione.abs().mean()),
        **{f"K_{r['origine']}_{int(100*r['soglia'])}": r["K_stella"] for _, r in k.iterrows()},
    }])
    sintesi.to_csv(config.TABLE_DIR / f"18_sintesi_{anno}.csv", index=False)
    k.to_csv(config.TABLE_DIR / f"18_soglia_{anno}.csv", index=False)
    pd.concat({o: c for o, c in curve.items()}, axis=1).to_csv(
        config.TABLE_DIR / f"18_curva_erosione_{anno}.csv")

    out(f"\nAnno completato in {(time.perf_counter() - t_avvio)/3600:.2f} ore.")
    destinazione = config.TABLE_DIR / f"18_anno_{anno}.txt"
    destinazione.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"\nReport salvato in {destinazione}")


if __name__ == "__main__":
    main()
