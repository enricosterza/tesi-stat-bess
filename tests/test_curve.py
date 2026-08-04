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


# --------------------------------------------------------------------------------------
# Scambio netto con l'esterno del perimetro
# --------------------------------------------------------------------------------------
def test_import_abbassa_il_prezzo():
    """
    L'import entra come offerta al prezzo minimo e trasla l'offerta verso destra: con
    250 MW importati la domanda viene coperta senza ricorrere all'offerta cara.

        offerta interna: 300 EUR x 500      domanda: 200 EUR x 250
        senza import -> l'unico prezzo che pareggia e' 300
        con 250 MW di import a prezzo minimo -> l'offerta a buon mercato basta
    """
    df = offerte(vendite=[(300, 500)], acquisti=[(200, 250)])
    assert curve.prezzo_equilibrio(df).prezzo == 300
    con_import = curve.aggiungi_import(df, 250)
    assert curve.prezzo_equilibrio(con_import).prezzo == config.PREZZO_MINIMO


def test_export_alza_il_prezzo():
    """
    L'export e' domanda che viene da fuori il perimetro e compra a qualunque prezzo:
    entra come acquisto al prezzo massimo e trasla la domanda verso destra.

        offerta interna: 10 EUR x 100 | 90 EUR x 100     domanda interna: 200 EUR x 100
        senza export -> equilibrio a 10 (bastano i primi 100 MW)
        con 100 MW esportati -> serve anche l'offerta a 90
    """
    df = offerte(vendite=[(10, 100), (90, 100)], acquisti=[(200, 100)])
    assert curve.prezzo_equilibrio(df).prezzo == 10
    con_export = curve.aggiungi_import(df, -100)
    assert curve.prezzo_equilibrio(con_export).prezzo == 90


def test_scambio_netto_nullo_non_modifica_le_offerte():
    """Un perimetro in pareggio con l'esterno non riceve alcun blocco."""
    df = offerte(vendite=[(10, 100)], acquisti=[(50, 100)])
    assert len(curve.aggiungi_import(df, 0)) == len(df)


def test_import_netto_e_la_differenza_fra_quantita_assegnate():
    """
    L'import netto del perimetro e' la differenza fra acquisti e vendite **assegnati**:
    se in una zona vengono acquistati 900 MW e venduti 400, i 500 mancanti arrivano da
    fuori. Le granularita' si sommano senza riscalare, perche' sono potenze.
    """
    df = pd.DataFrame([
        {"PURPOSE_CD": "BID", "AWARDED_QUANTITY_NO": 900.0, "ZONE_CD": "NORD",
         "PERIOD": 40, "GRANULARITY": "PT15", "STATUS_CD": "ACC"},
        {"PURPOSE_CD": "OFF", "AWARDED_QUANTITY_NO": 400.0, "ZONE_CD": "NORD",
         "PERIOD": 40, "GRANULARITY": "PT15", "STATUS_CD": "ACC"},
        {"PURPOSE_CD": "OFF", "AWARDED_QUANTITY_NO": 700.0, "ZONE_CD": "CSUD",
         "PERIOD": 40, "GRANULARITY": "PT15", "STATUS_CD": "ACC"},   # fuori perimetro
    ])
    assert curve.import_netto(df, 40, "PT15", zone=["NORD"]) == pytest.approx(500.0)


# --------------------------------------------------------------------------------------
# Eccesso di offerta, unicita' dell'equilibrio e sensibilita' del prezzo
# --------------------------------------------------------------------------------------
def test_l_eccesso_di_offerta_e_monotono():
    """
    S non decresce e D non cresce al crescere del prezzo, quindi l'eccesso S - D e'
    monotono non decrescente. E' la proprieta' che garantisce che i prezzi di equilibrio
    formino sempre una semiretta e che quindi l'equilibrio sia ben definito.
    """
    df = offerte(vendite=[(10, 50), (20, 30), (40, 100)],
                 acquisti=[(60, 60), (30, 40), (15, 100)])
    ec = curve.curva_eccesso(df)
    assert ec["eccesso"].is_monotonic_increasing
    assert ec["prezzo"].is_monotonic_increasing


def test_equilibrio_unico_quando_le_curve_si_incrociano_nettamente():
    """Se l'eccesso salta da negativo a positivo, il prezzo di equilibrio e' uno solo."""
    df = offerte(vendite=[(10, 30), (20, 200)], acquisti=[(50, 100)])
    intervallo = curve.intervallo_equilibrio(df)
    assert not intervallo["degenere"]
    assert intervallo["prezzo_minimo"] == intervallo["prezzo_massimo"] == 20


