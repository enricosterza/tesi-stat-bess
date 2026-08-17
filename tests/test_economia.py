"""
Test del conto economico dell'investitore (livello 2).

I casi sono costruiti perche' il risultato si calcoli a mano: capitale, ricavi e costi a
numeri tondi, tasso di sconto nullo dove serve a rendere trasparente la somma.

Esecuzione:
    .\.venv\Scripts\python.exe -m pytest tests -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp import config, economia  # noqa: E402


def _parametri(**kwargs) -> dict:
    """Parametri economici semplificati: nessuno sconto, nessun decadimento."""
    base = {
        "capex_eur_mwh": 1_000.0,
        "opex_eur_mwh_anno": 0.0,
        "vita_utile_anni": 10.0,
        "degrado_ricavi_annuo": 0.0,
        "tasso_sconto": 0.0,
    }
    base.update(kwargs)
    return base


def _bess(**kwargs) -> dict:
    base = dict(config.PARAMETRI_BESS)
    base.update(kwargs)
    return base


def test_il_van_e_la_somma_dei_flussi_meno_il_capitale():
    """
    Con tasso nullo, nessun decadimento e nessun costo, dieci anni da 100 EUR su un
    capitale di 400 danno 10 x 100 - 400 = 600 EUR.
    """
    c = economia.conto_economico(
        margine_lordo_annuo=100.0, energia_scaricata_annua_mwh=0.0,
        energia_caricata_annua_mwh=0.0, prezzo_medio_acquisto=0.0,
        capacita_mwh=0.4, parametri=_parametri(),
        parametri_bess=_bess(costo_variabile_eur_mwh=0.0, rapporto_prezzo_acquisto=1.0),
    )
    assert c.capex == pytest.approx(400.0)
    assert c.van == pytest.approx(600.0)


def test_con_K_uguale_a_uno_non_c_e_alcun_onere():
    """Il regime net-settled non deve produrre costi aggiuntivi sull'energia prelevata."""
    c = economia.conto_economico(
        margine_lordo_annuo=1_000.0, energia_scaricata_annua_mwh=100.0,
        energia_caricata_annua_mwh=110.0, prezzo_medio_acquisto=50.0,
        capacita_mwh=1.0, parametri=_parametri(),
        parametri_bess=_bess(costo_variabile_eur_mwh=0.0, rapporto_prezzo_acquisto=1.0),
    )
    assert c.onere_acquisto_annuo == pytest.approx(0.0)


def test_l_onere_cresce_in_proporzione_a_K_meno_uno():
    """
    Con K = 2,3 l'onere vale 1,3 volte il valore di mercato dell'energia prelevata:
    1,3 x 110 MWh x 50 EUR/MWh = 7.150 EUR.
    """
    c = economia.conto_economico(
        margine_lordo_annuo=1_000.0, energia_scaricata_annua_mwh=100.0,
        energia_caricata_annua_mwh=110.0, prezzo_medio_acquisto=50.0,
        capacita_mwh=1.0, parametri=_parametri(),
        parametri_bess=_bess(costo_variabile_eur_mwh=0.0, rapporto_prezzo_acquisto=2.3),
    )
    assert c.onere_acquisto_annuo == pytest.approx(7_150.0)
    assert c.ricavo_netto_primo_anno == pytest.approx(1_000.0 - 7_150.0)


def test_il_degrado_e_sottratto_una_volta_sola_sull_energia_scaricata():
    """12 EUR/MWh su 100 MWh scaricati fanno 1.200 EUR l'anno, non il doppio."""
    c = economia.conto_economico(
        margine_lordo_annuo=5_000.0, energia_scaricata_annua_mwh=100.0,
        energia_caricata_annua_mwh=110.0, prezzo_medio_acquisto=50.0,
        capacita_mwh=1.0, parametri=_parametri(),
        parametri_bess=_bess(costo_variabile_eur_mwh=12.0, rapporto_prezzo_acquisto=1.0),
    )
    assert c.costo_degrado_annuo == pytest.approx(1_200.0)
    assert c.ricavo_netto_primo_anno == pytest.approx(3_800.0)


def test_lo_sconto_riduce_il_van():
    """A parita' di flussi, un tasso positivo deve dare un valore attuale inferiore."""
    comune = dict(margine_lordo_annuo=100.0, energia_scaricata_annua_mwh=0.0,
                  energia_caricata_annua_mwh=0.0, prezzo_medio_acquisto=0.0,
                  capacita_mwh=0.1,
                  parametri_bess=_bess(costo_variabile_eur_mwh=0.0,
                                       rapporto_prezzo_acquisto=1.0))
    senza = economia.conto_economico(parametri=_parametri(tasso_sconto=0.0), **comune)
    con = economia.conto_economico(parametri=_parametri(tasso_sconto=0.05), **comune)
    assert con.van < senza.van


def test_l_annualizzazione_riporta_il_campione_a_365_giorni():
    """Trenta giorni da 10 EUR l'uno valgono 121,67 EUR l'anno."""
    assert economia.annualizza(300.0, 30) == pytest.approx(300.0 / 30 * 365)


def test_da_erosioni_usa_il_profitto_price_maker():
    """
    E' la scelta metodologica centrale del capitolo 5: il ricavo dell'investitore e' quello
    che resta dopo che l'accumulo ha spostato i prezzi, non quello illusorio price taker.
    """
    erosioni = pd.DataFrame({
        "data": ["20250101", "20250102"],
        "potenza_mw": [100.0, 100.0],
        "profitto_price_taker": [10_000.0, 10_000.0],
        "profitto_price_maker": [6_000.0, 6_000.0],
        "energia_ciclata_mwh": [400.0, 400.0],
    })
    c = economia.da_erosioni(erosioni, potenza_mw=100.0, prezzo_medio_acquisto=100.0,
                             durata_ore=4.0, parametri=_parametri())
    atteso = economia.annualizza(12_000.0, 2)
    assert c.margine_lordo_annuo == pytest.approx(atteso)
    # Se avesse usato il price taker il margine sarebbe stato di un terzo piu' alto.
    assert c.margine_lordo_annuo < economia.annualizza(20_000.0, 2)


def test_una_capacita_assente_viene_segnalata():
    """Meglio un errore esplicito che un conto economico su una tabella vuota."""
    erosioni = pd.DataFrame({"data": ["20250101"], "potenza_mw": [50.0],
                             "profitto_price_maker": [1.0], "energia_ciclata_mwh": [1.0]})
    with pytest.raises(ValueError, match="Nessuna riga"):
        economia.da_erosioni(erosioni, potenza_mw=999.0, prezzo_medio_acquisto=100.0)
