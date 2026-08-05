"""
Passo 6: la soglia di capacita' oltre la quale l'accumulo diventa price maker.

Che cosa calcola
----------------
Per ogni giorno del campione e per ogni capacita' aggregata della griglia:

1. si ricostruiscono le curve d'asta reali di tutti i periodi della giornata e se ne ricava
   il prezzo di riferimento, cioe' quello **senza** accumulo;
2. si ottimizza una volta sola il piano di carica e scarica su quei prezzi (D-25: le batterie
   sono molte e piccole, nessuna anticipa il proprio effetto);
3. si valorizza il piano ai prezzi di riferimento, ottenendo il profitto **price taker**;
4. si inserisce lo stesso piano nelle curve, si ricalcola l'equilibrio di ogni periodo e lo si
   valorizza ai prezzi nuovi, ottenendo il profitto **price maker**;
5. la differenza fra i due, in valore assoluto e in quota, e' l'**erosione** E(d, K).

Dalla tabella delle erosioni si stima poi la soglia K*, cioe' la capacita' alla quale il
quantile prudenziale dell'erosione attraversa il livello dichiarato, con l'intervallo di
confidenza ottenuto ricampionando i giorni (D-26, D-27) ed eventualmente stratificando per
stagione o per anno (D-28).

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\06_soglia_price_maker.py --mese 202501
    .\\.venv\\Scripts\\python.exe scripts\\06_soglia_price_maker.py --mese 202501 \\
        --griglia 0,250,500,1000,2000,4000 --durata 4 --quantile 0.9 --soglia 0.10

Il calcolo e' pesante: ogni coppia (giorno, capacita') richiede il clearing di tutti i periodi
della giornata. La tabella delle erosioni viene salvata, cosi' il bootstrap e le sue varianti
si possono rifare senza ricalcolarla.
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
from mgp import config, curve, io_gme  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

giorni_del_mese = import_module("03_valida_mese").giorni_del_mese

#: Griglia di capacita' aggregata predefinita, in MW.
#:
#: La prima versione partiva da 250 MW, ragionando sulla dimensione del mercato: in zona NORD
#: si scambiano 15-25 GW per asta, quindi poche centinaia di MW sembravano marginali. La
#: prima prova ha smentito il ragionamento — a 250 MW l'erosione era gia' del 12% e la soglia
#: cadeva fuori griglia — perche' cio' che conta non e' il volume complessivo ma la pendenza
#: della curva **attorno all'equilibrio**, dove i gradini sono pochi e larghi. La griglia
#: parte quindi da poche decine di MW.
GRIGLIA_PREDEFINITA = [25.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1500.0, 3000.0, 6000.0]

STAGIONI = {12: "inverno", 1: "inverno", 2: "inverno", 3: "primavera", 4: "primavera",
            5: "primavera", 6: "estate", 7: "estate", 8: "estate", 9: "autunno",
            10: "autunno", 11: "autunno"}


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def erosioni_giorno(data: str, griglia: list[float], durata_ore: float) -> pd.DataFrame:
    """
    Calcola l'erosione di una giornata su tutta la griglia di capacita'.

    Le curve d'asta e i prezzi di riferimento si calcolano **una volta sola** e si riusano
    per ogni capacita': cambia solo il profilo che vi si inserisce.
    """
    granularita = config.granularita_prevalente(data)
    df = io_gme.carica_giorno(data=data, zona=None)
    zone_presenti = set(df["ZONE_CD"].dropna().unique())
    perimetro = ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti]

    offerte_giorno = curve.offerte_giornata(df, granularita, zone=perimetro, con_import=True)
    periodi = sorted(offerte_giorno)
    riferimento = np.array(
        [curve.prezzo_equilibrio(offerte_giorno[p]).prezzo for p in periodi], dtype=float
    )

    mese = int(data[4:6])
    righe = []
    for potenza in griglia:
        e = bt.erosione(df, potenza_aggregata_mw=potenza, granularita=granularita, data=data,
                        durata_ore=durata_ore, zone=perimetro,
                        prezzi_riferimento=riferimento, offerte_giorno=offerte_giorno)
        righe.append({
            "data": data,
            "granularita": granularita,
            "anno": data[:4],
            "mese": data[4:6],
            "stagione": STAGIONI[mese],
            "potenza_mw": potenza,
            "durata_ore": durata_ore,
            "profitto_price_taker": e.profitto_price_taker,
            "profitto_price_maker": e.profitto_price_maker,
            "erosione_assoluta": e.erosione_assoluta,
            "erosione_relativa": e.erosione_relativa,
            "variazione_prezzo_media": e.variazione_prezzo_media,
            "cicli_equivalenti": e.cicli_equivalenti,
            "prezzo_medio_riferimento": float(np.nanmean(riferimento)),
            "spread_giornaliero": float(np.nanmax(riferimento) - np.nanmin(riferimento)),
        })
    return pd.DataFrame(righe)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mese", help="mese da elaborare, formato AAAAMM")
    parser.add_argument("--giorni", help="date AAAAMMGG separate da virgola")
    parser.add_argument("--etichetta", help="nome per i file prodotti")
    parser.add_argument("--griglia", help="capacita' in MW separate da virgola")
    parser.add_argument("--durata", type=float, default=4.0,
                        help="rapporto energia/potenza della flotta, in ore")
    parser.add_argument("--quantile", type=float, default=0.90,
                        help="quantile prudenziale (0,80 o 0,90; non usare code estreme)")
    parser.add_argument("--soglia", type=float, default=0.10,
                        help="quota di erosione che definisce il passaggio a price maker")
    parser.add_argument("--n-boot", type=int, default=1000)
    parser.add_argument("--riusa-tabella", action="store_true",
                        help="rilegge la tabella delle erosioni gia' calcolata")
    args = parser.parse_args()

    if args.giorni:
        giorni = args.giorni.split(",")
    elif args.mese:
        giorni = giorni_del_mese(args.mese)
    else:
        parser.error("indicare --mese oppure --giorni")
    etichetta = args.etichetta or (args.mese or giorni[0])
    griglia = ([float(x) for x in args.griglia.split(",")] if args.griglia
               else list(GRIGLIA_PREDEFINITA))

    config.assicura_cartelle()
    pd.set_option("display.width", 140)
    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo, flush=True)
        buffer.write(testo + "\n")

    f_erosioni = config.PROCESSED_DIR / f"erosioni_{etichetta}.csv"

    out(_sezione(f"SOGLIA PRICE MAKER — {etichetta}, {len(giorni)} giorni"))
    out(f"Griglia di capacita' aggregata (MW): {griglia}")
    out(f"Durata della flotta: {args.durata} ore  |  "
        f"quantile prudenziale: {args.quantile:.0%}  |  soglia di erosione: {args.soglia:.0%}")

    if args.riusa_tabella and f_erosioni.exists():
        erosioni = pd.read_csv(f_erosioni, dtype={"data": str, "anno": str, "mese": str})
        out(f"\nTabella delle erosioni riletta da {f_erosioni.name}: {len(erosioni)} righe.")
    else:
        inizio = time.time()
        pezzi = []
        for i, data in enumerate(giorni, start=1):
            pezzi.append(erosioni_giorno(data, griglia, args.durata))
            if i % 5 == 0 or i == len(giorni):
                out(f"  [{i:>3}/{len(giorni)}] {data}  "
                    f"({time.time() - inizio:.0f} s)")
        erosioni = pd.concat(pezzi, ignore_index=True)
        erosioni.to_csv(f_erosioni, index=False)
        out(f"\nCalcolo completato in {time.time() - inizio:.0f} secondi.")

    # ----------------------------------------------------------------------------------
    out(_sezione("A. COME CRESCE L'EROSIONE CON LA CAPACITA' INSTALLATA"))
    out("Quantili dell'erosione relativa fra i giorni del campione, per capacita'.")
    curva_rel = bt.curva_erosione(erosioni, quantili=(0.5, 0.8, 0.9))
    out("\n" + curva_rel.round(4).to_string(index=False))

    out("\nErosione in valore assoluto (euro al giorno), che resta interpretabile anche")
    out("nelle giornate a basso spread, dove il rapporto non lo e' (D-29):")
    curva_ass = bt.curva_erosione(erosioni, quantili=(0.5, 0.9),
                                  colonna_erosione="erosione_assoluta")
    out("\n" + curva_ass.round(1).to_string(index=False))

    senza_rapporto = int(erosioni["erosione_relativa"].isna().sum())
    out(f"\nCoppie (giorno, capacita') senza erosione relativa calcolabile: {senza_rapporto} "
        f"su {len(erosioni)} — sono le giornate a profitto atteso trascurabile, che restano "
        f"nel campione con la sola erosione assoluta.")

    # ----------------------------------------------------------------------------------
    out(_sezione("B. IL PAVIMENTO DI DISCRETEZZA"))
    out("A capacita' minuscole l'erosione misurata non e' un effetto di mercato ma della")
    out("discretezza delle curve: in qualche periodo l'equilibrio cade sul bordo di un")
    out("gradino e bastano pochi MW a farlo saltare. Si misura alla capacita' piu' piccola")
    out("della griglia e si sottrae giorno per giorno.")
    erosioni = bt.sottrai_pavimento(erosioni)
    capacita_minima = float(erosioni["potenza_mw"].min())
    pavimento = erosioni.loc[erosioni["potenza_mw"] == capacita_minima, "erosione_relativa"]
    out(f"\nPavimento misurato a {capacita_minima:.0f} MW: mediana {pavimento.median():.2%}, "
        f"80° percentile {pavimento.quantile(0.8):.2%}, "
        f"90° percentile {pavimento.quantile(0.9):.2%}, massimo {pavimento.max():.2%}")
    if pavimento.quantile(args.quantile) >= args.soglia / 2:
        out("ATTENZIONE: il pavimento e' almeno la meta' della soglia dichiarata. A questo")
        out("livello la soglia non e' interpretabile: alzare la soglia o migliorare la")
        out("risoluzione della ricostruzione.")

    # ----------------------------------------------------------------------------------
    out(_sezione("C. LA SOGLIA K*"))
    out("K* e' la capacita' alla quale il quantile prudenziale dell'erosione attraversa la")
    out("soglia dichiarata. L'intervallo di confidenza al 90% viene dal ricampionamento dei")
    out("giorni con reimmissione: un giorno entra o esce con tutta la sua curva.")
    complessiva = bt.bootstrap_soglia(erosioni, soglia=args.soglia, quantile=args.quantile,
                                      n_boot=args.n_boot, colonna_erosione="erosione_netta")
    lorda = bt.bootstrap_soglia(erosioni, soglia=args.soglia, quantile=args.quantile,
                                n_boot=args.n_boot)
    out("\nAl netto del pavimento (stima adottata):")
    out(complessiva.round(1).to_string(index=False))
    out("\nSull'erosione lorda, per confronto:")
    out(lorda.round(1).to_string(index=False))

    # ----------------------------------------------------------------------------------
    out(_sezione("D. STRATIFICAZIONE (D-28)"))
    out("La soglia non e' stazionaria: dipende dal mix produttivo e dal livello dei prezzi.")
    for colonna in ("stagione", "anno"):
        if erosioni[colonna].nunique() > 1:
            tabella = bt.bootstrap_soglia(erosioni, soglia=args.soglia,
                                          quantile=args.quantile, n_boot=args.n_boot,
                                          strato=colonna, colonna_erosione="erosione_netta")
            out(f"\nPer {colonna}:")
            out(tabella.round(1).to_string(index=False))
        else:
            out(f"\nPer {colonna}: un solo livello nel campione, stratificazione non "
                f"informativa.")

    # ----------------------------------------------------------------------------------
    out(_sezione("D. SENSIBILITA' DELLA SOGLIA ALLE SCELTE DICHIARATE"))
    out("Quantile e livello di erosione non sono stimati dai dati ma scelti: conviene")
    out("mostrare quanto la soglia dipende da quella scelta.")
    prove = []
    for quantile in (0.80, 0.90):
        for livello in (0.05, 0.10, 0.20):
            riga = bt.bootstrap_soglia(erosioni, soglia=livello, quantile=quantile,
                                       n_boot=max(200, args.n_boot // 5))
            if len(riga):
                voce = riga.iloc[0].to_dict()
                voce["quantile"] = quantile
                voce["soglia"] = livello
                prove.append(voce)
    if prove:
        tabella = pd.DataFrame(prove)[["quantile", "soglia", "K_stella", "K_inf", "K_sup",
                                       "quota_senza_attraversamento"]]
        out("\n" + tabella.round(2).to_string(index=False))

    # ----------------------------------------------------------------------------------
    f_curva = config.TABLE_DIR / f"06_curva_erosione_{etichetta}.csv"
    f_soglia = config.TABLE_DIR / f"06_soglia_{etichetta}.csv"
    f_report = config.TABLE_DIR / f"06_soglia_{etichetta}.txt"
    curva_rel.to_csv(f_curva, index=False)
    complessiva.to_csv(f_soglia, index=False)

    out(_sezione("FILE PRODOTTI"))
    for f in (f_erosioni, f_curva, f_soglia, f_report):
        out(f"  {f}")
    f_report.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