def test_equilibrio_non_unico_quando_l_eccesso_resta_nullo():
    """
    Con offerta 10 EUR x 100 e domanda 60 EUR x 100 piu' 5 EUR x 50, l'eccesso vale zero
    sia a 10 sia a 60 EUR: ogni prezzo fra i due pareggia domanda e offerta. La scelta del
    punto e' allora una convenzione, non un dato, e va segnalata come tale.
    """
    df = offerte(vendite=[(10, 100)], acquisti=[(60, 100), (5, 50)])
    intervallo = curve.intervallo_equilibrio(df)
    assert intervallo["degenere"]
    assert intervallo["prezzo_minimo"] == 10
    assert intervallo["prezzo_massimo"] == 60
    assert intervallo["ampiezza"] == 50
    # La funzione di clearing sceglie l'estremo inferiore.
    assert curve.prezzo_equilibrio(df).prezzo == 10


def test_offerta_aggiuntiva_abbassa_il_prezzo_e_domanda_aggiuntiva_lo_alza():
    """
    E' l'effetto di feedback che la tesi vuole misurare: una batteria che scarica aggiunge
    offerta e abbassa il prezzo, una che carica aggiunge domanda e lo alza.
    """
    df = offerte(vendite=[(10, 100), (90, 100)], acquisti=[(200, 150)])
    scarica = curve.impatto_prezzo(df, +100)
    carica = curve.impatto_prezzo(df, -100)
    assert scarica["variazione"] < 0
    assert carica["variazione"] > 0


def test_la_sensibilita_e_nulla_dove_la_curva_e_ripida():
    """
    Con un gradino di offerta molto ampio al prezzo di equilibrio, 100 MW in piu' non
    spostano il prezzo: la sensibilita' e' nulla. E' la situazione in cui una batteria di
    piccola taglia non ha alcun effetto sul prezzo.
    """
    df = offerte(vendite=[(10, 100), (50, 10000)], acquisti=[(200, 500)])
    assert curve.impatto_prezzo(df, 100)["sensibilita"] == 0.0


# --------------------------------------------------------------------------------------
# Clearing con offerte a blocchi
# --------------------------------------------------------------------------------------
def _giorno_con_blocco(prezzo_blocco: float) -> pd.DataFrame:
    """
    Costruisce una giornata di due periodi con un blocco di vendita che li copre entrambi.

    In ciascun periodo: offerta semplice 10 EUR x 100, domanda 200 EUR x 150.
    Senza il blocco l'equilibrio sarebbe al prezzo dell'offerta cara mancante; il blocco
    offre 100 MW in ognuno dei due periodi al prezzo indicato.
    """
    righe = []
    for periodo in (1, 2):
        righe += [
            {"PURPOSE_CD": "OFF", "ENERGY_PRICE_NO": 10.0, "QUANTITY_NO": 100.0,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo, "GRANULARITY": "PT60",
             "OFFER_TYPE": "S", "BLOCK_ID": "", "AWARDED_QUANTITY_NO": 0.0},
            {"PURPOSE_CD": "OFF", "ENERGY_PRICE_NO": 500.0, "QUANTITY_NO": 100.0,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo, "GRANULARITY": "PT60",
             "OFFER_TYPE": "S", "BLOCK_ID": "", "AWARDED_QUANTITY_NO": 0.0},
            {"PURPOSE_CD": "BID", "ENERGY_PRICE_NO": 200.0, "QUANTITY_NO": 150.0,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo, "GRANULARITY": "PT60",
             "OFFER_TYPE": "S", "BLOCK_ID": "", "AWARDED_QUANTITY_NO": 0.0},
            {"PURPOSE_CD": "OFF", "ENERGY_PRICE_NO": prezzo_blocco, "QUANTITY_NO": 100.0,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo, "GRANULARITY": "PT60",
             "OFFER_TYPE": "B", "BLOCK_ID": "BLK1", "AWARDED_QUANTITY_NO": 0.0},
        ]
    return pd.DataFrame(righe)


def test_blocco_conveniente_viene_accettato():
    """
    Un blocco di vendita a 50 EUR, con l'offerta semplice a buon mercato che copre solo
    100 dei 150 MW domandati, entra in merito: senza di lui il prezzo salirebbe a 500.
    Accettandolo, l'offerta a 10 piu' il blocco a 50 coprono i 150 MW e il prezzo e' 50.
    """
    ric = curve.clearing_giorno_con_blocchi(_giorno_con_blocco(50.0), "PT60",
                                            con_import=False)
    assert ric["blocchi_accettati"].iloc[0] == 1
    assert ric["prezzo"].tolist() == [50.0, 50.0]


