"""
K* definitiva sulla griglia a 132 punti, nelle due varianti di piano.

Che cosa cambia rispetto alla stima preliminare
-----------------------------------------------
La stima di 33,7 MW del 29/08 era su griglia a 13 punti ed erosione **lorda**. Qui:

* griglia **a 132 punti** (`batteria.GRIGLIA_CAPACITA_MW`), con passo 10 MW nella regione
  dove cadono le soglie;
* erosione **netta**, cioe' col pavimento di discretezza sottratto giorno per giorno (D-30).
  Il pavimento si misura alla capacita' piu' piccola della griglia, 1 MW, che e' troppo poco
  per muovere il mercato: quello che si osserva li' e' effetto della discretezza delle curve
  ricostruite, non di mercato. D-31 — le giornate a piano vuoto contano erosione nulla — e'
  gia' applicata dentro `erosione` e agisce a monte;
* **due varianti** del piano a confronto: previsione perfetta (riferimento) e previsione
  SARIMAX (realistico). La differenza fra le due soglie e' il risultato.

Il ruolo del bootstrap, che va precisato
----------------------------------------
D-37 ha tolto il bootstrap dei giorni dall'impianto: l'incertezza del modello non viene piu'
dal ricampionamento ma dall'errore di previsione. Il bootstrap resta pero' come **strumento
inferenziale** per l'intervallo di confidenza di K*, che e' una stima campionaria come
un'altra. Sono due ruoli distinti e non in contraddizione.

La verifica di non-monotonia
----------------------------
La regola del primo attraversamento presuppone che la curva erosione-capacita' sia crescente.
Con 132 punti un sobbalzo locale del quantile dentro un ricampionamento potrebbe far scattare
l'attraversamento in anticipo e abbassare K*. Si misurano **frequenza e ampiezza** dei doppi
attraversamenti, e soprattutto di quanto cambierebbe K* prendendo l'ultimo invece del primo:
se quel numero e' trascurabile la questione non si pone, altrimenti va deciso come correggere
(sarebbe D-41) prima di usare il risultato.

Esempio
-------
    .\\.venv\\Scripts\\python.exe scripts\\17_soglia_definitiva.py
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mgp import batteria as bt  # noqa: E402
from mgp import config, grafici  # noqa: E402

SOGLIE = (0.10, 0.20)
QUANTILE = 0.90
ORIGINI = ("perfetta", "previsione")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tabella", default="propagazione_NORD_2024_completa.csv")
    ap.add_argument("--n-boot", type=int, default=1000)
    args = ap.parse_args()

    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    t = pd.read_csv(config.PROCESSED_DIR / args.tabella, dtype={"data": str, "mese": str})
    pd.set_option("display.width", 175)

    out("=" * 88)
    out(f"K* DEFINITIVA — {t['data'].nunique()} giorni, "
        f"{t['potenza_mw'].nunique()} capacita', quantile {QUANTILE:.0%}")
    out("=" * 88)

    # ------------------------------------------------- il pavimento, misurato e sottratto
    out("\nIL PAVIMENTO DI DISCRETEZZA (D-30)")
    out("Misurato a 1 MW, capacita' troppo piccola per muovere il mercato: cio' che si")
    out("osserva li' e' l'effetto della discretezza delle curve, non un effetto di mercato.")
    out("")
    netti = {}
    for origine in ORIGINI:
        fetta = t[t["origine"] == origine].copy()
        pavimento = fetta.loc[fetta["potenza_mw"] == fetta["potenza_mw"].min(),
                              "erosione_relativa"]
        out(f"  {origine:11s}: mediana {pavimento.median():.2%}, "
            f"80° perc. {pavimento.quantile(0.8):.2%}, "
            f"90° perc. {pavimento.quantile(0.9):.2%}, massimo {pavimento.max():.2%}")
        netti[origine] = bt.sottrai_pavimento(fetta)

    # ------------------------------------------------------------- la curva, per variante
    out("\n" + "=" * 88)
    out("LA CURVA EROSIONE-CAPACITA' (netta), estratto")
    out("=" * 88)
    curve = {}
    for origine in ORIGINI:
        g = netti[origine].groupby("potenza_mw")["erosione_netta"]
        curve[origine] = pd.DataFrame({"mediana": g.median(), "q90": g.quantile(0.9)})
    estratto = pd.concat({o: c for o, c in curve.items()}, axis=1)
    mostrare = [k for k in estratto.index if k in
                (1, 10, 20, 30, 50, 70, 100, 150, 200, 300, 400, 600, 800, 1500, 3000, 6000)]
    out(estratto.loc[mostrare].round(4).to_string())

    # --------------------------------------------------- la verifica di non-monotonia
    out("\n" + "=" * 88)
    out("VERIFICA DI NON-MONOTONIA NEI RICAMPIONAMENTI")
    out("=" * 88)
    out("Se la curva quantile non fosse monotona, la regola del PRIMO attraversamento")
    out("potrebbe far scattare K* in anticipo. Si misurano frequenza, ampiezza dei cali e —")
    out("il numero che decide — di quanto disterebbero primo e ultimo attraversamento.")
    out("")
    diagnostiche = []
    for origine in ORIGINI:
        for soglia in SOGLIE:
            d = bt.diagnostica_monotonia(netti[origine], soglia=soglia, quantile=QUANTILE,
                                         n_boot=args.n_boot,
                                         colonna_erosione="erosione_netta")
            d["origine"] = origine
            diagnostiche.append(d)
            oss = d["osservata"]
            out(f"  {origine:11s} soglia {soglia:.0%}")
            out(f"    curva osservata: {oss['n_attraversamenti']} attraversament"
                f"{'o' if oss['n_attraversamenti'] == 1 else 'i'}, "
                f"calo massimo {oss['discesa_massima']:.4f} "
                f"({oss['discesa_massima']*100:.2f} punti percentuali)")
            out(f"    ricampionamenti con PIU' di un attraversamento: "
                f"{100*d['quota_multipli']:.1f}%   "
                f"(massimo {d['attraversamenti_max']} attraversamenti)")
            out(f"    ricampionamenti senza attraversamento           : "
                f"{100*d['quota_senza']:.1f}%")
            out(f"    calo massimo della curva: mediana "
                f"{100*d['discesa_massima_mediana']:.2f} pp, "
                f"90° perc. {100*d['discesa_massima_q90']:.2f} pp, "
                f"massimo {100*d['discesa_massima_max']:.2f} pp")
            out(f"    scarto fra ULTIMO e PRIMO attraversamento: medio "
                f"{d['scarto_primo_ultimo_medio']:.2f} MW, "
                f"massimo {d['scarto_primo_ultimo_max']:.2f} MW")
            out(f"    K* mediana col primo attraversamento {d['K_primo']:.1f} MW, "
                f"con l'ultimo {d['K_ultimo']:.1f} MW")
            out("")

    grave = [d for d in diagnostiche
             if d["quota_multipli"] > 0.05 or d["scarto_primo_ultimo_medio"] > 5.0]
    if grave:
        out("  ATTENZIONE: la non-monotonia non e' trascurabile in almeno una combinazione.")
        out("  Fermarsi e decidere la correzione (ultimo attraversamento oppure lisciamento")
        out("  monotono) PRIMA di usare questi K*: sarebbe una decisione da registrare.")
    else:
        out("  La non-monotonia e' trascurabile: primo e ultimo attraversamento coincidono")
        out("  o distano pochi MW, e i cali della curva sono frazioni di punto percentuale.")
        out("  La regola del primo attraversamento resta valida e non serve alcuna")
        out("  correzione. Nessuna decisione nuova da registrare.")

    # ------------------------------------------------------------------------ la soglia
    out("\n" + "=" * 88)
    out(f"K* — quantile {QUANTILE:.0%}, erosione netta, intervallo di confidenza al 90%")
    out("=" * 88)
    righe = []
    for origine in ORIGINI:
        for soglia in SOGLIE:
            r = bt.bootstrap_soglia(netti[origine], soglia=soglia, quantile=QUANTILE,
                                    n_boot=args.n_boot, colonna_erosione="erosione_netta")
            riga = r.iloc[0].to_dict()
            riga.update({"origine": origine, "soglia": soglia})
            righe.append(riga)
    k = pd.DataFrame(righe)[["origine", "soglia", "K_stella", "K_inf", "K_sup",
                             "quota_senza_attraversamento", "n_giorni", "n_capacita"]]
    out(k.round(2).to_string(index=False))

    out("\nIL CONFRONTO CHE E' IL RISULTATO:")
    for soglia in SOGLIE:
        a = float(k[(k["origine"] == "perfetta") & (k["soglia"] == soglia)]["K_stella"].iloc[0])
        b = float(k[(k["origine"] == "previsione") & (k["soglia"] == soglia)]["K_stella"].iloc[0])
        out(f"  soglia {soglia:.0%}: da {a:.1f} MW con previsione perfetta a {b:.1f} MW con "
            f"previsione realistica  ({100*(b-a)/a:+.1f}%)")
    out("\nUna flotta che pianifica su previsioni reali diventa price maker PRIMA: lo stesso")
    out("errore che le costa profitto le fa anche operare in modo meno mirato, quindi con")
    out("piu' effetto sul prezzo a parita' di capacita'.")

    # -------------------------------------------------------------------------- figura
    soglie_k = {(r["origine"], r["soglia"]): r["K_stella"] for _, r in k.iterrows()}
    percorso = grafici.salva(
        grafici.figura_curva_erosione(curve, soglie=SOGLIE, soglie_k=soglie_k),
        "17_curva_erosione")

    k.to_csv(config.TABLE_DIR / "17_soglia_definitiva.csv", index=False)
    estratto.to_csv(config.TABLE_DIR / "17_curva_erosione_netta.csv")
    pd.DataFrame([{kk: vv for kk, vv in d.items() if kk != "osservata"}
                  for d in diagnostiche]).to_csv(
        config.TABLE_DIR / "17_diagnostica_monotonia.csv", index=False)
    destinazione = config.TABLE_DIR / "17_soglia_definitiva.txt"
    destinazione.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"\nFigura: {percorso}")
    print(f"Report salvato in {destinazione}")


if __name__ == "__main__":
    main()
