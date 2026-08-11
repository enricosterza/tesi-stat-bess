"""
Test della simulazione dell'accumulo.

I casi sono costruiti perche' il risultato si calcoli a mano: due o tre periodi, prezzi
scelti a numeri tondi, rendimenti unitari dove servono a rendere trasparente il conto.

Esecuzione:
    .\\.venv\\Scripts\\python.exe -m pytest tests -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp import batteria as bt  # noqa: E402
from mgp import config, curve  # noqa: E402


def _batteria(**kwargs) -> bt.Batteria:
    """Batteria da 10 MW e 10 MWh senza perdite, salvo diversa indicazione."""
    parametri = dict(potenza_mw=10.0, capacita_mwh=10.0,
                     rendimento_carica=1.0, rendimento_scarica=1.0,
                     energia_iniziale_mwh=0.0, ciclo_chiuso=False)
    parametri.update(kwargs)
    return bt.Batteria(**parametri)


# --------------------------------------------------------------------------------------
# Caratteristiche della batteria
# --------------------------------------------------------------------------------------
def test_durata_e_rendimento_di_ciclo():
    """Una batteria da 100 MW e 400 MWh ha durata 4 ore; i rendimenti si compongono."""
    b = bt.Batteria(potenza_mw=100.0, capacita_mwh=400.0,
                    rendimento_carica=0.9, rendimento_scarica=0.9)
    assert b.durata_ore == 4.0
    assert b.rendimento_ciclo == pytest.approx(0.81)


# --------------------------------------------------------------------------------------
# Profilo ottimo a prezzi dati
# --------------------------------------------------------------------------------------
def test_compra_basso_e_vende_alto():
    """
    Con prezzi 10 e 100 e una batteria da 10 MW/10 MWh senza perdite, l'ottimo e' caricare
    a piena potenza nel primo periodo e scaricare nel secondo: il ricavo e'
    100 x 10 - 10 x 10 = 900 euro.
    """
    carica, scarica = bt.profilo_ottimo([10.0, 100.0], _batteria(), 1.0)
    assert carica == pytest.approx([10.0, 0.0])
    assert scarica == pytest.approx([0.0, 10.0])
    ricavo = float(np.sum(np.array([10.0, 100.0]) * (scarica - carica)))
    assert ricavo == pytest.approx(900.0)


def test_nessuna_operazione_se_il_prezzo_e_piatto():
    """Senza differenziale non c'e' arbitraggio: la batteria resta ferma."""
    carica, scarica = bt.profilo_ottimo([50.0, 50.0, 50.0], _batteria(), 1.0)
    assert carica == pytest.approx([0.0, 0.0, 0.0])
    assert scarica == pytest.approx([0.0, 0.0, 0.0])


def test_il_rendimento_rende_non_conveniente_un_differenziale_troppo_piccolo():
    """
    Con rendimento di ciclo 0,81 serve un prezzo di vendita almeno 1/0,81 volte quello di
    acquisto perche' l'operazione sia conveniente. Con 100 e 110 il differenziale non basta
    e la batteria resta ferma; con 100 e 200 conviene.
    """
    b = _batteria(rendimento_carica=0.9, rendimento_scarica=0.9)
    carica, scarica = bt.profilo_ottimo([100.0, 110.0], b, 1.0)
    assert scarica == pytest.approx([0.0, 0.0])

    carica, scarica = bt.profilo_ottimo([100.0, 200.0], b, 1.0)
    assert carica[0] > 0 and scarica[1] > 0


def test_la_capacita_limita_l_energia_accumulata():
    """
    Una batteria da 10 MW ma soli 5 MWh, su periodi di un'ora, non puo' caricare piu' di
    5 MWh in tutto: la potenza da sola non basta.
    """
    b = _batteria(capacita_mwh=5.0)
    carica, scarica = bt.profilo_ottimo([10.0, 10.0, 100.0], b, 1.0)
    assert float(np.sum(carica)) == pytest.approx(5.0)
    assert float(np.sum(scarica)) == pytest.approx(5.0)


def test_la_durata_del_periodo_entra_nel_bilancio_energetico():
    """
    Sugli stessi prezzi, con periodi da un quarto d'ora una batteria da 10 MW accumula
    2,5 MWh per periodo invece di 10: per riempire 10 MWh servono quattro periodi.
    """
    b = _batteria(capacita_mwh=10.0)
    prezzi = [10.0] * 4 + [100.0] * 4
    carica, scarica = bt.profilo_ottimo(prezzi, b, 0.25)
    assert float(np.sum(carica) * 0.25) == pytest.approx(10.0)
    assert carica[:4] == pytest.approx([10.0] * 4)


def test_il_ciclo_chiuso_impone_lo_stato_finale():
    """
    Con ciclo chiuso la batteria deve tornare allo stato iniziale: partendo da vuota non
    puo' terminare carica, anche se il prezzo finale fosse basso e converrebbe accumulare.
    """
    b = _batteria(ciclo_chiuso=True)
    carica, scarica = bt.profilo_ottimo([100.0, 10.0], b, 1.0)
    energia = bt.stato_di_carica(carica, scarica, b, 1.0)
    assert energia[-1] == pytest.approx(0.0)


def test_lo_stato_di_carica_resta_nei_limiti():
    """Il vincolo di capacita' vale in ogni periodo, non solo alla fine."""
    b = _batteria(capacita_mwh=10.0)
    prezzi = [10.0, 20.0, 5.0, 100.0, 90.0]
    carica, scarica = bt.profilo_ottimo(prezzi, b, 1.0)
    energia = bt.stato_di_carica(carica, scarica, b, 1.0)
    assert energia.min() >= -1e-6
    assert energia.max() <= b.capacita_mwh + 1e-6


