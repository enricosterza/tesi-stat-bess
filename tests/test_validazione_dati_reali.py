"""
Test di validazione su dati reali: la ricostruzione riproduce il prezzo ufficiale?

A differenza degli altri test, che girano su casi giocattolo calcolabili a mano, questi
verificano la pipeline sulle curve d'asta vere. Servono a proteggere il risultato che sta
alla base di tutto il lavoro: se il clearing sulle curve reali smettesse di riprodurre il
prezzo ufficiale, ogni prezzo controfattuale calcolato su quelle curve sarebbe privo di
fondamento.

I test **si saltano da soli** quando la cache dei dati non e' presente, cosi' la suite resta
eseguibile su una macchina senza i 6 GB di archivio GME. Per popolarla basta eseguire una
volta lo script di caricamento.

La misura completa, su un mese intero e con la scomposizione per giorno, ora e congestione,
sta in `scripts/03_valida_mese.py`: qui si verifica solo che l'ordine di grandezza sia quello
atteso, cioe' che nulla si sia rotto.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp import config, curve, io_gme  # noqa: E402

#: Giornata su cui girano i test: e' la prima di gennaio 2025, mercato orario.
GIORNO = "20250115"


def _carica():
    """Carica la giornata dalla cache, saltando il test se i dati non ci sono."""
    granularita = config.granularita_prevalente(GIORNO)
    cache = config.INTERIM_DIR / f"offerte_{GIORNO}_TUTTE_ALL.parquet"
    if not cache.exists():
        pytest.skip(f"cache assente ({cache.name}): eseguire prima uno script di caricamento")
    df = io_gme.carica_giorno(data=GIORNO, zona=None)
    perimetro = ["NORD"] + [
        z for z in config.ZONE_FRONTIERA_NORD if z in set(df["ZONE_CD"].dropna().unique())
    ]
    return df, granularita, perimetro


def test_il_prezzo_ufficiale_e_unico_entro_zona_e_periodo():
    """
    Presupposto del confronto: essendo l'asta a prezzo uniforme, il prezzo di assegnazione
    deve essere lo stesso per tutte le offerte accettate di una zona e di un periodo. Se
    cadesse, il termine di paragone della validazione non esisterebbe.
    """
    df, granularita, _ = _carica()
    prezzi = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)
    assert (prezzi["n_valori_distinti"] == 1).all()
    assert len(prezzi) == config.GRANULARITA_PERIODI[granularita]


def test_il_clearing_sulle_curve_reali_riproduce_il_prezzo_ufficiale():
    """
    Il test che conta: sulle curve vere, senza accumulo, il prezzo ricostruito deve
    coincidere con quello effettivamente formatosi sul mercato.

    Le soglie sono volutamente piu' larghe dei valori misurati (sul mese di gennaio 2025:
    errore mediano nullo, prezzo esatto nel 52% delle ore, entro 5 euro nel 99,5%), perche'
    qui interessa intercettare una rottura, non certificare l'accuratezza: quella si misura
    con lo script mensile.
    """
    df, granularita, perimetro = _carica()
    ricostruito = curve.clearing_giorno_con_blocchi(
        df, granularita, zone=perimetro, includi_altra_granularita=True, con_import=True
    )
    ufficiale = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)
    esito = curve.confronta_con_ufficiale(ricostruito, ufficiale)

    assert esito["n_ricostruiti"] == esito["n_periodi"], "alcune aste non hanno equilibrio"
    assert esito["errore_mediano"] < 1.0
    assert esito["match_5.0"] >= 90.0
    assert abs(esito["bias_mediano"]) < 1.0


def test_la_frequenza_di_match_misura_quanto_la_zona_e_isolata():
    """
    La frequenza di match non e' solo un indicatore di qualita' del codice: e' la misura di
    quanto la zona NORD si comporti davvero come un mercato a se' stante una volta
    reintrodotto lo scambio con l'esterno. Il confronto fra il perimetro allargato e la sola
    zona NORD quantifica il contributo delle frontiere.
    """
    df, granularita, perimetro = _carica()
    ufficiale = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)

    misure = {}
    for nome, zone in [("solo NORD", ["NORD"]), ("NORD + frontiere", perimetro)]:
        ric = curve.clearing_giorno_con_blocchi(df, granularita, zone=zone,
                                                includi_altra_granularita=True, con_import=True)
        misure[nome] = curve.confronta_con_ufficiale(ric, ufficiale)

    # Entrambi i perimetri devono restare utilizzabili: lo scambio netto assorbe la parte
    # maggiore dell'effetto delle frontiere, quindi la differenza fra i due e' contenuta.
    for nome, esito in misure.items():
        assert esito["match_5.0"] >= 80.0, f"perimetro {nome} troppo impreciso"


def test_senza_scambio_netto_il_prezzo_e_sistematicamente_troppo_alto():
    """
    Controlla che il blocco di scambio netto continui a fare quello che deve. Senza di esso
    la zona, che e' importatrice, non trova offerta interna sufficiente e il prezzo
    ricostruito risulta molto piu' alto di quello vero: e' l'errore di circa 100 euro/MWh
    che ha motivato la decisione D-16.
    """
    df, granularita, perimetro = _carica()
    ufficiale = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)

    senza = curve.confronta_con_ufficiale(
        curve.clearing_giorno(df, granularita, zone=perimetro,
                              includi_altra_granularita=True, con_import=False),
        ufficiale,
    )
    con = curve.confronta_con_ufficiale(
        curve.clearing_giorno(df, granularita, zone=perimetro,
                              includi_altra_granularita=True, con_import=True),
        ufficiale,
    )
    assert senza["bias_mediano"] > 10.0
    assert con["errore_mediano"] < senza["errore_mediano"] / 10
