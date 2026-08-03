"""
Test della ricostruzione delle curve e del prezzo di equilibrio.

I casi sono volutamente minuscoli e costruiti a mano: il risultato atteso si calcola su un
foglio di carta, quindi se il test fallisce l'errore e' nel codice e non nell'aspettativa.
Ogni test documenta il ragionamento economico che verifica.

Esecuzione:
    .\\.venv\\Scripts\\python.exe -m pytest tests -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp import config, curve  # noqa: E402


# --------------------------------------------------------------------------------------
# Utilita' per costruire insiemi di offerte giocattolo
# --------------------------------------------------------------------------------------
def offerte(vendite: list[tuple[float, float]], acquisti: list[tuple[float, float]],
            zona: str = "NORD", periodo: int = 1, granularita: str = "PT15",
            stato: str = "ACC") -> pd.DataFrame:
    """Costruisce un DataFrame di offerte da due liste di coppie (prezzo, quantita')."""
    righe = []
    for p, q in vendite:
        righe.append({"PURPOSE_CD": config.PURPOSE_VENDITA, "ENERGY_PRICE_NO": p,
                      "QUANTITY_NO": q, "STATUS_CD": stato, "ZONE_CD": zona,
                      "PERIOD": periodo, "GRANULARITY": granularita})
    for p, q in acquisti:
        righe.append({"PURPOSE_CD": config.PURPOSE_ACQUISTO, "ENERGY_PRICE_NO": p,
                      "QUANTITY_NO": q, "STATUS_CD": stato, "ZONE_CD": zona,
                      "PERIOD": periodo, "GRANULARITY": granularita})
    return pd.DataFrame(righe)


# --------------------------------------------------------------------------------------
# Curve a gradini
# --------------------------------------------------------------------------------------
def test_curva_offerta_e_crescente_e_cumulata():
    """
    L'offerta si ordina per prezzo crescente (merit order) e si cumula: a 20 euro sono
    disponibili sia i 50 MWh offerti a 10 sia i 30 offerti a 20.
    """
    df = offerte(vendite=[(20, 30), (10, 50), (40, 100)], acquisti=[(50, 10)])
    c = curve.curva_offerta(df)
    assert c["prezzo"].tolist() == [10, 20, 40]
    assert c["quantita_cumulata"].tolist() == [50, 80, 180]


def test_curva_domanda_e_decrescente_e_cumulata():
    """
    La domanda si ordina per prezzo decrescente: chi offre 60 compra a qualunque prezzo
    minore, quindi a 30 euro la domanda cumulata comprende anche la sua quantita'.
    """
    df = offerte(vendite=[(10, 10)], acquisti=[(30, 40), (60, 60), (15, 100)])
    c = curve.curva_domanda(df)
    assert c["prezzo"].tolist() == [60, 30, 15]
    assert c["quantita_cumulata"].tolist() == [60, 100, 200]


def test_offerte_allo_stesso_prezzo_formano_un_solo_gradino():
    """Due offerte allo stesso prezzo sono indistinguibili nella curva aggregata."""
    df = offerte(vendite=[(25, 10), (25, 15), (30, 5)], acquisti=[(99, 1)])
    c = curve.curva_offerta(df)
    assert len(c) == 2
    assert c["quantita_cumulata"].tolist() == [25, 30]


# --------------------------------------------------------------------------------------
# Prezzo di equilibrio
# --------------------------------------------------------------------------------------
def test_equilibrio_con_incrocio_esatto():
    """
    Caso costruito perche' le curve si incrocino esattamente.

        offerta:  10 EUR x 50 | 20 EUR x 50 | 40 EUR x 100
        domanda:  60 EUR x 60 | 30 EUR x 40 | 15 EUR x 100

    A 20 EUR l'offerta cumulata vale 100 (50 + 50) e la domanda cumulata vale 100
    (60 + 40): e' il primo prezzo in cui l'offerta raggiunge la domanda.
    """
    df = offerte(vendite=[(10, 50), (20, 50), (40, 100)],
                 acquisti=[(60, 60), (30, 40), (15, 100)])
    eq = curve.prezzo_equilibrio(df)
    assert eq.esiste
    assert eq.prezzo == 20
    assert eq.quantita == 100
    assert eq.offerta_cumulata == 100
    assert eq.domanda_cumulata == 100


def test_equilibrio_con_offerta_marginale_accettata_in_parte():
    """
    Quando l'incrocio non e' esatto, l'offerta marginale entra solo in parte: la quantita'
    scambiata e' il minimo fra i due lati.

        offerta:  10 EUR x 30 | 20 EUR x 200
        domanda:  50 EUR x 100

    A 20 EUR: offerta cumulata 230, domanda cumulata 100 -> si scambiano 100 MWh, cioe'
    dei 200 MWh offerti a 20 EUR ne entrano solo 70.
    """
    df = offerte(vendite=[(10, 30), (20, 200)], acquisti=[(50, 100)])
    eq = curve.prezzo_equilibrio(df)
    assert eq.prezzo == 20
    assert eq.quantita == 100
    assert eq.offerta_cumulata == 230


def test_nessun_equilibrio_se_la_domanda_supera_sempre_offerta():
    """
    Se la domanda eccede l'offerta a ogni prezzo non esiste intersezione. E' il caso di
    una zona importatrice modellata come isolata: nessun prezzo richiama abbastanza
    offerta interna (vedi D-01/D-10).
    """
    df = offerte(vendite=[(10, 10)], acquisti=[(4000, 500)])
    eq = curve.prezzo_equilibrio(df)
    assert not eq.esiste
    assert eq.motivo == "domanda_sempre_superiore"


def test_eccesso_di_offerta_porta_al_prezzo_minimo():
    """
    Con offerta abbondante a prezzo zero l'equilibrio cade sul prezzo piu' basso: e' il
    meccanismo che genera i prezzi bassi (o negativi) nelle ore di forte rinnovabile.
    """
    df = offerte(vendite=[(0, 1000)], acquisti=[(100, 50)])
    eq = curve.prezzo_equilibrio(df)
    assert eq.prezzo == 0
    assert eq.quantita == 50


def test_prezzi_negativi_sono_ammessi():
    """I prezzi vanno da -500 a 4000 EUR/MWh: l'algoritmo non deve assumere positivita'."""
    df = offerte(vendite=[(-500, 100), (50, 100)], acquisti=[(-100, 80)])
    eq = curve.prezzo_equilibrio(df)
    assert eq.prezzo == -500
    assert eq.quantita == 80


def test_lato_vuoto_non_produce_equilibrio():
    """Senza offerte di acquisto non c'e' asta."""
    df = offerte(vendite=[(10, 100)], acquisti=[])
    eq = curve.prezzo_equilibrio(df)
    assert not eq.esiste
    assert eq.motivo == "curva_vuota"


def test_il_prezzo_di_equilibrio_e_il_minimo_fra_quelli_ammissibili():
    """
    Se piu' prezzi soddisfano S(p) >= D(p) si sceglie il piu' basso: e' la definizione di
    prezzo marginale d'asta, e sceglierne uno piu' alto remunererebbe i venditori oltre
    quanto necessario a coprire la domanda.
    """
    df = offerte(vendite=[(10, 500)], acquisti=[(80, 100), (60, 100)])
    eq = curve.prezzo_equilibrio(df)
    assert eq.prezzo == 10


# --------------------------------------------------------------------------------------
# Selezione delle offerte e granularita'
# --------------------------------------------------------------------------------------
def test_filtro_su_stato_e_zona():
    """
    Entrano solo gli stati in gara (D-06) e solo le zone del perimetro (D-10):
    un'offerta revocata o di un'altra zona non deve comparire nella curva.
    """
    df = pd.concat([
        offerte([(10, 100)], [(50, 100)], zona="NORD", stato="ACC"),
        offerte([(1, 999)], [], zona="NORD", stato="REV"),      # revocata: esclusa
        offerte([(2, 888)], [], zona="CSUD", stato="ACC"),      # altra zona: esclusa
        offerte([(5, 50)], [], zona="SVIZ", stato="REJ"),       # frontiera: inclusa
    ], ignore_index=True)

    sel = curve.offerte_periodo(df, periodo=1, granularita="PT15", zone=["NORD", "SVIZ"])
    assert len(sel) == 3
    assert set(sel["ENERGY_PRICE_NO"]) == {10, 50, 5}


def test_periodo_va_letto_insieme_alla_granularita():
    """
    Il periodo 10 esiste sia a quarto d'ora sia a ora, ma indica istanti diversi:
    filtrare su PERIOD senza filtrare su GRANULARITY mescolerebbe le due cose.
    """
    df = pd.concat([
        offerte([(10, 100)], [(50, 100)], periodo=10, granularita="PT15"),
        offerte([(20, 700)], [(90, 700)], periodo=10, granularita="PT60"),
    ], ignore_index=True)

    sel = curve.offerte_periodo(df, periodo=10, granularita="PT15")
    assert len(sel) == 2
    assert sel["QUANTITY_NO"].tolist() == [100, 100]


def test_clearing_identico_a_qualunque_granularita():
    """
    La funzione di clearing e' indipendente dalla granularita' (D-15): le stesse offerte
    presentate come PT15, PT30 o PT60 devono dare lo stesso prezzo di equilibrio.
    """
    prezzi = []
    for g in ("PT15", "PT30", "PT60"):
        df = offerte(vendite=[(10, 50), (20, 50), (40, 100)],
                     acquisti=[(60, 60), (30, 40), (15, 100)], granularita=g, periodo=3)
        prezzi.append(curve.prezzo_equilibrio(
            curve.offerte_periodo(df, periodo=3, granularita=g)).prezzo)
    assert prezzi == [20, 20, 20]


@pytest.mark.parametrize("periodo_pt15, ora_attesa", [(1, 1), (4, 1), (5, 2), (40, 10), (96, 24)])
def test_ogni_quarto_dora_appartiene_alla_sua_ora(periodo_pt15, ora_attesa):
    """I quarti 1-4 stanno nell'ora 1, i quarti 37-40 nell'ora 10, i 93-96 nell'ora 24."""
    assert curve.periodo_contenitore(periodo_pt15, "PT60", "PT15") == ora_attesa


@pytest.mark.parametrize("periodo_pt15, ora_attesa", [(1, 1), (40, 10), (96, 24)])
def test_offerta_oraria_entra_nel_quarto_dora_con_quantita_invariata(periodo_pt15, ora_attesa):
    """
    Un'offerta oraria che concorre a un'asta da 15 minuti va cercata nell'ora che contiene
    quel quarto d'ora, e la sua quantita' resta **invariata**: `QUANTITY_NO` e' una potenza
    (MW), non l'energia del periodo, quindi un'offerta di 400 MW per un'ora vale 400 MW in
    ciascuno dei quattro quarti d'ora. Dividerla per quattro sottostimerebbe l'offerta.
    """
    df = pd.concat([
        offerte([(10, 100)], [(50, 100)], periodo=periodo_pt15, granularita="PT15"),
        offerte([(30, 400)], [], periodo=ora_attesa, granularita="PT60"),
        offerte([(99, 999)], [], periodo=ora_attesa + 1, granularita="PT60"),  # altra ora
    ], ignore_index=True)

    sel = curve.offerte_periodo(df, periodo=periodo_pt15, granularita="PT15",
                                includi_altra_granularita=True)
    oraria = sel[sel["GRANULARITY"] == "PT60"]
    assert len(oraria) == 1
    assert oraria["QUANTITY_NO"].iloc[0] == pytest.approx(400.0)
    assert 999 not in sel["QUANTITY_NO"].tolist()


def test_confronto_con_ufficiale_calcola_la_frequenza_di_match():
    """
    Su quattro periodi, due prezzi ricostruiti coincidono con l'ufficiale, uno sbaglia di
    0,4 EUR e uno di 10: il match a 0,01 EUR e' del 50%, quello a 1 EUR del 75%.
    """
    ricostruito = pd.DataFrame({"PERIOD": [1, 2, 3, 4], "prezzo": [100.0, 50.0, 70.4, 30.0]})
    ufficiale = pd.DataFrame({"PERIOD": [1, 2, 3, 4], "prezzo_ufficiale": [100.0, 50.0, 70.0, 40.0]})
    esito = curve.confronta_con_ufficiale(ricostruito, ufficiale)
    assert esito["n_ricostruiti"] == 4
    assert esito["match_0.01"] == pytest.approx(50.0)
    assert esito["match_1.0"] == pytest.approx(75.0)
    assert esito["errore_mediano"] == pytest.approx(0.2)
