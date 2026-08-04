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
from mgp import curve  # noqa: E402


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
