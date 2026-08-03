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

#: Granularita' presenti nei dati. `PERIOD` va SEMPRE letto insieme a `GRANULARITY`:
#: con PT15 vale 1-96, con PT30 1-48, con PT60 1-24. Filtrare su `PERIOD` senza filtrare
#: la granularita' mescolerebbe quarti d'ora e ore.
GRANULARITA_PERIODI: dict[str, int] = {"PT15": 96, "PT30": 48, "PT60": 24}
GRANULARITA_DEFAULT: str = "PT15"

#: Durata in ore di un periodo, per convertire quantita' (MWh) in potenza (MW) e viceversa.
DURATA_ORE: dict[str, float] = {"PT15": 0.25, "PT30": 0.5, "PT60": 1.0}

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
    "QUANTITY_NO",            # quantita' offerta, MWh
    "AWARDED_QUANTITY_NO",    # quantita' assegnata dall'algoritmo di mercato, MWh
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
    "AWARDED_QUANTITY_NO",
    "AWARDED_PRICE_NO",
    "MERIT_ORDER_NO",
    "PERIOD",
]


def assicura_cartelle() -> None:
    """Crea (se mancanti) le cartelle di output e cache. Idempotente."""
    for d in (INTERIM_DIR, PROCESSED_DIR, FIGURE_DIR, TABLE_DIR):
        d.mkdir(parents=True, exist_ok=True)
