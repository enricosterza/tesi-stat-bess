"""
Configurazione centrale del progetto: path dei dati e costanti di dominio.

Motivazione
-----------
I dati grezzi GME (~6 GB fra il file XML del 31/03/2026 e l'archivio storico 2015-2026)
NON sono stati spostati dentro una cartella `data/raw/`: sono voluminosi e risiedono in
una cartella sincronizzata su OneDrive, quindi copiarli avrebbe significato duplicare
gigabyte e innescare una risincronizzazione del cloud. Restano dove sono e vengono
raggiunti tramite i path definiti qui: se un domani i dati si spostano, si modifica
soltanto questo file.

Tutte le costanti di dominio (zona di riferimento, granularita', codici dei campi GME)
sono raccolte qui per evitare "stringhe magiche" sparse negli script.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------------------
# Path del progetto
# --------------------------------------------------------------------------------------
# config.py sta in <progetto>/src/mgp/config.py -> parents[2] e' la radice del progetto.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
INTERIM_DIR: Path = DATA_DIR / "interim"        # cache Parquet, rigenerabile
PROCESSED_DIR: Path = DATA_DIR / "processed"    # dataset finali per l'analisi
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
FIGURE_DIR: Path = OUTPUT_DIR / "figure"
TABLE_DIR: Path = OUTPUT_DIR / "tabelle"
DOCS_DIR: Path = PROJECT_ROOT / "docs"

# --------------------------------------------------------------------------------------
# Path dei dati grezzi GME (esterni al versionamento)
# --------------------------------------------------------------------------------------
# File "pilota" su cui e' impostata tutta la messa a punto della pipeline.
XML_PILOTA: Path = PROJECT_ROOT / "20260331MGPOffertePubbliche.xml"
DATA_PILOTA: str = "20260331"

# Archivio storico: un file .zip al giorno (2015-2026), ciascuno contenente l'XML omonimo.
# Nota: la cartella e' annidata due volte (MGP_OffertePubbliche/MGP_OffertePubbliche/).
ARCHIVIO_DIR: Path = PROJECT_ROOT / "MGP_OffertePubbliche" / "MGP_OffertePubbliche"


def path_giorno(data: str) -> Path:
    """
    Restituisce il path del file di offerte pubbliche MGP per una data.

    Parameters
    ----------
    data : str
        Data in formato 'YYYYMMDD' (es. '20260331').

    Returns
    -------
    Path
        Path dell'XML se presente in chiaro nella radice del progetto o nell'archivio,
        altrimenti il path dello .zip corrispondente nell'archivio storico.
        Il lettore (`mgp.io_gme`) sa gestire entrambi i formati.

    Raises
    ------
    FileNotFoundError
        Se non esiste ne' l'XML ne' lo zip per quella data.
    """
    nome = f"{data}MGPOffertePubbliche"
    candidati = [
        PROJECT_ROOT / f"{nome}.xml",
        ARCHIVIO_DIR / f"{nome}.xml",
        ARCHIVIO_DIR / f"{nome}.zip",
    ]
    for c in candidati:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Nessun file di offerte pubbliche trovato per la data {data}. "
        f"Cercato in: {[str(c) for c in candidati]}"
    )


# --------------------------------------------------------------------------------------
# Costanti di dominio (mercato elettrico / dati GME)
# --------------------------------------------------------------------------------------
ZONA_DEFAULT: str = "NORD"

#: Tag XML che delimita un singolo record di offerta nei file GME.
TAG_OFFERTA: str = "OfferteOperatori"

#: Codici di `PURPOSE_CD` (verificati sul file del 31/03/2026).
PURPOSE_ACQUISTO: str = "BID"   # offerta di acquisto  -> costruisce la curva di DOMANDA
PURPOSE_VENDITA: str = "OFF"    # offerta di vendita   -> costruisce la curva di OFFERTA

#: Zone virtuali di frontiera confinanti con NORD (decisione D-10: il perimetro di analisi
#: e' NORD piu' queste zone, senza vincoli di capacita' di transito).
#: ATTENZIONE - da verificare prima dell'uso: nel giorno pilota compaiono anche CORS, MALT,
#: MONT e COAC, che sono frontiere di ALTRE zone (Corsica verso CNOR/SARD, Malta verso SICI)
#: e non vanno incluse. Non compaiono zone per Austria e Slovenia, che pure confinano con
#: NORD: e' il primo controllo da fare (vedi docs/DIARIO.md, voce su D-10).
ZONE_FRONTIERA_NORD: list[str] = ["SVIZ", "FRAN"]

#: Stati delle offerte che hanno effettivamente partecipato all'asta e che quindi
#: compongono le curve di domanda e offerta (decisione D-06; i significati dei codici sono
#: quelli adottati il 03/08/2026, ancora da confermare con il relatore):
#:   ACC  accettata            REJ  rifiutata
#:   PREJ paradossalmente rifiutata (offerte a blocchi in merito sul prezzo ma escluse dal
#:        vincolo "tutto o niente": 20 righe nel giorno pilota, effetto non misurabile)
#: Restano fuori REP (sostituita: la conterebbe due volte), REV (revocata), INC (incongrua).
STATUS_IN_GARA: list[str] = ["ACC", "REJ", "PREJ"]

#: Granularita' presenti nei dati. `PERIOD` va SEMPRE letto insieme a `GRANULARITY`:
#: con PT15 vale 1-96, con PT30 1-48, con PT60 1-24. Filtrare su `PERIOD` senza filtrare
#: la granularita' mescolerebbe quarti d'ora e ore.
GRANULARITA_PERIODI: dict[str, int] = {"PT15": 96, "PT30": 48, "PT60": 24}
GRANULARITA_DEFAULT: str = "PT15"

#: Data in cui il MGP passa dal periodo orario al quarto d'ora. Verificata scandendo
#: l'archivio: il 30/09/2025 le offerte sono al 100% PT60, il 01/10/2025 all'82,8% PT15.
DATA_PASSAGGIO_PT15: str = "20251001"


def granularita_prevalente(data: str) -> str:
    """
    Restituisce la granularita' nativa prevalente di un giorno di mercato (decisione D-12).

    Parameters
    ----------
    data : str
        Data in formato 'YYYYMMDD'.

    Returns
    -------
    str
        'PT60' per i giorni fino al 30/09/2025, 'PT15' dal 01/10/2025.

    Perche' serve
    -------------
    Non esiste una granularita' unica valida per tutto il campione: nel 2025 i primi nove
    mesi sono orari e gli ultimi tre a quarto d'ora. Ogni giorno va quindi elaborato alla
    sua risoluzione nativa, e in ogni giorno resta una quota minoritaria di offerte
    all'altra granularita' (4-5% dopo il passaggio), il cui trattamento e' la questione
    aperta D-13.
    """
    return "PT15" if data >= DATA_PASSAGGIO_PT15 else "PT60"

#: Durata in ore di un periodo.
#:
#: ATTENZIONE ALLE UNITA': `QUANTITY_NO` e `AWARDED_QUANTITY_NO` sono **potenze (MW)**, non
#: energie riferite al periodo. Verificato confrontando le quantita' assegnate nazionali fra
#: un giorno orario e uno a quarto d'ora: se fossero energie di periodo, passando da PT60 a
#: PT15 dovrebbero ridursi a un quarto, mentre il rapporto osservato e' 0,83 (38.334 MW medi
#: all'ora il 15/01/2025 contro 31.956 MW medi al quarto d'ora il 31/03/2026, differenza
#: spiegata dalla stagionalita' del fabbisogno).
#:
#: Conseguenze: (a) un'offerta oraria vale la stessa potenza in tutti i quarti d'ora che
#: compongono l'ora, senza divisioni; (b) l'energia si ottiene moltiplicando per la durata,
#: e serve solo dove l'energia conta davvero, cioe' nel bilancio della batteria.
DURATA_ORE: dict[str, float] = {"PT15": 0.25, "PT30": 0.5, "PT60": 1.0}


def in_energia(potenza_mw: float, granularita: str) -> float:
    """Converte una potenza (MW) nell'energia del periodo (MWh)."""
    return potenza_mw * DURATA_ORE[granularita]