def test_blocco_troppo_caro_viene_rifiutato():
    """
    Un blocco offerto a 800 EUR resta fuori mercato: il prezzo di equilibrio senza di lui
    e' 500, quindi il blocco non copre il proprio prezzo e viene rifiutato. E' il
    tutto-o-niente che la ricostruzione a offerte divisibili non sa rappresentare.
    """
    ric = curve.clearing_giorno_con_blocchi(_giorno_con_blocco(800.0), "PT60",
                                            con_import=False)
    assert ric["blocchi_accettati"].iloc[0] == 0
    assert ric["prezzo"].tolist() == [500.0, 500.0]


def test_il_blocco_e_valutato_sulla_media_dei_suoi_periodi():
    """
    Il criterio e' il prezzo **medio ponderato** sui periodi coperti, non il prezzo di
    ciascuno: un blocco resta accettato anche se in un periodo e' fuori mercato, purche'
    negli altri guadagni abbastanza da coprire il proprio prezzo.

    Costruzione: due periodi con offerta 10 EUR x 100 e 500 EUR x 200, e un blocco a
    100 EUR x 100 su entrambi. Nel periodo 1 la domanda e' 250 MW e il prezzo si forma a
    500 (serve l'offerta cara); nel periodo 2 la domanda e' 60 MW e il prezzo e' 10, quindi
    li' il blocco vende sotto il proprio prezzo. La media ponderata vale 255 EUR, sopra i
    100 del blocco, che resta percio' accettato.
    """
    righe = []
    for periodo, domanda in ((1, 250.0), (2, 60.0)):
        righe += [
            {"PURPOSE_CD": "OFF", "ENERGY_PRICE_NO": 10.0, "QUANTITY_NO": 100.0,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo,
             "GRANULARITY": "PT60", "OFFER_TYPE": "S", "BLOCK_ID": "",
             "AWARDED_QUANTITY_NO": 0.0},
            {"PURPOSE_CD": "OFF", "ENERGY_PRICE_NO": 500.0, "QUANTITY_NO": 200.0,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo,
             "GRANULARITY": "PT60", "OFFER_TYPE": "S", "BLOCK_ID": "",
             "AWARDED_QUANTITY_NO": 0.0},
            {"PURPOSE_CD": "BID", "ENERGY_PRICE_NO": 600.0, "QUANTITY_NO": domanda,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo,
             "GRANULARITY": "PT60", "OFFER_TYPE": "S", "BLOCK_ID": "",
             "AWARDED_QUANTITY_NO": 0.0},
            {"PURPOSE_CD": "OFF", "ENERGY_PRICE_NO": 100.0, "QUANTITY_NO": 100.0,
             "STATUS_CD": "ACC", "ZONE_CD": "NORD", "PERIOD": periodo,
             "GRANULARITY": "PT60", "OFFER_TYPE": "B", "BLOCK_ID": "BLK1",
             "AWARDED_QUANTITY_NO": 0.0},
        ]
    ric = curve.clearing_giorno_con_blocchi(pd.DataFrame(righe), "PT60", con_import=False)
    assert ric["blocchi_accettati"].iloc[0] == 1
    assert ric["prezzo"].tolist() == [500.0, 10.0]


def test_il_surplus_e_la_differenza_fra_valore_e_costo_delle_offerte_accettate():
    """
    Con offerta 10 EUR x 100 e domanda 200 EUR x 100, si scambiano 100 MW: il valore per
    chi compra e' 200 x 100 = 20.000 e il costo per chi vende 10 x 100 = 1.000, quindi il
    surplus complessivo vale 19.000. Non dipende dal prezzo di equilibrio, che si limita a
    ripartirlo fra le due parti.
    """
    df = offerte(vendite=[(10, 100)], acquisti=[(200, 100)])
    assert curve.surplus(df) == pytest.approx(19000.0)


def test_il_surplus_conta_solo_le_offerte_accettate():
    """
    Le offerte fuori mercato non contribuiscono: qui la vendita a 500 e l'acquisto a 5
    restano fuori, e il surplus e' quello del solo scambio a buon mercato.
    """
    df = offerte(vendite=[(10, 100), (500, 100)], acquisti=[(200, 100), (5, 100)])
    assert curve.surplus(df) == pytest.approx(19000.0)


def test_senza_equilibrio_il_surplus_e_nullo():
    df = offerte(vendite=[(10, 10)], acquisti=[])
    assert curve.surplus(df) == 0.0


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
