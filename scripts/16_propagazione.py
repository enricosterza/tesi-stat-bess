"""
Punto 3: come l'errore di previsione si propaga al piano della batteria e al risultato.

La domanda
----------
Quanto valore si perde perche' la batteria pianifica su prezzi previsti invece che veri? E
soprattutto: **quale dei due meccanismi opposti prevale**?

* la **contrazione dello spread** dovrebbe peggiorare le cose. La fase 1 ha mostrato che il
  modello prevede spread in 40-80 EUR/MWh quando il reale va da 20 a 158, e li sottostima nel
  65% delle giornate. Se la batteria vede quasi la stessa opportunita' ogni giorno,
  pianifichera' quasi allo stesso modo e perdera' le giornate eccezionali, che sono quelle
  che fanno il margine annuo.
* il **vincolo di ammissibilita'** dovrebbe proteggere. Un errore di previsione puo' spostare
  *quando* la batteria opera, non l'ordine carica->scarica: lo stato parte da zero e il ciclo
  dev'essere chiuso. E soprattutto il piano dipende dall'**ordinamento** delle ore, non dal
  livello dei prezzi: un modello che sbagliasse tutti i prezzi di venti euro ma ne
  indovinasse l'ordine produrrebbe il piano ottimo.

Le due previsioni sono **ipotesi da verificare, non da confermare**. Il disegno le mette
entrambe in condizione di essere smentite: se la contrazione dominasse, l'efficienza dovrebbe
crollare proprio nelle giornate a spread ampio; se proteggesse l'ordinamento, l'efficienza
dovrebbe dipendere dalla correlazione di rango e non dall'errore in livello.

Esempio
-------
    .\\.venv\\Scripts\\python.exe scripts\\16_propagazione.py --processi 8
    .\\.venv\\Scripts\\python.exe scripts\\16_propagazione.py --riusa
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ast  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from mgp import config, parallelo  # noqa: E402

#: Griglia ridotta: qui interessa la propagazione, non la risoluzione fine di K*. Copre
#: comunque dal pavimento di discretezza (1 MW) alla saturazione (6 GW).
GRIGLIA = [1.0, 25.0, 50.0, 100.0, 150.0, 200.0, 300.0, 400.0, 600.0, 800.0,
           1500.0, 3000.0, 6000.0]

#: Capacita' a cui si legge la perdita informativa "pura": abbastanza piccola da restare in
#: regime price taker, cosi' che la differenza fra i due piani non sia confusa con l'effetto
#: sul prezzo.
CAPACITA_PRICE_TAKER = 25.0


def _sezione(out, titolo: str) -> None:
    out("\n" + "=" * 88)
    out(titolo)
    out("=" * 88)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--previsioni", default="previsioni_NORD_2024.csv")
    ap.add_argument("--processi", type=int, default=8)
    ap.add_argument("--riusa", action="store_true",
                    help="rilegge la tabella gia' calcolata invece di rifarla")
    ap.add_argument("--completa", action="store_true",
                    help="usa la griglia definitiva a 132 punti invece di quella ridotta")
    args = ap.parse_args()

    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    from mgp import batteria as bt
    griglia = bt.GRIGLIA_CAPACITA_MW if args.completa else GRIGLIA
    destinazione_tabella = config.PROCESSED_DIR / (
        "propagazione_NORD_2024_completa.csv" if args.completa
        else "propagazione_NORD_2024.csv")
    if args.riusa and destinazione_tabella.exists():
        t = pd.read_csv(destinazione_tabella, dtype={"data": str, "mese": str})
        out(f"Tabella riletta da {destinazione_tabella.name}: {len(t):,} righe.")
    else:
        previsioni = pd.read_csv(config.PROCESSED_DIR / args.previsioni, dtype={"data": str})
        t = parallelo.propagazione_campione(previsioni, griglia, processi=args.processi,
                                            avanzamento=out, ogni=25)
        t.to_csv(destinazione_tabella, index=False)

    pd.set_option("display.width", 175)
    perfetta = t[t["origine"] == "perfetta"].set_index(["data", "potenza_mw"])
    previsione = t[t["origine"] == "previsione"].set_index(["data", "potenza_mw"])
    confronto = perfetta.join(previsione, lsuffix="_perf", rsuffix="_prev").reset_index()

    out("=" * 88)
    out(f"PROPAGAZIONE DELL'ERRORE — {confronto['data'].nunique()} giorni, "
        f"{t['potenza_mw'].nunique()} capacita'")
    out("=" * 88)

    # ================================================================== A. i due piani
    _sezione(out, "A. QUANTO I DUE PIANI DIFFERISCONO")
    # La capacita' di lettura va CERCATA nella griglia, non data per presente: la griglia
    # ridotta contiene 25 MW, quella definitiva a 132 punti no (salta da 20 a 30). Un
    # confronto con una costante produrrebbe una tabella vuota e un errore molto piu' avanti,
    # dove la causa non si riconosce.
    disponibili = np.sort(confronto["potenza_mw"].unique())
    capacita = float(disponibili[np.argmin(np.abs(disponibili - CAPACITA_PRICE_TAKER))])
    if capacita != CAPACITA_PRICE_TAKER:
        out(f"  nota: {CAPACITA_PRICE_TAKER:.0f} MW non e' nella griglia, si legge a "
            f"{capacita:.0f} MW (la piu' vicina disponibile).")
    pt = confronto[confronto["potenza_mw"] == capacita].copy()

    def ore(colonna):
        return pt[colonna].apply(
            lambda v: set(ast.literal_eval(v)) if isinstance(v, str) else set(v))

    car_p, car_v = ore("ore_carica_perf"), ore("ore_carica_prev")
    sca_p, sca_v = ore("ore_scarica_perf"), ore("ore_scarica_prev")
    pt["comuni_carica"] = [len(a & b) for a, b in zip(car_p, car_v)]
    pt["comuni_scarica"] = [len(a & b) for a, b in zip(sca_p, sca_v)]
    pt["ore_carica_perf_n"] = [len(a) for a in car_p]
    pt["ore_scarica_perf_n"] = [len(a) for a in sca_p]

    attivi = pt[~pt["piano_vuoto_perf"]]
    out(f"  giornate con piano non vuoto (previsione perfetta): {len(attivi)} su {len(pt)}")
    out(f"  giornate con piano non vuoto (da previsione)      : "
        f"{int((~pt['piano_vuoto_prev']).sum())} su {len(pt)}")
    out(f"  giornate in cui la previsione fa RINUNCIARE a operare: "
        f"{int((~pt['piano_vuoto_perf'] & pt['piano_vuoto_prev']).sum())}")
    out(f"  giornate in cui la previsione fa operare quando non conveniva: "
        f"{int((pt['piano_vuoto_perf'] & ~pt['piano_vuoto_prev']).sum())}")
    if len(attivi):
        q_car = float((attivi["comuni_carica"] / attivi["ore_carica_perf_n"]).mean())
        q_sca = float((attivi["comuni_scarica"] / attivi["ore_scarica_perf_n"]).mean())
        out(f"\n  quota media di ore di CARICA azzeccate  : {100*q_car:5.1f}%")
        out(f"  quota media di ore di SCARICA azzeccate : {100*q_sca:5.1f}%")
    out(f"\n  ora del minimo indovinata esattamente: "
        f"{100*float((pt['ora_min_reale_perf'] == pt['ora_min_prevista_perf']).mean()):5.1f}% "
        f"delle giornate")
    out(f"  ora del massimo indovinata esattamente: "
        f"{100*float((pt['ora_max_reale_perf'] == pt['ora_max_prevista_perf']).mean()):5.1f}%")

    # ============================================== B. le tre grandezze, regime price taker
    _sezione(out, f"B. LE TRE GRANDEZZE A {capacita:.0f} MW (regime price taker)")
    out("A questa capacita' l'effetto sul prezzo e' trascurabile, quindi la differenza fra")
    out("i due piani e' PURA perdita informativa, non cannibalizzazione.")
    out("")
    atteso = pt["profitto_atteso_prev"].sum()
    realizzato = pt["profitto_price_taker_prev"].sum()
    perfetto = pt["profitto_price_taker_perf"].sum()
    out(f"  profitto che la batteria SI ASPETTAVA (piano previsto, prezzi previsti): "
        f"{atteso:12,.0f} EUR")
    out(f"  profitto REALIZZATO           (piano previsto, prezzi veri)           : "
        f"{realizzato:12,.0f} EUR")
    out(f"  profitto con PREVISIONE PERFETTA (limite superiore)                   : "
        f"{perfetto:12,.0f} EUR")
    out(f"\n  perdita da incertezza informativa: {perfetto - realizzato:12,.0f} EUR "
        f"({100*(perfetto - realizzato)/perfetto:.1f}% del limite superiore)")
    out(f"  efficienza informativa           : {100*realizzato/perfetto:12.1f}%")
    out(f"  illusione (atteso meno realizzato): {atteso - realizzato:12,.0f} EUR "
        f"({100*(atteso - realizzato)/perfetto:+.1f}% del limite superiore)")

    # =================================================== C. ipotesi 1: contrazione spread
    _sezione(out, "C. IPOTESI 1 — LA CONTRAZIONE DELLO SPREAD PEGGIORA LE COSE?")
    out("Se vera, l'efficienza deve CROLLARE nelle giornate a spread ampio, che sono quelle")
    out("in cui il modello sottostima di piu'. Se invece l'efficienza vi resta alta o")
    out("addirittura sale, l'ipotesi e' smentita.")
    out("")
    validi = pt[pt["profitto_price_taker_perf"] > 1.0].copy()
    validi["efficienza"] = (validi["profitto_price_taker_prev"]
                            / validi["profitto_price_taker_perf"])
    validi["perdita"] = (validi["profitto_price_taker_perf"]
                         - validi["profitto_price_taker_prev"])
    validi["quintile_spread"] = pd.qcut(validi["spread_reale_perf"], 5, labels=False)
    tab = validi.groupby("quintile_spread").agg(
        spread_min=("spread_reale_perf", "min"), spread_max=("spread_reale_perf", "max"),
        efficienza_media=("efficienza", "mean"),
        perdita_media=("perdita", "mean"),
        profitto_perfetto=("profitto_price_taker_perf", "mean"),
        n=("efficienza", "size"))
    out(tab.round(3).to_string())
    r = stats.pearsonr(validi["spread_reale_perf"], validi["efficienza"])
    out(f"\n  correlazione spread ~ efficienza: {r.statistic:+.3f} (p = {r.pvalue:.2e})")
    r2 = stats.pearsonr(validi["spread_reale_perf"], validi["perdita"])
    out(f"  correlazione spread ~ perdita in EURO: {r2.statistic:+.3f} (p = {r2.pvalue:.2e})")
    out("  NOTA: perdita assoluta ed efficienza possono muoversi in verso opposto. Una")
    out("  perdita in euro crescente con lo spread e' quasi meccanica, perche' cresce anche")
    out("  il profitto potenziale; e' l'EFFICIENZA a dire se il danno e' proporzionalmente")
    out("  peggiore, ed e' quella che decide l'ipotesi.")

    # ================================================ D. ipotesi 2: l'ordinamento protegge
    _sezione(out, "D. IPOTESI 2 — E' L'ORDINAMENTO CHE PROTEGGE?")
    out("Il piano dipende dall'ORDINE delle ore, non dal livello dei prezzi. Se e' cosi',")
    out("l'efficienza deve dipendere dalla correlazione di RANGO fra previsione e realta',")
    out("piu' che dall'errore in livello.")
    out("")
    validi["errore_livello"] = (validi["spread_reale_perf"]
                                - validi["spread_previsto_perf"]).abs()
    for nome, colonna in (("correlazione di rango", "correlazione_rango_perf"),
                          ("correlazione lineare", "correlazione_lineare_perf"),
                          ("|errore sullo spread|", "errore_livello")):
        rr = stats.pearsonr(validi[colonna], validi["efficienza"])
        out(f"  efficienza ~ {nome:24s}: {rr.statistic:+.3f} (p = {rr.pvalue:.2e})")
    out("")
    validi["quintile_rango"] = pd.qcut(validi["correlazione_rango_perf"], 5, labels=False)
    tabr = validi.groupby("quintile_rango").agg(
        rango_min=("correlazione_rango_perf", "min"),
        rango_max=("correlazione_rango_perf", "max"),
        efficienza_media=("efficienza", "mean"),
        spread_medio=("spread_reale_perf", "mean"), n=("efficienza", "size"))
    out(tabr.round(3).to_string())
    out(f"\n  correlazione di rango mediana sull'anno: "
        f"{validi['correlazione_rango_perf'].median():.3f}")
    out(f"  giornate con rango sopra 0,9: "
        f"{100*float((validi['correlazione_rango_perf'] > 0.9).mean()):.1f}%")

    # =============================================================== E. erosione e soglia
    _sezione(out, "E. L'EROSIONE CAMBIA, SE IL PIANO NASCE DA UNA PREVISIONE?")
    out("L'erosione misura la cannibalizzazione a parita' di piano. Con un piano diverso il")
    out("confronto non e' piu' a parita': va letto come 'quanta della propria fonte di")
    out("reddito distrugge una flotta che pianifica come pianifica davvero'.")
    out("")
    curva = t.groupby(["origine", "potenza_mw"]).agg(
        erosione_mediana=("erosione_relativa", "median"),
        erosione_q90=("erosione_relativa", lambda s: float(s.quantile(0.9))),
        profitto_pt=("profitto_price_taker", "sum"),
        profitto_pm=("profitto_price_maker", "sum"),
        piani_vuoti=("piano_vuoto", "sum"))
    out(curva.round(4).to_string())

    suffisso = "_completa" if args.completa else ""
    destinazione = config.TABLE_DIR / f"16_propagazione{suffisso}.txt"
    destinazione.write_text(buffer.getvalue(), encoding="utf-8")
    validi.to_csv(config.TABLE_DIR / f"16_efficienza_per_giorno{suffisso}.csv", index=False)
    curva.to_csv(config.TABLE_DIR / f"16_curva_erosione_due_origini{suffisso}.csv")
    print(f"\nReport salvato in {destinazione}")


if __name__ == "__main__":
    main()