#: Limiti di prezzo ammessi sul MGP (€/MWh), verificati sul giorno pilota: i prezzi offerti
#: vanno da -500 a 4000 (i prezzi negativi sono ammessi). Un'offerta di ACQUISTO a P_MAX e
#: un'offerta di VENDITA a P_MIN sono "price taker": accettano qualunque prezzo di mercato.
#: Nel giorno pilota, zona NORD: 28.504 acquisti a 4000 (52% delle offerte di acquisto) e
#: 2.197 vendite a -500. Molto piu' numerose (37.705) le vendite offerte a 0 €/MWh, che
#: comprendono i contratti bilaterali e le unita' must-run: sono price taker "di fatto" ma
#: non al limite di prezzo, quindi vengono contate a parte.
PREZZO_MASSIMO: float = 4000.0
PREZZO_MINIMO: float = -500.0

#: Colonne effettivamente utili all'analisi (le altre vengono scartate in lettura).
COLONNE_UTILI: list[str] = [
    "PURPOSE_CD",             # BID / OFF
    "STATUS_CD",              # ACC / REP / REJ / REV / INC / PREJ
    "ZONE_CD",                # zona di mercato
    "PERIOD",                 # periodo del giorno (dipende da GRANULARITY)
    "GRANULARITY",            # PT15 / PT30 / PT60
    "ENERGY_PRICE_NO",        # prezzo offerto, €/MWh
    "QUANTITY_NO",            # quantita' offerta, MW (potenza: vedi nota su DURATA_ORE)
    "ADJ_QUANTITY_NO",        # quantita' rettificata: e' quella su cui l'asta si risolve
    "MINIMUM_ACCEPTANCE_RATIO",  # quota minima accettabile dell'offerta (indivisibilita')
    "AWARDED_QUANTITY_NO",    # quantita' assegnata dall'algoritmo di mercato, MW
    "AWARDED_PRICE_NO",       # prezzo di assegnazione = prezzo zonale ufficiale (su righe ACC)
    "MERIT_ORDER_NO",         # posizione nell'ordine di merito
    "PARTIAL_QTY_ACCEPTED_IN",# S/N: accettazione parziale ammessa
    "BLOCK_ID",               # identificativo dell'offerta a blocchi (quasi sempre vuoto)
    "OFFER_TYPE",             # S = semplice, B = a blocchi
    "TYPE_CD",                # REG = regolare, STND = standard (frontiere estere)
    "BILATERAL_IN",           # true = contratto bilaterale registrato come offerta
    "UNIT_REFERENCE_NO",      # unita' di produzione/consumo
    "OPERATORE",              # ragione sociale dell'operatore
    "MARKET_CD",              # MGP
    "BID_OFFER_DATE_DT",      # data di competenza (YYYYMMDD)
]

#: Colonne da convertire in numerico (vedi `io_gme._to_float` per il perche' della
#: conversione difensiva sul separatore decimale).
COLONNE_NUMERICHE: list[str] = [
    "ENERGY_PRICE_NO",
    "QUANTITY_NO",
    "ADJ_QUANTITY_NO",
    "AWARDED_QUANTITY_NO",
    "AWARDED_PRICE_NO",
    "MERIT_ORDER_NO",
    "PERIOD",
]


def assicura_cartelle() -> None:
    """Crea (se mancanti) le cartelle di output e cache. Idempotente."""
    for d in (INTERIM_DIR, PROCESSED_DIR, FIGURE_DIR, TABLE_DIR):
        d.mkdir(parents=True, exist_ok=True)