# --------------------------------------------------------------------------------------
# Effetto di retroazione sul prezzo
# --------------------------------------------------------------------------------------
def _giornata(prezzi_attesi: list[float], gradino: float = 100.0,
              passo: float = 10.0) -> pd.DataFrame:
    """
    Costruisce una giornata di aste orarie con un prezzo di equilibrio noto e una curva di
    offerta a gradini regolari, cosi' che l'effetto di una batteria sia calcolabile a mano.

    In ciascun periodo l'offerta e' composta da undici gradini di ampiezza `gradino` MW, ai
    prezzi da `prezzo - 5*passo` a `prezzo + 5*passo`; la domanda e' price taker per
    5,5 gradini. L'equilibrio cade cosi' **a meta' del sesto gradino**, cioe' al prezzo
    voluto e con mezzo gradino di margine su entrambi i lati: una batteria piu' piccola di
    mezzo gradino non muove il prezzo, una piu' grande lo sposta di `passo` per ogni gradino
    che consuma.

    Un dettaglio che conta: se l'equilibrio cadesse esattamente sullo spigolo fra due
    gradini, qualunque quantita' aggiunta lo spingerebbe al gradino successivo, e il
    comportamento osservato sarebbe un artefatto della costruzione anziche' un risultato.
    """
    righe = []
    for periodo, prezzo in enumerate(prezzi_attesi, start=1):
        for k in range(11):
            righe.append({
                "PURPOSE_CD": "OFF", "ENERGY_PRICE_NO": prezzo + passo * (k - 5),
                "QUANTITY_NO": gradino, "STATUS_CD": "ACC", "ZONE_CD": "NORD",
                "PERIOD": periodo, "GRANULARITY": "PT60", "OFFER_TYPE": "S",
                "BLOCK_ID": "", "AWARDED_QUANTITY_NO": 0.0,
            })
        righe.append({
            "PURPOSE_CD": "BID", "ENERGY_PRICE_NO": 4000.0, "QUANTITY_NO": 5.5 * gradino,
            "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo,
            "GRANULARITY": "PT60", "OFFER_TYPE": "S", "BLOCK_ID": "",
            "AWARDED_QUANTITY_NO": 0.0,
        })
    return pd.DataFrame(righe)


def test_la_giornata_di_prova_ha_i_prezzi_attesi():
    """Controllo dell'impalcatura: senza batteria i prezzi sono quelli costruiti."""
    df = _giornata([100.0, 300.0])
    ric = curve.clearing_giorno(df, "PT60", con_import=False)
    assert ric["prezzo"].tolist() == [100.0, 300.0]


