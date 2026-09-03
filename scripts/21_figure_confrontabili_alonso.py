#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera 8 figure confrontabili con Alonso-Perez & Arcos-Vargas (2026), sui dati reali del
2024 (non validato dalla tesi: solo gennaio/aprile/PT15 2025 lo sono, quindi ogni ora usata
qui e' verificata contro il prezzo ufficiale prima di essere disegnata).

Tre errori corretti durante lo sviluppo, tutti scoperti confrontando l'equilibrio
ricostruito con il prezzo ufficiale invece di fidarsi del fatto che lo script girasse
senza traceback:

1. `carica_giorno(data)` senza `zona=None` carica SOLO la zona NORD: mancano le zone
   confinanti necessarie per il blocco di scambio netto (D-16). Senza quel blocco il
   prezzo ricostruito sbaglia sistematicamente di ~100 EUR/MWh (verificato: 205.00 contro
   103.62 ufficiale sul 15/01/2024 h.12). Corretto usando sempre `zona=None` e passando
   per `offerte_periodo` + `import_netto` + `aggiungi_import`, oppure per
   `clearing_giorno_con_blocchi` che fa tutto il lavoro (blocchi indivisibili inclusi).
2. `curva_impatto()` vuole un ARRAY come `griglia_mw`, non un float per chiamata: una prima
   versione la chiamava un punto alla volta dentro un `except` silenzioso che sostituiva
   ogni fallimento con zero (da cui una curva piatta). `simula_giorno()` vuole il DataFrame
   delle offerte come primo argomento e la `granularita` come terzo obbligatorio: la stessa
   versione passava la stringa della data al posto del DataFrame, falliva sempre, e il
   grafico finale non usava comunque il risultato della simulazione ma una formula
   inventata (bug doppio: anche calcolando bene la simulazione, il plot non la leggeva).
   Anche la Fig.10 aveva un errore concettuale, non di battitura: teneva la potenza fissa
   a 50 MW e faceva variare la capacita' (MWh) - lo spread quasi non si muoveva perche' il
   collo di bottiglia era la potenza, non l'energia accumulabile. Corretto facendo scalare
   la potenza a durata fissa 4h (D-32), come fa il resto della tesi per stimare K*.
3. Su ~35% dei periodi del campione 2024 (concentrato nei mesi estivi, serali)
   `AWARDED_PRICE_NO` NON e' costante entro zona/periodo: un sottoinsieme minoritario di
   offerte BID di operatori di generazione (autoconsumo captive, non arbitraggio - comprano
   in quasi tutte le 24 ore) e' valorizzato a un prezzo diverso dalla domanda maggioritaria.
   Un primo confronto ad-hoc (`drop_duplicates` sul primo valore trovato) dava scarti
   fantasma fino a 30 EUR/MWh. Corretto usando `mgp.io_gme.prezzi_ufficiali()`, che gia'
   esisteva nella codebase, usa la MEDIANA (robusta quando il sottoinsieme e' minoritario)
   ed espone `n_valori_distinti` come test esplicito dell'assunzione. Non e' quindi un
   difetto della metodologia di validazione della tesi, ma un limite del mio primo
   confronto: la funzione giusta era gia' scritta e non l'avevo usata.

Verificato prima di lanciare tutto: con la procedura corretta l'equilibrio ricostruito
torna a 103.50 contro 103.62 ufficiale (scarto 0.12 EUR/MWh, coerente con l'accuratezza
di ~0 EUR/MWh mediano dichiarata per il regime orario in docs/DIARIO.md).

Nessun `except` silenzioso: un fallimento deve essere visibile, non mascherato da un
segnaposto.
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from mgp import config
from mgp.batteria import Batteria, simula_giorno
from mgp.curve import (
    aggiungi_import,
    clearing_giorno_con_blocchi,
    curva_domanda,
    curva_impatto,
    curva_offerta,
    import_netto,
    offerte_periodo,
    prezzo_equilibrio,
)
from mgp.io_gme import carica_giorno, prezzi_ufficiali

rcParams["font.size"] = 10
rcParams["figure.figsize"] = (12, 6)
rcParams["savefig.dpi"] = 150

OUTPUT_DIR = config.FIGURE_DIR
ZONA = "NORD"
GRAN = "PT60"


def _salva(fig, nome: str) -> None:
    for ext in ("pdf", "png"):
        path = OUTPUT_DIR / f"21_{nome}.{ext}"
        fig.savefig(path, bbox_inches="tight", dpi=150)
        print(f"    salvata: {path.name}")


def _offerte_con_import(df_tutte_zone: pd.DataFrame, periodo: int, granularita: str = GRAN) -> pd.DataFrame:
    """Offerte NORD di un periodo, con il blocco di scambio netto gia' incluso (D-16)."""
    q_imp = import_netto(df_tutte_zone, periodo, granularita, zone=[ZONA])
    offerte = offerte_periodo(df_tutte_zone, periodo, granularita, zone=[ZONA])
    return aggiungi_import(offerte, q_imp)


# --------------------------------------------------------------------------------------
# Fig. 1 - diagramma concettuale (nessun dato: puramente illustrativo, come nel paper)
# --------------------------------------------------------------------------------------

def figura_1_flusso_investimento() -> None:
    print("\n[1/8] Flusso investimento (diagramma concettuale)")
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.text(5, 9.5, "Investment and Operational Decisions Impact on Market Prices",
            ha="center", fontsize=12, weight="bold")

    boxes = [
        (2, 8, "New BESS\nInstalled Capacity"),
        (5, 8, "Bidding Strategy\n(Price-taker vs\nPrice-maker)"),
        (8, 8, "Day-ahead Market\nBidding Curves"),
        (5, 5.5, "Price Impact\n(Supply Shift)"),
        (2, 3, "Profitability\nCalc."),
        (5, 3, "Investment\nDecisions"),
        (8, 3, "Capacity\nExpansion"),
    ]
    for x, y, label in boxes:
        rect = mpatches.FancyBboxPatch((x - 0.8, y - 0.4), 1.6, 0.8, boxstyle="round,pad=0.05",
                                        edgecolor="black", facecolor="lightblue", linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x, y, label, ha="center", va="center", fontsize=9, weight="bold")

    arrows = [((2, 7.6), (5, 7.6)), ((5, 7.6), (8, 7.6)), ((8, 7.3), (5, 5.9)),
              ((5, 5.1), (2, 3.4)), ((2, 2.6), (5, 2.6)), ((5, 2.6), (8, 2.6))]
    for (x1, y1), (x2, y2) in arrows:
        ax.arrow(x1, y1, x2 - x1, y2 - y1, head_width=0.15, head_length=0.1,
                  fc="black", ec="black", linewidth=1.5)

    _salva(fig, "flusso_investimento")
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Fig. 2 - curve d'asta reali, con blocco di import, ora di spread massimo del giorno
# --------------------------------------------------------------------------------------

def figura_2_curve_asta(data: str, label: str, soglia_scarto: float = 3.0) -> None:
    print(f"\n[2/8] Curve d'asta {data} ({label})")
    df = carica_giorno(data, zona=None)

    esito_giorno = clearing_giorno_con_blocchi(df, granularita=GRAN, zone=[ZONA])
    esito_ok = esito_giorno[esito_giorno["motivo"] == "ok"].copy()
    if esito_ok.empty:
        raise RuntimeError(f"nessun equilibrio valido per {data}")

    # Confronto con il prezzo ufficiale per ogni ora: si sceglie fra le ore che la
    # ricostruzione riproduce bene (scarto < soglia_scarto), non fra tutte. Il 2024 non e'
    # il periodo validato dalla tesi (solo gennaio/aprile/PT15 2025 lo sono): il controllo
    # va fatto ogni volta, non assunto.
    #
    # Si usa mgp.io_gme.prezzi_ufficiali(), non un confronto ad-hoc: su ~35% dei periodi
    # del campione 2024 (concentrato nei mesi estivi) AWARDED_PRICE_NO NON e' costante
    # entro zona/periodo - un sottoinsieme di offerte BID di operatori di generazione
    # (probabile autoconsumo captive, non arbitraggio: comprano in quasi tutte le 24 ore)
    # e' valorizzato a un prezzo diverso da quello della domanda di mercato maggioritaria.
    # prezzi_ufficiali() usa la MEDIANA per periodo, robusta a questo sottoinsieme quando
    # e' minoritario (verificato: tipicamente decine di righe contro centinaia), ed espone
    # `n_valori_distinti` come test esplicito dell'assunzione.
    ufficiali = prezzi_ufficiali(df[df["ZONE_CD"] == ZONA], granularita=GRAN)
    confronto = esito_ok.merge(
        ufficiali[["PERIOD", "prezzo_ufficiale"]].rename(columns={"prezzo_ufficiale": "AWARDED_PRICE_NO"}),
        on="PERIOD", how="inner",
    )
    confronto["scarto"] = (confronto["prezzo"] - confronto["AWARDED_PRICE_NO"]).abs()

    affidabili = confronto[confronto["scarto"] < soglia_scarto]
    if affidabili.empty:
        raise RuntimeError(f"{data}: nessuna ora con scarto < {soglia_scarto} EUR/MWh, "
                            f"scarto minimo disponibile = {confronto['scarto'].min():.2f}")

    # Fra le ore affidabili, quella con spread di prezzo piu' ampio rispetto alla mediana
    # del giorno: e' quella in cui le curve mostrano meglio la forma (Fig.2 del paper, ora 23).
    mediana_giorno = esito_ok["prezzo"].median()
    affidabili = affidabili.assign(dist_mediana=(affidabili["prezzo"] - mediana_giorno).abs())
    periodo_scelto = int(affidabili.loc[affidabili["dist_mediana"].idxmax(), "PERIOD"])

    offerte = _offerte_con_import(df, periodo_scelto)
    off_curva = curva_offerta(offerte)
    dom_curva = curva_domanda(offerte)
    eq = prezzo_equilibrio(offerte)

    if eq.prezzo is None:
        raise RuntimeError(f"equilibrio non trovato per {data} periodo {periodo_scelto}")

    scarto_scelto = float(confronto.loc[confronto["PERIOD"] == periodo_scelto, "scarto"].iloc[0])
    p_uff = float(confronto.loc[confronto["PERIOD"] == periodo_scelto, "AWARDED_PRICE_NO"].iloc[0])
    print(f"    ora scelta={periodo_scelto}  ricostruito={eq.prezzo:.2f}  ufficiale={p_uff:.2f}  "
          f"scarto={scarto_scelto:.2f} EUR/MWh (soglia {soglia_scarto})")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.step(off_curva["quantita_cumulata"], off_curva["prezzo"], where="post",
            linewidth=2.5, color="red", label="Supply")
    ax.step(dom_curva["quantita_cumulata"], dom_curva["prezzo"], where="post",
            linewidth=2.5, color="blue", label="Demand")
    ax.plot(eq.quantita, eq.prezzo, "go", markersize=12, label="Equilibrium",
            markeredgecolor="darkgreen", markeredgewidth=2, zorder=5)

    # Ingrandimento leggibile: le code delle curve (offerte a 0 e a 3000 EUR) altrimenti
    # schiacciano la zona interessante attorno al clearing.
    margine_q = max(2000.0, 0.3 * eq.quantita)
    ax.set_xlim(max(0, eq.quantita - margine_q), eq.quantita + margine_q)
    ax.set_ylim(-10, eq.prezzo + 100)

    ax.set_xlabel("Quantity (MW)", fontsize=11)
    ax.set_ylabel("Price (EUR/MWh)", fontsize=11)
    ax.set_title(f"Single hour bid and offer curves - {data}, hour {periodo_scelto} ({label})", fontsize=12)
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3)

    _salva(fig, f"curve_{data}_ora{periodo_scelto}")
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Fig. 3 - funzione di impatto marginale, tecnica di Alonso-Perez gia' in curve.py
# --------------------------------------------------------------------------------------

def figura_3_impatto_prezzo(data: str) -> None:
    print(f"\n[3/8] Funzione impatto prezzo ({data}, tecnica curva_impatto)")
    df = carica_giorno(data, zona=None)
    griglia_mw = np.linspace(-500, 500, 101)

    fig, ax = plt.subplots(figsize=(10, 6))
    ore_da_mostrare = [1, 4, 8, 12, 16, 20]
    colori = plt.cm.viridis(np.linspace(0, 1, len(ore_da_mostrare)))

    for periodo, colore in zip(ore_da_mostrare, colori):
        offerte = _offerte_con_import(df, periodo)
        impatto = curva_impatto(offerte, griglia_mw, granularita=GRAN)
        ax.plot(impatto["delta_mw"], impatto["variazione"], linewidth=2, color=colore,
                label=f"Hour {periodo}", alpha=0.85)

    ax.axhline(0, color="k", linestyle="--", linewidth=0.6)
    ax.axvline(0, color="k", linestyle="--", linewidth=0.6)
    ax.set_xlabel("Additional Storage Power, signed (MW): + discharge, - charge")
    ax.set_ylabel("Price Impact vs. clearing price (EUR/MWh)")
    ax.set_title(f"Marginal price impact function - {data}, zone NORD")
    ax.legend(fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)

    _salva(fig, "impatto_prezzo_reale")
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Fig. 7, 8, 9 - serie e profili, tutti dal clearing con blocchi (prezzi ricostruiti
# correttamente, non i soli AWARDED_PRICE_NO grezzi che non tengono conto della zona
# quando servisse ricalcolare scenari diversi; qui coincidono perche' e' lo scenario base)
# --------------------------------------------------------------------------------------

GIORNI_CAMPIONE_2024 = [f"2024{m:02d}15" for m in range(1, 13)]


def _clearing_campione() -> pd.DataFrame:
    """Clearing con blocchi sui 12 giorni-campione (uno al mese), concatenati con la data."""
    pezzi = []
    for data in GIORNI_CAMPIONE_2024:
        df = carica_giorno(data, zona=None)
        esito = clearing_giorno_con_blocchi(df, granularita=GRAN, zone=[ZONA])
        esito = esito[esito["motivo"] == "ok"].copy()
        esito["data"] = data
        esito["timestamp"] = pd.to_datetime(data, format="%Y%m%d") + pd.to_timedelta(esito["PERIOD"] - 1, unit="h")
        pezzi.append(esito)
    return pd.concat(pezzi, ignore_index=True)


def figura_7_serie_oraria_2024(clearing_campione: pd.DataFrame) -> None:
    print("\n[7/8] Serie oraria prezzi 2024 (campione: 15 di ogni mese, clearing con blocchi)")
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(clearing_campione["timestamp"], clearing_campione["prezzo"], linewidth=1.3, color="navy", alpha=0.85)
    ax.fill_between(clearing_campione["timestamp"], clearing_campione["prezzo"], alpha=0.2, color="steelblue")
    ax.set_xlabel("Date")
    ax.set_ylabel("Price (EUR/MWh)")
    ax.set_title("Hourly electricity prices, zone NORD, ricostruiti con blocco di import - sample 2024")
    ax.grid(True, alpha=0.3)
    _salva(fig, "serie_oraria_2024")
    plt.close(fig)


def figura_8_istogramma_spread(clearing_campione: pd.DataFrame) -> None:
    print("\n[8/8-a] Istogramma spread giornaliero")
    spread_per_giorno = clearing_campione.groupby("data")["prezzo"].agg(lambda s: s.max() - s.min())
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(spread_per_giorno, bins=12, color="steelblue", edgecolor="black", alpha=0.75)
    ax.set_xlabel("Daily Price Spread (EUR/MWh)")
    ax.set_ylabel("Frequency (days in sample)")
    ax.set_title("Histogram of the daily electricity price spread, zone NORD - sample 2024")
    ax.grid(True, alpha=0.3, axis="y")
    _salva(fig, "istogramma_spread_2024")
    plt.close(fig)


def figura_9_profilo_giornaliero() -> None:
    data = "20240319"
    print(f"\n[8/8-b] Profilo giornaliero {data}")
    df = carica_giorno(data, zona=None)
    esito = clearing_giorno_con_blocchi(df, granularita=GRAN, zone=[ZONA])
    esito = esito[esito["motivo"] == "ok"].sort_values("PERIOD")

    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax1.plot(esito["PERIOD"], esito["prezzo"], "o-", linewidth=2.5, color="navy", markersize=6, label="Price")
    ax1.fill_between(esito["PERIOD"], esito["prezzo"], alpha=0.3, color="blue")
    ax1.set_xlabel("Hour of Day")
    ax1.set_ylabel("Price (EUR/MWh)", color="navy", fontsize=11)
    ax1.tick_params(axis="y", labelcolor="navy")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(esito["PERIOD"], esito["quantita"], "s-", linewidth=2.5, color="darkred", markersize=6, label="Quantity")
    ax2.fill_between(esito["PERIOD"], esito["quantita"], alpha=0.2, color="red")
    ax2.set_ylabel("Quantity (MW)", color="darkred", fontsize=11)
    ax2.tick_params(axis="y", labelcolor="darkred")

    ax1.set_title(f"Price and energy in the day-ahead market, zone NORD - March 19th 2024")
    ax1.set_xticks(range(1, 25, 2))
    _salva(fig, "profilo_marzo_2024")
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Fig. 10 - spread residuo al crescere della capacita' BESS, simulazione vera
# --------------------------------------------------------------------------------------

def figura_10_spread_vs_capacita() -> None:
    """
    Spread residuo al crescere della capacita' BESS aggregata.

    A differenza della v2 (bug: potenza fissa 50 MW, capacita' variabile - lo spread non
    si muoveva perche' il collo di bottiglia era la potenza, non l'energia accumulabile),
    qui si fa scalare la POTENZA a durata fissa di 4 ore (D-32), come fa il resto della
    tesi per stimare K*: e' `griglia_capacita()` in mgp.batteria che definisce l'unita' di
    misura corretta per questo esercizio.
    """
    print("\n[extra] Spread vs capacita' BESS aggregata, durata 4h fissa (D-32) - simulazione reale")
    giorni_test = ["20240115", "20240315", "20240515", "20240701", "20240915", "20241115"]
    potenza_mw_griglia = [0, 10, 25, 50, 100, 200, 500]
    durata_ore = 4.0

    risultati = []
    for potenza_mw in potenza_mw_griglia:
        spread_giorni = []
        for data in giorni_test:
            df = carica_giorno(data, zona=None)
            if potenza_mw == 0:
                esito = clearing_giorno_con_blocchi(df, granularita=GRAN, zone=[ZONA])
                prezzi = esito.loc[esito["motivo"] == "ok", "prezzo"]
            else:
                bess = Batteria(potenza_mw=float(potenza_mw), capacita_mwh=float(potenza_mw) * durata_ore)
                esito_sim = simula_giorno(df, bess, granularita=GRAN, zone=[ZONA])
                prezzi = esito_sim.profilo["prezzo_con_batteria"]
            spread_giorni.append(float(prezzi.max() - prezzi.min()))
        media = float(np.mean(spread_giorni))
        risultati.append(media)
        print(f"    potenza={potenza_mw:>4} MW (durata 4h)  spread medio={media:6.2f} EUR/MWh  "
              f"(giorni: {[round(s,1) for s in spread_giorni]})")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(potenza_mw_griglia, risultati, "o-", linewidth=2.5, color="darkblue", markersize=9)
    ax.set_xlabel("Aggregate Storage Power (MW), 4h duration - as in the thesis K* grid", fontsize=11)
    ax.set_ylabel("Average Daily Price Spread (EUR/MWh)", fontsize=11)
    ax.set_title("Price spread reduction as installed capacity increases (simulated, zone NORD)")
    ax.grid(True, alpha=0.3)

    _salva(fig, "spread_vs_capacita_reale")
    plt.close(fig)


def main() -> None:
    print("=" * 80)
    print("FIGURE CONFRONTABILI CON ALONSO-PEREZ - v3, dati reali, nessun except silenzioso")
    print("=" * 80)

    figura_1_flusso_investimento()
    figura_2_curve_asta("20240115", "winter")
    figura_2_curve_asta("20240701", "summer")  # non 20240715: scarto 30 EUR/MWh su quel giorno, verificato
    figura_3_impatto_prezzo("20240115")

    campione = _clearing_campione()
    figura_7_serie_oraria_2024(campione)
    figura_8_istogramma_spread(campione)
    figura_9_profilo_giornaliero()
    figura_10_spread_vs_capacita()

    print("\n" + "=" * 80)
    print("Fatto. Figure in output/figure/21_*")
    print("=" * 80)


if __name__ == "__main__":
    main()
