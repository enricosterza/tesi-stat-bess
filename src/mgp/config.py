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

# --------------------------------------------------------------------------------------
# Parametri tecnici dell'accumulo elettrochimico (decisione D-32)
# --------------------------------------------------------------------------------------
#: FONTE: Alonso-Perez, S. e Arcos-Vargas, A. (2026), "Storage deployment and its impact on
#: wholesale electricity prices", Energy Reports 15, 108991.
#:
#: Perche' presi da li' invece che scelti da noi: quello studio affronta la stessa domanda di
#: ricerca (effetto dell'aggiunta di capacita' di accumulo sui prezzi del mercato del giorno
#: prima) sul mercato spagnolo con dati OMIE 2024. I suoi parametri tecnici sono quindi
#: **citabili**, mentre i valori usati in precedenza qui (rendimenti 0,95 e costo variabile
#: assente) erano posti da noi senza fonte.
#:
#: ATTENZIONE - cosa NON e' trasferibile da quel lavoro:
#:   * le soglie di saturazione che gli autori trovano (~15 e ~32 GWh) valgono per la Spagna
#:     del 2024 e non sono trasferibili all'Italia: non vanno usate ne' come valore atteso
#:     ne' come griglia di capacita'. Per la zona NORD l'ordine di grandezza misurato e' di
#:     decine-centinaia di MW (D-30), cioe' due ordini di grandezza piu' basso;
#:   * i loro dati sono orari (24 periodi al giorno), i nostri anche a quarto d'ora (96):
#:     nessuna costante di questo progetto deve assumere 24 periodi;
#:   * mercato (OMIE/Spagna contro GME/Italia zona NORD) e impianto metodologico
#:     (deterministico puntuale contro stocastico distribuzionale, vedi D-24) restano diversi.
PARAMETRI_BESS: dict[str, float] = {
    #: Rendimento di ciclo completo (round-trip). I rendimenti di carica e di scarica si
    #: ottengono come sua radice quadrata, ipotizzando che la perdita si ripartisca in parti
    #: uguali fra le due direzioni: 0,9592 ciascuno.
    "rendimento_ciclo": 0.92,

    #: Costo variabile per MWh ciclato, in €/MWh: e' il costo opportunita' del degrado, cioe'
    #: la quota di vita utile consumata da un ciclo. Si applica **solo alla scarica**, in modo
    #: che un ciclo completo costi 12 €/MWh e non 24 (vedi D-32).
    "costo_variabile_eur_mwh": 12.0,

    #: Cicli equivalenti l'anno. NON e' un vincolo del programma lineare, che e' giornaliero:
    #: serve al calcolo economico annuale (capitolo 5) per il degrado. Corrobora pero' il
    #: vincolo di ciclo chiuso giornaliero, che ne implica 365: 350 e' il 96% di quel valore.
    "cicli_anno": 350.0,

    #: Rapporto fra capacita' energetica e potenza, in ore. Equivale alla condizione "potenza
    #: del convertitore pari al 25% della capacita' energetica": sono la stessa affermazione,
    #: perche' P = 0,25 * E se e solo se E / P = 4 ore. Gli autori mostrano che oltre il 25%
    #: il dimensionamento del convertitore smette di essere vincolante.
    "durata_ore": 4.0,

    #: Orizzonte di ottimizzazione, in giorni. Gli autori misurano che un orizzonte di 3
    #: giorni cattura oltre il 99% del profitto ottenibile con 5 giorni: il rendimento
    #: decrescente dell'orizzonte e' quindi rapido, e la giornata singola adottata qui (con
    #: ciclo chiuso, D-22) e' un troncamento accettabile. Resta un limite dichiarato.
    "orizzonte_giorni": 1.0,

    #: Il parametro K: rapporto fra il prezzo pagato sull'energia PRELEVATA dalla rete e
    #: quello incassato su quella IMMESSA (D-35). Entra soltanto nella valorizzazione
    #: economica, mai nel piano operativo: l'effetto dell'accumulo sul prezzo di equilibrio
    #: e' un fenomeno di mercato e non dipende da come l'investitore sia tassato.
    #:
    #: Due regimi:
    #:   K = 1    net-settled: prelievo e immissione allo stesso prezzo all'ingrosso. E' il
    #:            regime economicamente efficiente, ma in Italia NON esiste oggi per
    #:            l'arbitraggio puro: e' riservato ai servizi resi al gestore di rete e ai
    #:            servizi ausiliari. E' il default, cosi' che i risultati gia' calcolati
    #:            restino invariati.
    #:   K ~ 2,3  regime italiano attuale: sull'energia prelevata gravano oneri di rete,
    #:            oneri generali di sistema e fiscalita', che ne moltiplicano il costo
    #:            rispetto al prezzo all'ingrosso.
    "rapporto_prezzo_acquisto": 1.0,
}


#: Parametri economici per il conto dell'investitore (D-36), contesto italiano.
#:
#: FONTE: Lilla et al. (2026), Sustainability. Sono valori centrali di intervalli piu' ampi,
#: riportati qui insieme al loro range perche' l'analisi di sensitivita' del Capitolo 5 deve
#: poterli far variare.
#:
#: ATTENZIONE: questi parametri appartengono al LIVELLO 2 dell'analisi, il conto economico
#: dell'investitore. Non entrano mai nel calcolo dell'erosione o della soglia, che sono
#: grandezze di mercato (D-34).
PARAMETRI_ECONOMICI: dict[str, float] = {
    #: Investimento iniziale per MWh di capacita' energetica installata, in euro.
    "capex_eur_mwh": 110_000.0,
    "capex_min_eur_mwh": 80_000.0,
    "capex_max_eur_mwh": 150_000.0,

    #: Costi operativi annui per MWh installato, in euro.
    "opex_eur_mwh_anno": 2_000.0,
    "opex_min_eur_mwh_anno": 1_000.0,
    "opex_max_eur_mwh_anno": 10_000.0,

    #: Vita utile dell'impianto, in anni: e' l'orizzonte su cui si sconta.
    "vita_utile_anni": 15.0,

    #: Decadimento annuo dei ricavi, in frazione: tiene conto del degrado della capacita'
    #: e quindi della progressiva riduzione dell'energia ciclabile.
    "degrado_ricavi_annuo": 0.015,

    #: Tasso di sconto reale.
    "tasso_sconto": 0.03,
}


def rendimenti_da_ciclo(rendimento_ciclo: float | None = None) -> tuple[float, float]:
    """
    Ripartisce un rendimento di ciclo completo fra carica e scarica.

    Parameters
    ----------
    rendimento_ciclo : float, opzionale
        Rendimento round-trip. Se omesso si usa `PARAMETRI_BESS["rendimento_ciclo"]`.

    Returns
    -------
    (rendimento_carica, rendimento_scarica) : tuple[float, float]
        Entrambi pari alla radice quadrata del rendimento di ciclo.

    Assunzione
    ----------
    La perdita si ripartisce **in parti uguali** fra le due direzioni. E' una convenzione: la
    fonte da' il solo valore round-trip, che e' anche l'unica grandezza misurabile a morsetti.
    Il modello e' peraltro insensibile alla ripartizione quando il ciclo e' chiuso e i prezzi
    sono positivi, perche' entra solo il prodotto dei due rendimenti; la ripartizione conta
    soltanto con prezzi negativi, dove caricare e' remunerato.
    """
    if rendimento_ciclo is None:
        rendimento_ciclo = PARAMETRI_BESS["rendimento_ciclo"]
    radice = float(rendimento_ciclo) ** 0.5
    return radice, radice


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