def test_la_batteria_alza_il_prezzo_dove_carica_e_lo_abbassa_dove_scarica():
    """
    E' l'effetto di retroazione, ed e' quantificabile: una batteria da 100 MW consuma un
    gradino intero, quindi sposta il prezzo di un passo. Caricando nel periodo a 100 EUR lo
    porta a 110, scaricando in quello a 300 lo porta a 290. Il differenziale che sfrutta
    passa da 200 a 180 EUR per effetto della sua stessa azione.
    """
    df = _giornata([100.0, 300.0], gradino=100.0, passo=10.0)
    b = _batteria(potenza_mw=100.0, capacita_mwh=100.0, ciclo_chiuso=True)
    esito = bt.simula_giorno(df, b, "PT60", con_import=False)

    assert esito.profilo["carica_mw"].tolist() == pytest.approx([100.0, 0.0])
    assert esito.profilo["scarica_mw"].tolist() == pytest.approx([0.0, 100.0])
    assert esito.profilo["prezzo_con_batteria"].tolist() == pytest.approx([110.0, 290.0])


def test_il_ricavo_effettivo_e_inferiore_a_quello_calcolato_sui_prezzi_di_partenza():
    """
    Chi ottimizza sui prezzi osservati e ignora la retroazione si aspetta 300 x 100 -
    100 x 100 = 20.000 euro, ma ne incassa 290 x 100 - 110 x 100 = 18.000: la differenza e'
    il costo dell'illusione di essere price taker.
    """
    df = _giornata([100.0, 300.0])
    b = _batteria(potenza_mw=100.0, capacita_mwh=100.0, ciclo_chiuso=True)
    esito = bt.simula_giorno(df, b, "PT60", con_import=False)
    assert esito.ricavo_prezzi_dati == pytest.approx(20000.0)
    assert esito.ricavo == pytest.approx(18000.0)


def test_una_batteria_piccola_non_muove_il_prezzo():
    """
    Sotto il mezzo gradino di margine l'ipotesi di price taker e' innocua: i prezzi restano
    quelli di partenza e i due ricavi coincidono.
    """
    df = _giornata([100.0, 300.0], gradino=100.0)
    b = _batteria(potenza_mw=10.0, capacita_mwh=10.0, ciclo_chiuso=True)
    esito = bt.simula_giorno(df, b, "PT60", con_import=False)
    assert esito.variazione_prezzo_media == pytest.approx(0.0)
    assert esito.ricavo == pytest.approx(esito.ricavo_prezzi_dati)


def test_i_cicli_equivalenti_contano_gli_svuotamenti():
    """
    Una batteria da 100 MWh che immette in rete 100 MWh nella giornata ha compiuto un ciclo
    equivalente, indipendentemente da come lo ha distribuito nel tempo.
    """
    df = _giornata([100.0, 300.0])
    b = _batteria(potenza_mw=100.0, capacita_mwh=100.0, ciclo_chiuso=True)
    esito = bt.simula_giorno(df, b, "PT60", con_import=False)
    assert esito.cicli_equivalenti == pytest.approx(1.0)
    assert esito.energia_ciclata_mwh == pytest.approx(100.0)


# --------------------------------------------------------------------------------------
# Erosione di profitto: i due profitti a piano invariato
# --------------------------------------------------------------------------------------
def test_i_due_profitti_coincidono_se_la_taglia_e_trascurabile():
    """
    Sotto il margine del gradino l'accumulo non muove il prezzo, quindi il profitto price
    maker coincide con quello price taker e l'erosione e' nulla. E' la definizione stessa di
    price taker: non e' un'ipotesi, e' una proprieta' verificabile.
    """
    df = _giornata([100.0, 300.0], gradino=100.0)
    e = bt.erosione(df, potenza_aggregata_mw=10.0, granularita="PT60", durata_ore=1.0,
                    con_import=False)
    assert e.erosione_assoluta == pytest.approx(0.0)
    assert e.erosione_relativa == pytest.approx(0.0)
    assert e.profitto_price_maker == pytest.approx(e.profitto_price_taker)


def test_l_erosione_e_la_quota_di_profitto_distrutta():
    """
    Una flotta da 100 MW consuma un gradino e sposta i prezzi da (100, 300) a (110, 290).
    Il profitto atteso e' 300x100 - 100x100 = 20.000 euro, quello realizzato
    290x100 - 110x100 = 18.000: l'erosione vale 2.000 euro, cioe' il 10%.

    I rendimenti sono posti pari a uno perche' il conto resti verificabile a mano; con i
    valori realistici (0,95 per verso) la scarica sarebbe limitata a 90,25 MW e i due
    profitti varrebbero 17.075 e 15.247 euro.
    """
    df = _giornata([100.0, 300.0], gradino=100.0, passo=10.0)
    e = bt.erosione(df, potenza_aggregata_mw=100.0, granularita="PT60", durata_ore=1.0,
                    con_import=False, rendimento_carica=1.0, rendimento_scarica=1.0)
    assert e.profitto_price_taker == pytest.approx(20000.0)
    assert e.profitto_price_maker == pytest.approx(18000.0)
    assert e.erosione_assoluta == pytest.approx(2000.0)
    assert e.erosione_relativa == pytest.approx(0.10)


