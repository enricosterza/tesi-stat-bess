"""
Confronto fra regimi di volatilita': 2022 estremo, 2023 e 2024 piu' tranquilli.

Che cosa e' questo confronto, e che cosa NON e'
----------------------------------------------
Non e' la stocasticita' della tesi. Quella e' la propagazione dell'errore di previsione
**dentro** ciascun anno, ed e' cio' che produce l'intervallo di confidenza di $K^*$. Qui i
tre anni sono **tre casi**, non un campione da cui inferire: con tre punti non si stima una
relazione, si osserva un ordinamento e si verifica se i meccanismi trovati su un anno
reggano sugli altri.

Le tre domande, formulate prima di guardare i tre anni insieme
--------------------------------------------------------------
1. La soglia e' governata dalla **ripidita'** della curva dove si opera, o dalla volatilita'
   del prezzo? Sul 2022 le due cose puntavano in direzioni opposte: volatilita' altissima ma
   soglia bassa.
2. Il risultato **ordinale** — conta il rango, non il livello — regge fuori dal 2024?
3. Il calo di $K^*$ dovuto alla previsione e' una **costante strutturale** attorno a un
   terzo, o dipende dal regime?

Esempio
-------
    .\\.venv\\Scripts\\python.exe scripts\\19_confronto_regimi.py
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from mgp import config, grafici  # noqa: E402

ANNI = ("2022", "2023", "2024")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anni", default=",".join(ANNI))
    args = ap.parse_args()

    anni = [a.strip() for a in args.anni.split(",")]
    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    pd.set_option("display.width", 200)

    # ------------------------------------------------------------- raccolta per anno
    righe, curve, previsioni = [], {}, {}
    for anno in anni:
        t = pd.read_csv(config.PROCESSED_DIR / f"propagazione_NORD_{anno}_completa.csv",
                        dtype={"data": str})
        p = pd.read_csv(config.PROCESSED_DIR / f"previsioni_NORD_{anno}.csv",
                        dtype={"data": str})
        k = pd.read_csv(config.TABLE_DIR / f"18_soglia_{anno}.csv")
        curve[anno] = pd.read_csv(config.TABLE_DIR / f"18_curva_erosione_{anno}.csv",
                                  header=[0, 1], index_col=0)
        previsioni[anno] = p

        disponibili = np.sort(t["potenza_mw"].unique())
        capacita = float(disponibili[np.argmin(np.abs(disponibili - 25.0))])
        pf = t[(t.origine == "perfetta") & (t.potenza_mw == capacita)].set_index("data")
        pv = t[(t.origine == "previsione") & (t.potenza_mw == capacita)].set_index("data")
        validi = pf["profitto_price_taker"] > 1.0
        pavimento = t[(t.origine == "perfetta")
                      & (t.potenza_mw == t.potenza_mw.min())]["erosione_relativa"]

        def kk(origine: str, soglia: float) -> float:
            return float(k[(k.origine == origine) & (k.soglia == soglia)]["K_stella"].iloc[0])

        e = p["errore"].to_numpy(dtype=float)
        rango = pf["correlazione_rango"]
        righe.append({
            "anno": anno,
            "spread_medio": float(pf["spread_reale"].mean()),
            "spread_mediano": float(pf["spread_reale"].median()),
            "pavimento_mediano": float(pavimento.median()),
            "pavimento_q90": float(pavimento.quantile(0.9)),
            "K_perf_10": kk("perfetta", 0.10), "K_prev_10": kk("previsione", 0.10),
            "K_perf_20": kk("perfetta", 0.20), "K_prev_20": kk("previsione", 0.20),
            "rmse": float(np.sqrt(np.mean(e ** 2))),
            "rango_mediano": float(rango.median()),
            "rango_q10": float(rango.quantile(0.10)),
            "eff_pesata": float(pv["profitto_price_taker"].sum()
                                / pf["profitto_price_taker"].sum()),
            "eff_equipesata": float((pv["profitto_price_taker"][validi]
                                     / pf["profitto_price_taker"][validi]).mean()),
            "copertura_90": float(p["dentro_ic"].mean()),
        })

    t = pd.DataFrame(righe).set_index("anno")
    for soglia in ("10", "20"):
        t[f"calo_{soglia}"] = (t[f"K_prev_{soglia}"] / t[f"K_perf_{soglia}"] - 1)

    out("=" * 100)
    out("CONFRONTO FRA REGIMI DI VOLATILITA'")
    out("=" * 100)
    out("I tre anni sono tre CASI, non un campione: con tre punti non si stima una relazione,")
    out("si osserva un ordinamento e si verifica se i meccanismi reggano. La stocasticita'")
    out("della tesi resta la propagazione dell'errore DENTRO ciascun anno.")
    out("")
    ordinati = t.sort_values("spread_medio", ascending=False)
    out(ordinati[["spread_medio", "spread_mediano", "pavimento_mediano", "pavimento_q90",
                  "rmse", "rango_mediano", "copertura_90"]].round(4).to_string())
    out("")
    out(ordinati[["K_perf_10", "K_prev_10", "calo_10", "K_perf_20", "K_prev_20", "calo_20",
                  "eff_pesata", "eff_equipesata"]].round(4).to_string())

    # ------------------------------------------------------- 1. ripidita' o volatilita'?
    out("\n" + "=" * 100)
    out("1. LA SOGLIA SEGUE LA RIPIDITA' DELLA CURVA O LA VOLATILITA' DEL PREZZO?")
    out("=" * 100)
    o = t.sort_values("spread_medio", ascending=False)
    out("  ordinamento per spread    : " + " > ".join(
        f"{a} ({v:.1f})" for a, v in o["spread_medio"].items()))
    out("  ordinamento per pavimento : " + " > ".join(
        f"{a} ({100*v:.2f}%)" for a, v in o["pavimento_mediano"].items()))
    out("  ordinamento per K* (10%)  : " + " < ".join(
        f"{a} ({v:.1f} MW)" for a, v in o["K_perf_10"].items()))
    out("")
    out("  Il pavimento a 1 MW e' un termometro della ripidita': misura di quanto si muove il")
    out("  prezzo quando si aggiunge una capacita' troppo piccola per contare economicamente.")
    out("")
    r_sp = stats.pearsonr(t["spread_medio"], t["K_perf_10"])
    r_pv = stats.pearsonr(t["pavimento_mediano"], t["K_perf_10"])
    out(f"  correlazione K* ~ spread    : {r_sp.statistic:+.3f}")
    out(f"  correlazione K* ~ pavimento : {r_pv.statistic:+.3f}")
    out("  ATTENZIONE: con TRE punti questi coefficienti non distinguono nulla, e spread e")
    out("  pavimento sono a loro volta perfettamente co-ordinati fra questi tre anni. La")
    out("  correlazione non separa le due spiegazioni: e' il MECCANISMO a farlo, e il")
    out("  pavimento e' l'unico dei due che misuri direttamente cio' che K* misura.")
    out("")
    out("  Erosione netta a capacita' fissate (mediana fra le giornate):")
    fisse = [50.0, 100.0, 200.0, 400.0]
    conf = pd.DataFrame({
        a: [float(curve[a][("perfetta", "mediana")].reindex([k]).iloc[0]) for k in fisse]
        for a in anni}, index=[f"{int(k)} MW" for k in fisse])
    out("  " + conf.round(4).to_string().replace("\n", "\n  "))
    out("  A parita' di capacita' installata l'erosione e' molto maggiore nell'anno a curva")
    out("  piu' ripida: e' la stessa cosa che K* dice, letta all'incontrario.")

    # -------------------------------------------------------------- 2. il rango regge?
    out("\n" + "=" * 100)
    out("2. IL RISULTATO ORDINALE REGGE FUORI DAL 2024?")
    out("=" * 100)
    out(t[["rmse", "rango_mediano", "rango_q10", "eff_pesata", "eff_equipesata"]]
        .round(4).to_string())
    out("")
    out(f"  RMSE varia di {t['rmse'].max()/t['rmse'].min():.1f} volte fra gli anni "
        f"({t['rmse'].min():.2f} - {t['rmse'].max():.2f} EUR/MWh)")
    out(f"  la correlazione di rango mediana varia di "
        f"{100*(t['rango_mediano'].max()/t['rango_mediano'].min()-1):.1f}% "
        f"({t['rango_mediano'].min():.3f} - {t['rango_mediano'].max():.3f})")
    out("")
    out("  E' la verifica piu' forte del risultato ordinale: l'errore in livello cambia di")
    out("  un fattore tre fra i regimi, l'ordinamento delle ore quasi non cambia.")
    out("")
    out("  L'efficienza pero' NON e' funzione della sola mediana del rango:")
    for a in t.index:
        out(f"    {a}: rango mediano {t.loc[a,'rango_mediano']:.3f}, "
            f"10 perc. {t.loc[a,'rango_q10']:.3f}, "
            f"efficienza equipesata {100*t.loc[a,'eff_equipesata']:.1f}%")
    out("  Il 2022 e il 2023 hanno mediana quasi identica ed efficienza molto diversa: conta")
    out("  anche la CODA BASSA della distribuzione del rango, cioe' quante giornate il modello")
    out("  sbaglia l'ordinamento in modo grave, non solo quanto lo azzecca di norma.")

    # ----------------------------------------------------- 3. il calo e' una costante?
    out("\n" + "=" * 100)
    out("3. IL CALO DI K* DOVUTO ALLA PREVISIONE E' UNA COSTANTE STRUTTURALE?")
    out("=" * 100)
    cali = t[["calo_10", "calo_20"]] * 100
    out(cali.round(1).to_string())
    tutti = np.concatenate([cali["calo_10"].to_numpy(), cali["calo_20"].to_numpy()])
    out(f"\n  sei valori, da {tutti.min():.1f}% a {tutti.max():.1f}%, "
        f"mediana {np.median(tutti):.1f}%")
    entro_anno = float(np.abs(cali["calo_10"] - cali["calo_20"]).max())
    fra_anni = float(cali["calo_10"].max() - cali["calo_10"].min())
    out(f"  escursione DENTRO un anno (fra le due soglie): fino a {entro_anno:.1f} punti")
    out(f"  escursione FRA anni (a soglia 10%)           : {fra_anni:.1f} punti")
    out("")
    out("  Con due punti sembrava una costante attorno a un terzo. Con tre non lo e': il calo")
    out("  sta fra un quarto e un terzo, e varia DENTRO un anno quanto varia fra anni. Va")
    out("  riportato come intervallo, non come costante.")

    # ------------------------------------------- la calibrazione e il ritardo di regime
    out("\n" + "=" * 100)
    out("UN'OSSERVAZIONE SULLA CALIBRAZIONE: LA FINESTRA MOBILE RITARDA SUL REGIME")
    out("=" * 100)
    out("La copertura al 90% nominale non e' ne' stabile ne' monotona nella volatilita':")
    for a in anni:
        out(f"    {a}: {100*t.loc[a,'copertura_90']:5.1f}%")
    out("")
    out("  L'ipotesi: la finestra di stima e' di 365 giorni, quindi ogni modello dichiara")
    out("  l'incertezza dell'anno PRECEDENTE. Il 2022 e' stimato su un 2021 tranquillo e")
    out("  risulta troppo sicuro; il 2023 su un 2022 estremo e risulta troppo prudente.")
    out("  Se e' vero, la copertura deve MIGLIORARE lungo l'anno, man mano che la finestra")
    out("  si riempie di dati dello stesso regime.")
    out("")
    for a in anni:
        p = previsioni[a].copy()
        p["mese"] = p["data"].str[4:6]
        per_mese = p.groupby("mese")["dentro_ic"].mean() * 100
        out(f"    {a}: " + " ".join(f"{m}:{v:4.0f}" for m, v in per_mese.items()))
    out("")
    out("  Se lo schema si vede, e' un effetto del disegno e non del mercato, e va dichiarato:")
    out("  gli intervalli di previsione sono affidabili solo a regime stabile.")

    # ---------------------------------------------------------------------- prodotti
    figura = grafici.figura_confronto_regimi(t, curve)
    percorso = grafici.salva(figura, "19_confronto_regimi")
    t.to_csv(config.TABLE_DIR / "19_confronto_regimi.csv")
    destinazione = config.TABLE_DIR / "19_confronto_regimi.txt"
    destinazione.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"\nFigura: {percorso}")
    print(f"Report salvato in {destinazione}")


if __name__ == "__main__":
    main()