def test_l_erosione_cresce_con_la_capacita_installata():
    """
    E' il fenomeno che la tesi vuole misurare: piu' accumulo entra in mercato, piu' esso
    stesso comprime il differenziale da cui trae profitto.
    """
    df = _giornata([100.0, 300.0], gradino=100.0)
    valori = [bt.erosione(df, potenza_aggregata_mw=k, granularita="PT60", durata_ore=1.0,
                          con_import=False).erosione_relativa
              for k in (100.0, 200.0, 300.0)]
    assert valori[0] < valori[1] < valori[2]


def test_il_piano_e_lo_stesso_nei_due_profitti():
    """
    L'erosione deve misurare solo l'effetto sul prezzo: il piano non viene riottimizzato sui
    prezzi nuovi (D-25). Lo si verifica confrontando il piano con quello ottimo calcolato
    sui soli prezzi di riferimento.
    """
    df = _giornata([100.0, 300.0], gradino=100.0)
    e = bt.erosione(df, potenza_aggregata_mw=100.0, granularita="PT60", durata_ore=1.0,
                    con_import=False)
    atteso_carica, atteso_scarica = bt.profilo_ottimo(
        e.profilo["prezzo_riferimento"].to_numpy(),
        bt.flotta(100.0, 1.0), 1.0)
    assert e.profilo["carica_mw"].to_numpy() == pytest.approx(atteso_carica)
    assert e.profilo["scarica_mw"].to_numpy() == pytest.approx(atteso_scarica)


def test_col_piano_vuoto_l_erosione_e_nulla_per_definizione():
    """
    Con prezzi piatti il differenziale non copre il costo di degrado e il piano ottimo e'
    non fare nulla. La batteria non tocca il mercato e non ha profitto da erodere: l'erosione
    e' allora **zero per definizione**, non indefinita (0/0) e non mancante (D-31).

    Il giorno resta nel campione, coerentemente con D-29: scartarlo introdurrebbe proprio il
    bias verso i giorni ad alta rinnovabile che D-29 vuole evitare.
    """
    df = _giornata([100.0, 100.0], gradino=100.0)
    e = bt.erosione(df, potenza_aggregata_mw=100.0, granularita="PT60", durata_ore=1.0,
                    con_import=False)
    assert e.piano_vuoto
    assert e.profitto_price_taker == pytest.approx(0.0)
    assert e.erosione_relativa == 0.0
    assert e.erosione_assoluta == 0.0
    assert e.energia_ciclata_mwh == pytest.approx(0.0)


def test_col_piano_non_vuoto_ma_profitto_irrisorio_il_rapporto_non_si_calcola():
    """
    Caso distinto dal precedente: il piano c'e' ma il profitto e' cosi' piccolo che il
    rapporto sarebbe dominato dal rumore. Qui l'erosione relativa resta NaN (D-29), mentre
    quella assoluta e' definita. Serve a verificare che D-31 non abbia inghiottito D-29.
    """
    df = _giornata([100.0, 100.1], gradino=100.0)
    e = bt.erosione(df, potenza_aggregata_mw=1.0, granularita="PT60", durata_ore=1.0,
                    con_import=False, costo_variabile_eur_mwh=0.0,
                    rendimento_carica=1.0, rendimento_scarica=1.0)
    assert not e.piano_vuoto
    assert 0.0 < e.profitto_price_taker < bt.PROFITTO_MINIMO_PER_RAPPORTO
    assert np.isnan(e.erosione_relativa)
    assert np.isfinite(e.erosione_assoluta)


def test_il_costo_variabile_impone_un_differenziale_minimo():
    """
    Il costo di degrado si applica alla sola scarica: un ciclo completo costa `k` una volta,
    non due (D-32). Con k = 12 EUR/MWh un differenziale di 5 EUR non basta a giustificare il
    ciclo, mentre uno di 60 si'.
    """
    piatta = _giornata([100.0, 105.0], gradino=100.0)
    ampia = _giornata([100.0, 160.0], gradino=100.0)

    ferma = bt.erosione(piatta, potenza_aggregata_mw=10.0, granularita="PT60",
                        durata_ore=1.0, con_import=False)
    attiva = bt.erosione(ampia, potenza_aggregata_mw=10.0, granularita="PT60",
                         durata_ore=1.0, con_import=False)

    assert ferma.piano_vuoto
    assert not attiva.piano_vuoto
    assert attiva.profitto_price_taker > 0.0


def test_i_parametri_di_riferimento_arrivano_dalla_configurazione():
    """
    I default di rendimento, costo variabile e durata non sono scritti in `batteria.py` ma
    presi da `config.PARAMETRI_BESS`, che ne documenta la fonte (D-32). Se qualcuno cambia
    la configurazione, il modello deve seguirla.
    """
    b = bt.flotta(100.0)
    assert b.rendimento_ciclo == pytest.approx(config.PARAMETRI_BESS["rendimento_ciclo"])
    assert b.rendimento_carica == pytest.approx(b.rendimento_scarica)
    assert b.costo_variabile_eur_mwh == pytest.approx(
        config.PARAMETRI_BESS["costo_variabile_eur_mwh"])
    assert b.durata_ore == pytest.approx(config.PARAMETRI_BESS["durata_ore"])
    assert b.capacita_mwh == pytest.approx(100.0 * config.PARAMETRI_BESS["durata_ore"])


def test_la_flotta_aggrega_potenza_e_durata():
    """K MW con durata di quattro ore sono 4K MWh di capacita' energetica."""
    f = bt.flotta(250.0, durata_ore=4.0)
    assert f.potenza_mw == 250.0
    assert f.capacita_mwh == 1000.0
    assert f.durata_ore == 4.0
    assert f.ciclo_chiuso is True


# --------------------------------------------------------------------------------------
# Soglia stocastica e bootstrap
# --------------------------------------------------------------------------------------
def _tabella_erosioni(pendenze: dict[str, float], griglia=(100, 200, 300, 400, 500)):
    """Tabella giorno x capacita' con erosione lineare nella capacita', per giorno."""
    righe = []
    for giorno, pendenza in pendenze.items():
        for k in griglia:
            righe.append({"data": giorno, "potenza_mw": float(k),
                          "erosione_relativa": pendenza * k,
                          "stagione": "inverno" if giorno < "d3" else "estate"})
    return pd.DataFrame(righe)


def test_la_soglia_cade_dove_il_quantile_incrocia_il_livello_dichiarato():
    """
    Con quattro giorni la cui erosione cresce di 0,02%, 0,04%, 0,06% e 0,08% ogni 100 MW, il
    90esimo percentile fra i giorni segue quasi il giorno peggiore. Cercando dove supera il
    10% si ottiene una soglia vicina ai 130 MW, e comunque compresa fra i 125 del giorno
    peggiore e i 167 del penultimo.
    """
    tabella = _tabella_erosioni({"d1": 0.0002, "d2": 0.0004, "d3": 0.0006, "d4": 0.0008})
    esito = bt.bootstrap_soglia(tabella, soglia=0.10, quantile=0.90, n_boot=200)
    assert len(esito) == 1
    riga = esito.iloc[0]
    assert 125.0 <= riga["K_stella"] <= 170.0
    assert riga["K_inf"] <= riga["K_stella"] <= riga["K_sup"]
    assert riga["n_giorni"] == 4


def test_una_soglia_mai_raggiunta_viene_segnalata_e_non_inventata():
    """
    Se entro la griglia di capacita' l'erosione non arriva mai al livello dichiarato, la
    soglia non esiste nel campione simulato: va restituito NaN e contata la quota di
    ricampionamenti senza attraversamento, non estrapolato un valore.
    """
    tabella = _tabella_erosioni({"d1": 0.00001, "d2": 0.00002})
    esito = bt.bootstrap_soglia(tabella, soglia=0.50, quantile=0.90, n_boot=50)
    assert np.isnan(esito.iloc[0]["K_stella"])
    assert esito.iloc[0]["quota_senza_attraversamento"] == pytest.approx(1.0)


def test_la_stratificazione_produce_una_soglia_per_strato():
    """La soglia non e' stazionaria: stratificando si ottiene una stima per gruppo (D-28)."""
    tabella = _tabella_erosioni({"d1": 0.0002, "d2": 0.0003, "d3": 0.0008, "d4": 0.0009})
    esito = bt.bootstrap_soglia(tabella, soglia=0.10, quantile=0.90, n_boot=100,
                                strato="stagione")
    assert set(esito["strato"]) == {"inverno", "estate"}
    inverno = esito.loc[esito.strato == "inverno", "K_stella"].iloc[0]
    estate = esito.loc[esito.strato == "estate", "K_stella"].iloc[0]
    # In estate l'erosione cresce piu' in fretta, quindi la soglia arriva prima.
    assert estate < inverno


def test_il_bootstrap_e_riproducibile():
    """Con lo stesso seme si ottiene lo stesso intervallo: i risultati vanno replicabili."""
    tabella = _tabella_erosioni({"d1": 0.0002, "d2": 0.0005, "d3": 0.0007})
    primo = bt.bootstrap_soglia(tabella, n_boot=100, seme=7)
    secondo = bt.bootstrap_soglia(tabella, n_boot=100, seme=7)
    assert primo.iloc[0]["K_inf"] == secondo.iloc[0]["K_inf"]
    assert primo.iloc[0]["K_sup"] == secondo.iloc[0]["K_sup"]


def test_la_curva_di_erosione_riassume_i_quantili_per_capacita():
    """La curva quantile-contro-capacita' e' cio' che si porta in tesi accanto alla soglia."""
    tabella = _tabella_erosioni({"d1": 0.0002, "d2": 0.0006})
    curva = bt.curva_erosione(tabella, quantili=(0.5, 0.9))
    assert list(curva["potenza_mw"]) == [100.0, 200.0, 300.0, 400.0, 500.0]
    assert curva["q50"].is_monotonic_increasing
    assert (curva["n_giorni"] == 2).all()


def test_il_pavimento_si_sottrae_giorno_per_giorno():
    """
    Il pavimento e' l'erosione misurata alla capacita' piu' piccola, che per costruzione non
    puo' essere un effetto di mercato. Va sottratto **per giornata**, perche' dipende da dove
    cade l'equilibrio in quella giornata, non da una costante generale.
    """
    tabella = pd.DataFrame({
        "data": ["d1", "d1", "d1", "d2", "d2", "d2"],
        "potenza_mw": [1.0, 100.0, 200.0, 1.0, 100.0, 200.0],
        "erosione_relativa": [0.02, 0.05, 0.09, 0.00, 0.04, 0.10],
    })
    netta = bt.sottrai_pavimento(tabella)
    assert netta["erosione_netta"].tolist() == pytest.approx([0.0, 0.03, 0.07, 0.0, 0.04, 0.10])


def test_il_pavimento_non_produce_valori_negativi():
    """
    Se in una giornata l'erosione a capacita' grande fosse minore del pavimento — puo'
    succedere perche' il salto di gradino sparisce quando la curva si sposta — il risultato
    va troncato a zero invece di diventare negativo, che non avrebbe senso.
    """
    tabella = pd.DataFrame({
        "data": ["d1", "d1"],
        "potenza_mw": [1.0, 100.0],
        "erosione_relativa": [0.05, 0.02],
    })
    netta = bt.sottrai_pavimento(tabella)
    assert netta["erosione_netta"].tolist() == pytest.approx([0.0, 0.0])


def test_la_soglia_richiede_le_colonne_attese():
    """Un errore esplicito e' meglio di un risultato calcolato su dati incompleti."""
    with pytest.raises(ValueError, match="colonne mancanti"):
        bt.bootstrap_soglia(pd.DataFrame({"data": ["d1"], "potenza_mw": [100.0]}))


def test_la_batteria_grande_erode_il_proprio_margine():
    """
    Il meccanismo centrale della tesi: raddoppiando la taglia il ricavo **non** raddoppia,
    perche' ogni gradino consumato peggiora il prezzo di acquisto e quello di vendita. Il
    ricavo per MW installato e' quindi decrescente.
    """
    df = _giornata([100.0, 300.0])
    piccola = bt.simula_giorno(df, _batteria(potenza_mw=100.0, capacita_mwh=100.0,
                                             ciclo_chiuso=True), "PT60", con_import=False)
    grande = bt.simula_giorno(df, _batteria(potenza_mw=200.0, capacita_mwh=200.0,
                                            ciclo_chiuso=True), "PT60", con_import=False)
    assert grande.ricavo > piccola.ricavo
    assert grande.ricavo < 2 * piccola.ricavo
    assert grande.ricavo / 200.0 < piccola.ricavo / 100.0
