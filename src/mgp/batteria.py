"""
Accumulo che fa arbitraggio sul MGP: dal piano di carica e scarica alla soglia di capacita'
oltre la quale l'accumulo smette di essere price taker.

La domanda a cui serve questo modulo
------------------------------------
Non "quanto guadagna una batteria", ma **a partire da quale capacita' aggregata installata
l'accumulo diventa price maker**, cioe' sposta i prezzi che sta sfruttando al punto da
erodere il proprio margine. La transizione non e' un punto ma un fenomeno graduale e
aleatorio, perche' dipende dalla forma delle curve d'asta, che cambia ogni giorno: va quindi
caratterizzata come **soglia stocastica** (decisione D-24).

La metrica: erosione di profitto
--------------------------------
Per un giorno storico e una capacita' aggregata K si confrontano due profitti calcolati sullo
**stesso identico piano** di carica e scarica:

* `profitto_price_taker`: il piano valorizzato ai prezzi storici, cioe' come se l'accumulo
  non li muovesse. E' quello che si aspetta chi ottimizza su una serie di prezzi passati;
* `profitto_price_maker`: lo stesso piano inserito nelle curve d'asta reali, con l'equilibrio
  di ogni periodo ricalcolato e il piano valorizzato ai prezzi nuovi.

L'erosione e' la quota di profitto che l'accumulo distrugge da se':

    E(d, K) = (profitto_price_taker - profitto_price_maker) / profitto_price_taker

Poiche' il piano e' lo stesso nei due casi, la differenza misura **solo** l'effetto sul
prezzo, non un diverso comportamento.

Lo scenario simulato: tante batterie piccole non coordinate (D-25)
------------------------------------------------------------------
Il piano si ottimizza **una volta sola** sui prezzi storici, e l'equilibrio si ricalcola
**una volta sola**, solo per valorizzare. Non c'e' riottimizzazione strategica ne' ricerca di
un punto fisso fra profilo e prezzi.

La giustificazione e' economica: nessun singolo operatore, essendo piccolo, ha ragione di
anticipare il proprio effetto sul prezzo, quindi ciascuno ottimizza sul segnale che osserva.
Tutte le batterie osservano lo stesso segnale e i loro profili si sommano — e' coordinamento
**implicito via prezzo comune**, non collusione. E' questo che rende legittimo trattare la
capacita' aggregata K come un unico profilo.

Come partecipa al mercato
-------------------------
L'accumulo si presenta come **price taker nel modo di offrire**: la carica entra come domanda
al prezzo massimo, la scarica come offerta al prezzo minimo, cioe' accetta qualunque prezzo
pur di ottenere il volume programmato. Il prezzo che ne risulta e' pero' endogeno: price
taker nel modo di offrire non significa privo di effetto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from . import config, curve


# --------------------------------------------------------------------------------------
# Caratteristiche fisiche
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Batteria:
    """
    Caratteristiche fisiche di un sistema di accumulo.

    Attributes
    ----------
    potenza_mw : float
        Potenza nominale in MW, uguale in carica e in scarica.
    capacita_mwh : float
        Capacita' energetica utile in MWh.
    rendimento_carica : float
        Quota dell'energia prelevata dalla rete che finisce nell'accumulo.
    rendimento_scarica : float
        Quota dell'energia immagazzinata che viene immessa in rete.
    costo_variabile_eur_mwh : float
        Costo opportunita' del degrado, in €/MWh, applicato all'energia **scaricata**.
    energia_iniziale_mwh : float
        Stato di carica a inizio giornata.
    ciclo_chiuso : bool
        Se True, si impone che lo stato di carica finale sia uguale a quello iniziale. E'
        la condizione che rende le giornate confrontabili fra loro: senza di essa la
        batteria potrebbe svuotarsi il primo giorno e mostrare un ricavo non ripetibile.

    Note
    ----
    Il rapporto fra capacita' e potenza e' la **durata** dell'accumulo, in ore: una batteria
    da 100 MW e 400 MWh ha durata 4 ore, cioe' impiega quattro ore a scaricarsi a potenza
    piena. E' uno dei due parametri di dimensionamento che la tesi si propone di ottimizzare.

    I valori predefiniti di rendimento e costo variabile vengono da `config.PARAMETRI_BESS`,
    che ne documenta la fonte (D-32). Non sono scelte di comodo: cambiarli cambia il piano
    ottimo e quindi tutti i risultati a valle.
    """

    potenza_mw: float
    capacita_mwh: float
    rendimento_carica: float = field(
        default_factory=lambda: config.rendimenti_da_ciclo()[0])
    rendimento_scarica: float = field(
        default_factory=lambda: config.rendimenti_da_ciclo()[1])
    costo_variabile_eur_mwh: float = field(
        default_factory=lambda: config.PARAMETRI_BESS["costo_variabile_eur_mwh"])
    energia_iniziale_mwh: float = 0.0
    ciclo_chiuso: bool = True

    @property
    def durata_ore(self) -> float:
        """Ore necessarie a scaricare l'accumulo pieno alla potenza nominale."""
        return self.capacita_mwh / self.potenza_mw if self.potenza_mw else float("nan")

    @property
    def rendimento_ciclo(self) -> float:
        """Rendimento di ciclo completo: energia restituita su energia prelevata."""
        return self.rendimento_carica * self.rendimento_scarica

    @property
    def spread_minimo_eur_mwh(self) -> float:
        """
        Differenziale di prezzo sotto il quale un ciclo non e' conveniente.

        Perche' serve
        -------------
        Rende esplicita la soglia implicita nei parametri tecnici: comprare a `p_c` e
        rivendere a `p_s` conviene solo se `p_s * rendimento_ciclo - p_c > costo variabile`.
        A parita' di prezzo di carica p, il differenziale minimo e' quindi

            p * (1 - rendimento_ciclo) + costo_variabile / ... circa  cv + p * (1 - eta)

        Il valore restituito e' la componente indipendente dal livello dei prezzi, cioe' il
        solo costo variabile riportato all'energia prelevata. E' la ragione per cui, con i
        parametri adottati, nelle giornate a basso differenziale il piano ottimo e' **non
        fare nulla** (decisione D-31).
        """
        return self.costo_variabile_eur_mwh * self.rendimento_scarica


@dataclass
class EsitoSimulazione:
    """
    Esito della simulazione di una giornata.

    Attributes
    ----------
    profilo : pd.DataFrame
        Una riga per periodo, con carica, scarica, stato di carica, prezzo senza batteria e
        prezzo con batteria.
    ricavo : float
        Ricavo netto della giornata ai prezzi con batteria, in euro.
    ricavo_prezzi_dati : float
        Ricavo che si otterrebbe se i prezzi restassero quelli senza batteria: e' il ricavo
        illusorio di chi ignora l'effetto di retroazione.
    energia_ciclata_mwh : float
        Energia complessivamente immessa in rete nella giornata.
    cicli_equivalenti : float
        Energia ciclata divisa per la capacita': quante volte la batteria si e' svuotata.
    variazione_prezzo_media : float
        Media sui periodi della differenza fra prezzo con batteria e prezzo senza.
    iterazioni : int
        Iterazioni impiegate dal punto fisso fra profilo e prezzi.
    convergenza : bool
        True se il profilo si e' stabilizzato prima del limite di iterazioni.
    """

    profilo: pd.DataFrame
    ricavo: float
    ricavo_prezzi_dati: float
    energia_ciclata_mwh: float
    cicli_equivalenti: float
    variazione_prezzo_media: float
    iterazioni: int
    convergenza: bool
    dettagli: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Profilo ottimo a prezzi dati
# --------------------------------------------------------------------------------------
def profilo_ottimo(
    prezzi: np.ndarray | list[float],
    batteria: Batteria,
    durata_periodo_ore: float,
    periodi_per_ora: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Calcola il profilo di carica e scarica che massimizza il ricavo a prezzi dati.

    Parameters
    ----------
    prezzi : array
        Prezzo di ciascun periodo, in €/MWh.
    batteria : Batteria
        Caratteristiche dell'accumulo.
    durata_periodo_ore : float
        Durata di un periodo in ore (0,25 per il quarto d'ora, 1 per l'ora).
    periodi_per_ora : int
        Numero di periodi che compongono un'ora: 4 con PT15, 1 con PT60. Se maggiore di 1
        il piano e' vincolato a essere **costante dentro ciascuna ora** (D-33).

    Returns
    -------
    (carica, scarica) : tuple[np.ndarray, np.ndarray]
        Potenze in MW per ciascun periodo.

    Il problema risolto
    -------------------
    Massimizza $\\sum_t (p_t - k)\\, \\Delta s_t - \\sum_t p_t \\Delta c_t$ sotto i vincoli di
    potenza, di capacita' e di bilancio energetico
    $e_t = e_{t-1} + \\eta^{c} c_t \\Delta - s_t \\Delta / \\eta^{s}$.
    E' un programma lineare: la funzione obiettivo e i vincoli sono lineari nelle variabili
    $c_t$ e $s_t$, e i vincoli di capacita' si scrivono come somme cumulate.

    Il termine $k$ e' il **costo variabile** dell'accumulo (`costo_variabile_eur_mwh`), cioe'
    il costo opportunita' del degrado: ogni MWh ciclato consuma una quota di vita utile.
    Si applica alla sola **scarica**, cosi' che un ciclo completo costi $k$ una volta e non
    due (D-32).

    Conseguenza da tenere presente: con $k > 0$ l'arbitraggio richiede un differenziale
    minimo, e nelle giornate in cui i prezzi sono troppo piatti la soluzione ottima e'
    **non fare nulla** — carica e scarica identicamente nulle. Non e' un fallimento del
    solutore ma la risposta corretta, ed e' il caso trattato da D-31.

    Il vincolo di non simultaneita' ($c_t s_t = 0$) **non** e' imposto, perche' renderebbe il
    problema non lineare. Con rendimenti minori di uno e prezzi positivi la soluzione ottima
    non carica e scarica mai nello stesso periodo — sarebbe una perdita secca — quindi il
    vincolo non e' vincolante. Puo' esserlo con prezzi negativi, situazione ammessa dal
    mercato: la funzione segnala il caso restituendo profili in cui entrambe le variabili
    sono positive, ed e' un controllo da fare a valle.

    Il vincolo orario-nei-quarti (D-33)
    -----------------------------------
    Nel mercato del giorno prima il prodotto e' **orario**: un'offerta oraria vale la stessa
    potenza in tutti e quattro i quarti dell'ora (D-13), e nessun operatore puo' articolare la
    propria posizione dentro l'ora. Lasciare invece che la batteria cambi potenza ogni quindici
    minuti le darebbe una liberta' preclusa al resto del mercato: il profitto price taker ne
    risulterebbe gonfiato del 2-4% (fino al 20% nelle giornate a margine sottile) e la soglia
    $K^*$ apparirebbe piu' alta di quanto sia. E' un artefatto, non un effetto di mercato. Il
    vincolo e' formalizzato anche da Veenstra e Mulder (2025).

    Con `periodi_per_ora > 1` il problema si risolve quindi **sulle medie orarie dei prezzi**,
    con passo di un'ora, e il piano ottenuto viene replicato nei quattro quarti. Non servono
    vincoli di uguaglianza espliciti, perche':

    * a potenza costante nell'ora il ricavo dipende solo dalla **media** dei quattro prezzi,
      dato che $\\sum_q p_q P \\Delta = P \\bar{p} \\cdot 1\\,\\mathrm{h}$;
    * lo stato di carica e' lineare, quindi **monotono**, dentro l'ora: i suoi estremi cadono
      ai bordi, e vincolarlo a fine ora basta a vincolarlo ovunque.

    L'equivalenza con la formulazione esplicita — stesso LP a 96 periodi piu' 144 righe di
    uguaglianza — e' stata verificata su tre giornate: piani identici periodo per periodo e
    profitti coincidenti alla quarta cifra decimale. La via adottata usa 48 variabili invece
    di 192.

    Assunzione forte
    ----------------
    Il profilo e' calcolato conoscendo i prezzi di tutti i periodi della giornata, cioe' in
    condizioni di **previsione perfetta**. Il ricavo che ne risulta e' quindi un limite
    superiore, non un risultato conseguibile: serve come termine di confronto. Il
    trattamento dell'incertezza e' una questione aperta.
    """
    prezzi = np.asarray(prezzi, dtype=float)
    if periodi_per_ora > 1:
        if len(prezzi) % periodi_per_ora:
            raise ValueError(
                f"I {len(prezzi)} periodi non sono divisibili in ore da "
                f"{periodi_per_ora} periodi: il vincolo orario non e' applicabile."
            )
        n_ore = len(prezzi) // periodi_per_ora
        medie = prezzi.reshape(n_ore, periodi_per_ora).mean(axis=1)
        carica, scarica = profilo_ottimo(
            medie, batteria, durata_periodo_ore * periodi_per_ora, periodi_per_ora=1
        )
        return (np.repeat(carica, periodi_per_ora),
                np.repeat(scarica, periodi_per_ora))

    n = len(prezzi)
    delta = durata_periodo_ore

    # Variabili: [c_1..c_n, s_1..s_n]. linprog minimizza, quindi si cambia segno.
    # Il costo variabile penalizza la sola scarica: rende meno conveniente ogni MWh
    # immesso in rete, e con differenziali piccoli azzera del tutto il piano (D-31, D-32).
    cv = batteria.costo_variabile_eur_mwh
    costo = np.concatenate([prezzi * delta, -(prezzi - cv) * delta])

    # Somme cumulate dell'energia immagazzinata.
    triangolare = np.tril(np.ones((n, n)))
    guadagno = triangolare * batteria.rendimento_carica * delta
    perdita = -triangolare * delta / batteria.rendimento_scarica

    # e_t <= capacita'  e  -e_t <= energia iniziale (cioe' e_t >= 0)
    A_ub = np.vstack([
        np.hstack([guadagno, perdita]),
        np.hstack([-guadagno, -perdita]),
    ])
    b_ub = np.concatenate([
        np.full(n, batteria.capacita_mwh - batteria.energia_iniziale_mwh),
        np.full(n, batteria.energia_iniziale_mwh),
    ])

    A_eq = b_eq = None
    if batteria.ciclo_chiuso:
        A_eq = np.hstack([guadagno[-1:], perdita[-1:]])
        b_eq = np.zeros(1)

    limiti = [(0.0, batteria.potenza_mw)] * (2 * n)
    esito = linprog(costo, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                    bounds=limiti, method="highs")
    if not esito.success:
        return np.zeros(n), np.zeros(n)

    carica = np.round(esito.x[:n], 9)
    scarica = np.round(esito.x[n:], 9)
    return carica, scarica


def stato_di_carica(
    carica: np.ndarray, scarica: np.ndarray, batteria: Batteria, durata_periodo_ore: float
) -> np.ndarray:
    """Ricostruisce lo stato di carica periodo per periodo a partire dal profilo."""
    accumulo = (carica * batteria.rendimento_carica
                - scarica / batteria.rendimento_scarica) * durata_periodo_ore
    return batteria.energia_iniziale_mwh + np.cumsum(accumulo)


#: Durata di riferimento della flotta, in ore (fonte in `config.PARAMETRI_BESS`, D-32).
DURATA_RIFERIMENTO_ORE: float = config.PARAMETRI_BESS["durata_ore"]


def griglia_capacita() -> list[float]:
    """
    Griglia delle capacita' aggregate K su cui si misura l'erosione.

    Returns
    -------
    list[float]
        132 capacita' in MW, da 1 a 6000, con passo variabile.

    I quattro regimi di passo, e perche'
    ------------------------------------
    ==================  ==========  ======  =====================================================
    Intervallo (MW)     Passo (MW)  Punti   A che serve
    ==================  ==========  ======  =====================================================
    1 - 20                       1      20  la regione del **pavimento di discretezza** (D-30)
    30 - 400                    10      38  dove cadono le soglie al 5%, 10% e 20%
    425 - 1000                  25      24  la salita verso la saturazione
    1100 - 6000                100      50  il tratto oltre il 100% di erosione
    ==================  ==========  ======  =====================================================

    **Il minimo resta 1 MW e non va abbassato.** `sottrai_pavimento` usa la capacita' piu'
    piccola della griglia come riferimento di «effetto nullo»: cambiarla ridefinirebbe il
    pavimento e renderebbe i risultati non confrontabili con quelli gia' prodotti.

    Il **passo di 1 MW sotto i 20** non serve alla risoluzione ma a una verifica: se il
    pavimento e' davvero discretezza della ricostruzione e non effetto di mercato, la curva
    li' dev'essere piatta. Su gennaio 2025 lo e' (1 e 2 MW danno lo stesso quantile al 90%,
    2,76%). Con venti punti a passo unitario quella piattezza si osserva su ogni campione
    invece di essere assunta.

    Perche' il passo nella regione della soglia e' 10 MW e non 5
    ------------------------------------------------------------
    Perche' 10 MW e' gia' circa **cinque volte piu' fine dell'intervallo di confidenza** di
    K*, che su gennaio 2025 era ampio circa 96 MW (83-179). La griglia e' cosi' calibrata
    sulla risoluzione informativa reale: raffinarla sotto l'ampiezza dell'incertezza
    campionaria darebbe una precisione fittizia, che il rumore statistico non giustifica e
    che costerebbe il doppio del tempo di calcolo.

    L'estensione in alto arriva a 6000 MW perche' il 100% di erosione — cioe' il profitto
    price maker che diventa negativo — viene attraversato attorno ai 1600 MW sul 90°
    percentile ma solo attorno ai 2450 MW sulla mediana: per mostrare la saturazione su
    tutti i quantili, e non solo sul piu' estremo, bisogna spingersi ben oltre.
    """
    regimi = (np.arange(1, 21, 1),         # pavimento
              np.arange(30, 401, 10),      # soglie
              np.arange(425, 1001, 25),    # transizione
              np.arange(1100, 6001, 100))  # saturazione
    return [float(x) for x in np.concatenate(regimi)]


#: Griglia predefinita delle capacita' aggregate (MW). Vedi `griglia_capacita`.
GRIGLIA_CAPACITA_MW: list[float] = griglia_capacita()


def flotta(potenza_aggregata_mw: float,
           durata_ore: float = DURATA_RIFERIMENTO_ORE,
           **parametri) -> Batteria:
    """
    Costruisce la batteria equivalente a una flotta di accumuli non coordinati.

    Parameters
    ----------
    potenza_aggregata_mw : float
        Capacita' aggregata installata K, in MW di potenza.
    durata_ore : float
        Rapporto fra capacita' energetica e potenza, in ore. Quattro ore e' il taglio piu'
        diffuso negli impianti in costruzione.
    **parametri
        Altri campi di `Batteria` (rendimenti, ciclo chiuso, energia iniziale).

    Returns
    -------
    Batteria

    Perche' una flotta si puo' trattare come un'unica batteria
    ----------------------------------------------------------
    Nello scenario adottato (D-25) le batterie sono molte e piccole, nessuna di esse ha
    ragione di anticipare il proprio effetto sul prezzo, e tutte osservano **lo stesso
    segnale di prezzo**. Ottimizzando ciascuna sullo stesso vettore di prezzi e con gli
    stessi parametri tecnici, i profili risultanti sono proporzionali fra loro e la loro
    somma coincide con il profilo che si otterrebbe ottimizzando una sola batteria di taglia
    pari alla somma. E' coordinamento implicito via prezzo comune, non collusione, e vale
    finche' i vincoli sono lineari e uguali per tutte.

    L'equivalenza si rompe se le batterie hanno durate diverse o vincoli iniziali diversi:
    in quel caso la somma dei profili ottimi non e' il profilo ottimo della somma. E' una
    delle direzioni in cui il modello si puo' raffinare.
    """
    parametri.setdefault("ciclo_chiuso", True)
    return Batteria(potenza_mw=potenza_aggregata_mw,
                    capacita_mwh=potenza_aggregata_mw * durata_ore,
                    **parametri)


# --------------------------------------------------------------------------------------
# I due profitti e l'erosione (impianto D-24, D-25)
# --------------------------------------------------------------------------------------
def profitto_price_taker(
    carica: np.ndarray,
    scarica: np.ndarray,
    prezzi: np.ndarray | list[float],
    durata_periodo_ore: float,
    rapporto_prezzo_acquisto: float | None = None,
) -> float:
    """
    Valorizza un piano ai prezzi dati, come se l'accumulo non li muovesse.

    Parameters
    ----------
    carica, scarica : array
        Potenze in MW per ciascun periodo.
    prezzi : array
        Prezzi di riferimento, in €/MWh.
    durata_periodo_ore : float
        Durata di un periodo in ore.
    rapporto_prezzo_acquisto : float, opzionale
        Il parametro **K**: rapporto fra il prezzo pagato sull'energia prelevata e il prezzo
        incassato su quella immessa. Se omesso si usa
        `config.PARAMETRI_BESS["rapporto_prezzo_acquisto"]`, che vale 1 (net-settled).

    Returns
    -------
    float
        Margine lordo di mercato in euro:
        $\\sum_t p_t \\Delta s_t - K \\sum_t p_t \\Delta c_t$.

    Che cosa rappresenta
    --------------------
    E' il ricavo che un investitore si aspetta guardando una serie storica di prezzi e
    ottimizzandoci sopra: ignora completamente il fatto che l'accumulo, entrando in mercato,
    sposta quei prezzi. E' il termine di confronto rispetto a cui si misura l'erosione, e non
    e' un risultato conseguibile quando la capacita' installata e' rilevante.

    ATTENZIONE - e' un MARGINE LORDO DI MERCATO, non il profitto dell'investitore
    ---------------------------------------------------------------------------
    Il valore restituito e' il solo margine di compravendita sul mercato del giorno prima.
    **Non** vi sono dedotti: il costo di degrado, gli oneri di rete e la fiscalita'
    sull'energia prelevata, l'investimento iniziale, i costi operativi. Il conto economico
    dell'investitore si fa a valle, nel modulo `economia` e nel Capitolo 5 della tesi, dove
    tutti i costi si applicano in modo unificato (decisione D-34).

    La scelta risponde a un'architettura a due livelli. Il **livello 1** — l'effetto
    dell'accumulo sul prezzo di equilibrio, cioe' erosione e soglia — e' un fenomeno di
    mercato, che non dipende da come l'investitore sia tassato: mescolarvi i costi
    renderebbe la soglia funzione del regime fiscale, il che sarebbe economicamente
    sbagliato. Il **livello 2** e' il conto dell'investitore, e li' i costi entrano tutti.

    Il caso del degrado, che e' sottile
    -----------------------------------
    Il costo di degrado ha una **doppia natura**, ed e' l'unico parametro che sta a cavallo
    dei due livelli:

    * nel **piano** e' un segnale operativo: `profilo_ottimo` lo usa per decidere quando
      valga la pena ciclare, ed e' cio' che genera le giornate a piano vuoto (D-31);
    * nel **conto economico** e' un costo monetario, e va sottratto una volta sola, a valle.

    Non e' quindi un'incoerenza che il piano lo consideri e questa funzione no: e' la
    conseguenza voluta della separazione fra i due livelli. Sottrarlo anche qui lo
    conterebbe due volte nel Capitolo 5.

    Il prezzo di acquisto
    ---------------------
    Con `rapporto_prezzo_acquisto = 1` (default) l'energia prelevata e' valorizzata allo
    stesso prezzo di quella immessa: e' il regime **net-settled**, che in Italia non esiste
    oggi per l'arbitraggio puro. Si veda il parametro per il caso italiano (D-35).

    Perche' acquisto e vendita si valorizzano separatamente
    -------------------------------------------------------
    Con $K = 1$ basterebbe il flusso netto $s_t - c_t$ moltiplicato per il prezzo, ed e' come
    era scritto prima. Con $K \\ne 1$ i due lati non sono piu' compensabili, perche' il
    prelievo e' pagato a un prezzo diverso: vanno quindi tenuti distinti. Il risultato con
    $K = 1$ coincide al centesimo con la formulazione precedente.
    """
    if rapporto_prezzo_acquisto is None:
        rapporto_prezzo_acquisto = config.PARAMETRI_BESS["rapporto_prezzo_acquisto"]
    prezzi = np.asarray(prezzi, dtype=float)
    delta = durata_periodo_ore
    ricavo_vendita = np.nansum(prezzi * np.asarray(scarica, dtype=float) * delta)
    costo_acquisto = np.nansum(prezzi * np.asarray(carica, dtype=float) * delta)
    return float(ricavo_vendita - rapporto_prezzo_acquisto * costo_acquisto)


def profitto_price_maker(
    carica: np.ndarray,
    scarica: np.ndarray,
    offerte_giorno: dict[int, pd.DataFrame],
    periodi: list[int],
    durata_periodo_ore: float,
    rapporto_prezzo_acquisto: float | None = None,
) -> tuple[float, np.ndarray]:
    """
    Inserisce il piano nelle curve d'asta, ricalcola l'equilibrio e valorizza ai prezzi nuovi.

    Parameters
    ----------
    carica, scarica : array
        Potenze in MW per ciascun periodo, nello stesso ordine di `periodi`.
    offerte_giorno : dict[int, pd.DataFrame]
        Offerte di ciascuna asta, da `curve.offerte_giornata`.
    periodi : list[int]
        Periodi della giornata, nell'ordine.
    durata_periodo_ore : float
        Durata di un periodo in ore.

    Returns
    -------
    (profitto, prezzi) : tuple[float, np.ndarray]
        Profitto in euro ai prezzi ricalcolati, e il vettore di quei prezzi.

    Come entra la batteria nelle curve
    ----------------------------------
    Nei periodi di carica come **domanda addizionale al prezzo massimo**, in quelli di
    scarica come **offerta addizionale al prezzo minimo**: e' il modo di offrire di chi ha
    gia' deciso il proprio programma e accetta qualunque prezzo pur di eseguirlo.

    L'equilibrio si ricalcola **una volta sola** e serve soltanto a valorizzare (D-25). Non
    si riottimizza il piano sui prezzi nuovi: farlo significherebbe simulare un operatore che
    anticipa il proprio effetto, cioe' un altro scenario. La differenza fra questo profitto e
    quello price taker misura percio' esattamente l'effetto sul prezzo, a piano invariato.
    """
    prezzi = np.empty(len(periodi), dtype=float)
    for i, periodo in enumerate(periodi):
        offerte = offerte_giorno[int(periodo)]
        netto = float(scarica[i] - carica[i])
        if netto != 0.0:
            offerte = curve.aggiungi_import(offerte, netto)
        eq = curve.prezzo_equilibrio(offerte)
        prezzi[i] = np.nan if eq.prezzo is None else eq.prezzo
    profitto = profitto_price_taker(carica, scarica, prezzi, durata_periodo_ore,
                                    rapporto_prezzo_acquisto)
    return profitto, prezzi


@dataclass
class Erosione:
    """
    Esito del confronto fra profitto price taker e price maker per un giorno e una capacita'.

    Attributes
    ----------
    data : str
        Giorno di mercato.
    potenza_mw : float
        Capacita' aggregata K simulata, in MW.
    profitto_price_taker : float
        Profitto atteso ai prezzi di riferimento, in euro.
    profitto_price_maker : float
        Profitto ai prezzi ricalcolati con l'accumulo in mercato, in euro.
    erosione_assoluta : float
        Differenza fra i due, in euro. Resta interpretabile anche nei giorni a basso spread.
    erosione_relativa : float
        Quota di profitto eroso. Vale NaN quando il profitto price taker e' trascurabile,
        perche' il rapporto non sarebbe informativo (D-29).
    variazione_prezzo_media : float
        Media sui periodi della differenza fra prezzo con accumulo e prezzo di riferimento.
    energia_ciclata_mwh : float
    cicli_equivalenti : float
    profitto_atteso : float
        Il piano valorizzato ai prezzi su cui e' stato **ottimizzato**. Con
        `prezzi_piano=None` coincide per costruzione con `profitto_price_taker`; quando il
        piano nasce da una previsione e' invece il profitto che l'operatore si **aspettava**,
        e la sua distanza da `profitto_price_taker` misura il costo dell'errore previsivo.
    """

    data: str
    potenza_mw: float
    profitto_price_taker: float
    profitto_price_maker: float
    erosione_assoluta: float
    erosione_relativa: float
    variazione_prezzo_media: float
    energia_ciclata_mwh: float
    cicli_equivalenti: float
    profitto_atteso: float = float("nan")
    piano_vuoto: bool = False
    profilo: pd.DataFrame = field(default_factory=pd.DataFrame)


#: Sotto questo profitto price taker (euro) l'erosione relativa non viene calcolata: il
#: rapporto sarebbe dominato dal rumore. I giorni restano comunque nel campione, con la sola
#: erosione assoluta (D-29).
PROFITTO_MINIMO_PER_RAPPORTO: float = 1.0


def erosione(
    df: pd.DataFrame,
    potenza_aggregata_mw: float,
    granularita: str,
    data: str = "",
    durata_ore: float = DURATA_RIFERIMENTO_ORE,
    zone: list[str] | str | None = None,
    prezzi_riferimento: np.ndarray | None = None,
    prezzi_piano: np.ndarray | None = None,
    offerte_giorno: dict[int, pd.DataFrame] | None = None,
    con_import: bool = True,
    **parametri_batteria,
) -> Erosione:
    """
    Calcola l'erosione di profitto di una giornata per una data capacita' aggregata.

    Parameters
    ----------
    df : pd.DataFrame
        Offerte del giorno.
    potenza_aggregata_mw : float
        Capacita' aggregata K, in MW.
    granularita : str
        Granularita' delle aste.
    data : str
        Etichetta del giorno, riportata nell'esito.
    durata_ore : float
        Rapporto energia/potenza della flotta.
    zone : list[str] | str | None
        Perimetro zonale.
    prezzi_riferimento : array | None
        Prezzi con cui si **valorizza** il profitto price taker, e su cui si ottimizza il
        piano se `prezzi_piano` non e' indicato. Se None si usano i prezzi ricostruiti
        **senza** accumulo (vedi nota).
    prezzi_piano : array | None
        Prezzi su cui si **ottimizza** il piano, quando devono essere diversi da quelli con
        cui lo si valorizza. Se None il piano si ottimizza su `prezzi_riferimento`, che e'
        il caso di previsione perfetta e il comportamento storico della funzione.
    offerte_giorno : dict[int, pd.DataFrame] | None
        Curve gia' preparate da `curve.offerte_giornata`. Passarle evita di ricostruirle a
        ogni capacita' della griglia: sulle stesse curve cambia solo il profilo inserito.
    con_import : bool
        Se includere il blocco di scambio netto.
    **parametri_batteria
        Rendimenti, ciclo chiuso, energia iniziale.

    Returns
    -------
    Erosione

    Perche' i prezzi di riferimento sono quelli ricostruiti e non quelli ufficiali
    -----------------------------------------------------------------------------
    Sarebbe naturale usare i prezzi ufficiali come "prezzi storici". Cosi' facendo, pero',
    la differenza fra i due profitti conterrebbe **due** cose: l'effetto dell'accumulo sul
    prezzo, che e' l'oggetto dello studio, e l'errore della ricostruzione, che non lo e'.
    Usando per entrambi i profitti i prezzi ricostruiti senza accumulo, l'errore di
    ricostruzione entra in modo identico nei due termini e si semplifica nella differenza:
    l'erosione isola cosi' il solo effetto di prezzo.

    La ricostruzione e' comunque validata contro i prezzi ufficiali (si veda
    `curve.confronta_con_ufficiale` e lo script di validazione mensile), ed e' quella
    validazione a garantire che le curve su cui si simula siano quelle vere. Passando
    `prezzi_riferimento` si puo' rifare il calcolo sui prezzi ufficiali come controllo di
    sensibilita'.
    """
    if offerte_giorno is None:
        offerte_giorno = curve.offerte_giornata(df, granularita, zone=zone,
                                                con_import=con_import)
    periodi = sorted(offerte_giorno)
    delta = config.DURATA_ORE[granularita]

    if prezzi_riferimento is None:
        base = np.array(
            [curve.prezzo_equilibrio(offerte_giorno[p]).prezzo for p in periodi],
            dtype=float,
        )
    else:
        base = np.asarray(prezzi_riferimento, dtype=float)

    accumulo = flotta(potenza_aggregata_mw, durata_ore, **parametri_batteria)
    # Su quali prezzi si costruisce il piano. Con `prezzi_piano=None` sono gli stessi con
    # cui lo si valorizza: e' la previsione perfetta, il comportamento storico.
    base_piano = base if prezzi_piano is None else np.asarray(prezzi_piano, dtype=float)
    riferimento = np.nan_to_num(
        base_piano,
        nan=float(np.nanmean(base_piano)) if np.isfinite(base_piano).any() else 0.0)
    # Il vincolo orario-nei-quarti si deriva dalla granularita' dell'asta: 4 periodi per
    # ora su PT15, 1 su PT60, dove il vincolo e' vacuo e non cambia nulla (D-33).
    periodi_per_ora = int(round(1.0 / delta))
    carica, scarica = profilo_ottimo(riferimento, accumulo, delta,
                                     periodi_per_ora=periodi_per_ora)

    pi_pt = profitto_price_taker(carica, scarica, base, delta)
    pi_pm, prezzi_nuovi = profitto_price_maker(carica, scarica, offerte_giorno, periodi, delta)
    # Quello che l'operatore si aspettava di guadagnare: lo stesso piano valorizzato ai
    # prezzi su cui l'ha costruito. Con previsione perfetta coincide con pi_pt.
    pi_atteso = (pi_pt if prezzi_piano is None
                 else profitto_price_taker(carica, scarica, base_piano, delta))

    assoluta = pi_pt - pi_pm
    relativa = (assoluta / pi_pt) if abs(pi_pt) >= PROFITTO_MINIMO_PER_RAPPORTO else float("nan")

    # D-31 - giornate in cui il piano ottimo e' non fare nulla. Con un costo variabile
    # positivo il differenziale di prezzo puo' non coprire il degrado: il solutore
    # restituisce allora carica e scarica identicamente nulle. In quel caso non c'e'
    # profitto da erodere e la flotta non tocca il mercato, quindi l'erosione e' nulla per
    # definizione - non indefinita (0/0) e non mancante. La giornata resta nel campione,
    # coerentemente con D-29: escluderla introdurrebbe il bias verso i giorni ad alta
    # rinnovabile che D-29 vuole proprio evitare.
    piano_vuoto = not (np.any(carica > 0) or np.any(scarica > 0))
    if piano_vuoto:
        assoluta = 0.0
        relativa = 0.0

    energia_ciclata = float(np.sum(scarica) * delta)

    profilo = pd.DataFrame({
        "PERIOD": periodi,
        "prezzo_riferimento": base,
        "prezzo_piano": base_piano,
        "prezzo_con_accumulo": prezzi_nuovi,
        "carica_mw": carica,
        "scarica_mw": scarica,
        "energia_mwh": stato_di_carica(carica, scarica, accumulo, delta),
    })

    return Erosione(
        data=data,
        potenza_mw=potenza_aggregata_mw,
        profitto_price_taker=pi_pt,
        profitto_price_maker=pi_pm,
        erosione_assoluta=assoluta,
        erosione_relativa=relativa,
        variazione_prezzo_media=float(np.nanmean(prezzi_nuovi - base)),
        energia_ciclata_mwh=energia_ciclata,
        cicli_equivalenti=energia_ciclata / accumulo.capacita_mwh if accumulo.capacita_mwh else 0.0,
        profitto_atteso=pi_atteso,
        piano_vuoto=piano_vuoto,
        profilo=profilo,
    )


# --------------------------------------------------------------------------------------
# Simulazione con effetto di retroazione sul prezzo
# --------------------------------------------------------------------------------------
def simula_giorno(
    df: pd.DataFrame,
    batteria: Batteria,
    granularita: str,
    zone: list[str] | str | None = None,
    stati: list[str] | None = None,
    includi_altra_granularita: bool = True,
    con_import: bool = True,
    max_iterazioni: int = 10,
) -> EsitoSimulazione:
    """
    Simula una giornata di mercato con la batteria inserita, ricalcolando i prezzi.

    Parameters
    ----------
    df : pd.DataFrame
        Offerte del giorno.
    batteria : Batteria
        Caratteristiche dell'accumulo.
    granularita : str
        Granularita' delle aste da ricostruire.
    zone, stati, includi_altra_granularita, con_import
        Perimetro e trattamento delle offerte, come in `curve.clearing_giorno`.
    max_iterazioni : int
        Limite di iterazioni del punto fisso fra profilo e prezzi.

    Returns
    -------
    EsitoSimulazione

    Il punto fisso fra profilo e prezzi
    -----------------------------------
    Profilo e prezzi si determinano a vicenda: il profilo ottimo dipende dai prezzi, e i
    prezzi dipendono dal profilo. Si procede iterando:

    1. si calcolano i prezzi **senza** batteria;
    2. si ottimizza il profilo su quei prezzi;
    3. si reinseriscono carica e scarica nelle curve e si ricalcolano i prezzi;
    4. si ri-ottimizza il profilo sui nuovi prezzi, e si ripete.

    Il procedimento si ferma quando il profilo non cambia piu'. **Non c'e' garanzia di
    convergenza**, e la ragione e' sostanziale, non numerica: la batteria carica dove il
    prezzo e' basso, ma caricando lo alza, e sul prezzo alzato non converrebbe piu'
    caricare. Su un mercato in cui la batteria pesa molto la successione oscilla fra due
    configurazioni e il punto fisso non esiste.

    Quando questo accade non si restituisce l'ultimo profilo raggiunto, che dipenderebbe
    solo da dove si e' interrotta l'iterazione: fra i profili incontrati si sceglie quello
    con il **ricavo effettivamente realizzato** piu' alto, cioe' valutato ai prezzi che quel
    profilo stesso genera. Il campo `convergenza` distingue i due casi e va riportato.

    Non e' lo scenario adottato
    ---------------------------
    Questa funzione simula un **operatore unico che riottimizza** finche' profilo e prezzi
    non sono coerenti fra loro. E' l'alternativa scartata con D-25: descrive un monopolista
    dell'accumulo, mentre la domanda di ricerca riguarda l'ingresso di capacita' distribuita
    fra molti operatori in concorrenza, che non riottimizzano affatto.

    Resta nel modulo come **variante di confronto**: il divario fra questo scenario e quello
    non coordinato misura quanto vale, per l'accumulo, internalizzare il proprio effetto sul
    prezzo. Per l'impianto principale si usano invece `erosione` e le funzioni collegate.

    Interpretazione economica
    -------------------------
    Il punto fisso, quando esiste, e' l'equilibrio di un operatore che ottimizza credendo di
    essere price taker e poi subisce lo spostamento che ha causato. La selezione per ricavo
    realizzato, usata quando il punto fisso non esiste, corrisponde invece a un operatore che
    **internalizza** l'effetto, cioe' sceglie il profilo sapendo come muovera' i prezzi. Le
    due letture non coincidono, e nel riportare i risultati va detto quale vale per ciascuna
    giornata.
    """
    periodi = sorted(
        df.loc[df["GRANULARITY"] == granularita, "PERIOD"].dropna().unique().tolist()
    )
    delta = config.DURATA_ORE[granularita]

    # Offerte di ciascun periodo, con il blocco di scambio gia' incluso: si calcolano una
    # volta sola, perche' non dipendono dal profilo della batteria.
    offerte_base: dict[int, pd.DataFrame] = {}
    for periodo in periodi:
        periodo = int(periodo)
        off = curve.offerte_periodo(df, periodo, granularita, zone=zone, stati=stati,
                                    includi_altra_granularita=includi_altra_granularita)
        if con_import:
            off = curve.aggiungi_import(
                off, curve.import_netto(df, periodo, granularita, zone=zone)
            )
        offerte_base[periodo] = off

    def prezzi_con(carica: np.ndarray, scarica: np.ndarray) -> np.ndarray:
        prezzi = []
        for i, periodo in enumerate(periodi):
            offerte = offerte_base[int(periodo)]
            # Carica = domanda addizionale (segno negativo), scarica = offerta addizionale.
            netto = float(scarica[i] - carica[i])
            if netto != 0.0:
                offerte = curve.aggiungi_import(offerte, netto)
            eq = curve.prezzo_equilibrio(offerte)
            prezzi.append(np.nan if eq.prezzo is None else eq.prezzo)
        return np.asarray(prezzi, dtype=float)

    n = len(periodi)
    zero = np.zeros(n)
    prezzi_base = prezzi_con(zero, zero)
    riferimento = float(np.nanmean(prezzi_base)) if np.isfinite(prezzi_base).any() else 0.0

    visitati: list[dict] = []
    chiavi: set = set()
    precedente: tuple | None = None
    prezzi_correnti = prezzi_base
    convergenza = False
    iterazione = 0

    for iterazione in range(1, max_iterazioni + 1):
        utilizzabili = np.nan_to_num(prezzi_correnti, nan=riferimento)
        carica, scarica = profilo_ottimo(utilizzabili, batteria, delta)
        chiave = (tuple(np.round(carica, 6)), tuple(np.round(scarica, 6)))

        if precedente is not None and chiave == precedente:
            # Ottimizzando sui prezzi che il profilo stesso genera si ritrova lo stesso
            # profilo: e' il punto fisso cercato.
            convergenza = True
            break
        if chiave in chiavi:
            break                     # ciclo piu' lungo di uno: oscillazione

        prezzi_indotti = prezzi_con(carica, scarica)
        netto_iter = (scarica - carica) * delta
        visitati.append({
            "carica": carica,
            "scarica": scarica,
            "prezzi": prezzi_indotti,
            "ricavo": float(np.nansum(prezzi_indotti * netto_iter)),
        })
        chiavi.add(chiave)
        precedente = chiave
        prezzi_correnti = prezzi_indotti

    if not visitati:
        visitati.append({"carica": zero, "scarica": zero,
                         "prezzi": prezzi_base, "ricavo": 0.0})

    # Se il punto fisso esiste e' l'ultimo profilo visitato; se invece la successione
    # oscilla, fra i profili incontrati si sceglie quello che massimizza il ricavo
    # effettivamente realizzato, cioe' valutato ai prezzi che il profilo stesso genera.
    # Restituire l'ultimo profilo raggiunto sarebbe arbitrario: dipenderebbe soltanto da
    # dove si e' interrotta l'iterazione.
    scelto = visitati[-1] if convergenza else max(visitati, key=lambda v: v["ricavo"])
    carica, scarica = scelto["carica"], scelto["scarica"]
    prezzi_correnti = scelto["prezzi"]

    energia = stato_di_carica(carica, scarica, batteria, delta)
    netto = (scarica - carica) * delta
    ricavo = float(np.nansum(prezzi_correnti * netto))
    ricavo_illusorio = float(np.nansum(prezzi_base * netto))
    energia_ciclata = float(np.sum(scarica) * delta)

    profilo = pd.DataFrame({
        "PERIOD": periodi,
        "prezzo_senza_batteria": prezzi_base,
        "prezzo_con_batteria": prezzi_correnti,
        "carica_mw": carica,
        "scarica_mw": scarica,
        "energia_mwh": energia,
    })
    profilo["variazione_prezzo"] = (
        profilo["prezzo_con_batteria"] - profilo["prezzo_senza_batteria"]
    )

    return EsitoSimulazione(
        profilo=profilo,
        ricavo=ricavo,
        ricavo_prezzi_dati=ricavo_illusorio,
        energia_ciclata_mwh=energia_ciclata,
        cicli_equivalenti=energia_ciclata / batteria.capacita_mwh if batteria.capacita_mwh else 0.0,
        variazione_prezzo_media=float(np.nanmean(profilo["variazione_prezzo"])),
        iterazioni=iterazione,
        convergenza=convergenza,
        dettagli={
            "periodi": n,
            "simultaneita": int(np.sum((carica > 1e-6) & (scarica > 1e-6))),
        },
    )


# --------------------------------------------------------------------------------------
# La soglia stocastica: bootstrap sui giorni (D-26, D-27, D-28)
# --------------------------------------------------------------------------------------
def _attraversamento(griglia: np.ndarray, valori: np.ndarray, soglia: float) -> float:
    """
    Trova per interpolazione lineare il punto in cui una curva crescente supera una soglia.

    Restituisce NaN se la curva non attraversa la soglia entro la griglia: e' un esito
    informativo — significa che entro le capacita' simulate l'erosione non raggiunge mai il
    livello dichiarato — e va contato, non silenziato.
    """
    sopra = np.flatnonzero(valori >= soglia)
    if sopra.size == 0:
        return float("nan")
    i = int(sopra[0])
    if i == 0:
        return float(griglia[0])
    x0, x1 = float(griglia[i - 1]), float(griglia[i])
    y0, y1 = float(valori[i - 1]), float(valori[i])
    if not np.isfinite(y0) or y1 == y0:
        return x1
    return x0 + (soglia - y0) * (x1 - x0) / (y1 - y0)


def sottrai_pavimento(
    erosioni: pd.DataFrame,
    capacita_minima: float | None = None,
    colonna_erosione: str = "erosione_relativa",
    nome_colonna: str = "erosione_netta",
) -> pd.DataFrame:
    """
    Toglie dall'erosione il "pavimento" dovuto alla discretezza della ricostruzione.

    Parameters
    ----------
    erosioni : pd.DataFrame
        Tabella giorno x capacita' con l'erosione.
    capacita_minima : float | None
        Capacita' che rappresenta l'assenza di effetto. Default: la piu' piccola presente
        nella griglia, che va scelta abbastanza piccola da non poter muovere il mercato.
    colonna_erosione, nome_colonna : str
        Colonna di partenza e nome della colonna aggiunta.

    Returns
    -------
    pd.DataFrame
        La tabella con in piu' la colonna dell'erosione netta, troncata a zero.

    Il problema che risolve
    -----------------------
    A capacita' minuscole l'erosione misurata non e' nulla, ma non e' nemmeno un effetto di
    mercato: e' l'effetto della **discretezza delle curve ricostruite**. In alcuni periodi
    l'equilibrio cade esattamente sul bordo di un gradino, e bastano pochi megawatt a farlo
    saltare al gradino successivo, con un salto di prezzo di alcuni euro. Misurato sui dati:
    a 1 MW di capacita' aggregata il prezzo si muove in media in 1,5 periodi su una decina,
    ma quando si muove salta di 1,8-2,7 €/MWh; e l'erosione a 1 MW e a 5 MW e' praticamente
    identica, mentre un effetto reale dovrebbe crescere con la capacita'.

    Nel mercato vero questo non accade allo stesso modo, perche' l'offerta marginale viene
    accettata parzialmente e l'incrocio cade all'interno del gradino: il pavimento e' quindi
    un artefatto della ricostruzione a gradini, non un fenomeno da misurare.

    Il pavimento vale circa l'1% in mediana e il 3,6% al novantesimo percentile: e' quindi
    trascurabile rispetto a una soglia del 20%, rilevante rispetto a una del 10%, e
    **comparabile alla soglia stessa** se la si fissasse al 5%, che percio' non e'
    utilizzabile.
    """
    if capacita_minima is None:
        capacita_minima = float(erosioni["potenza_mw"].min())
    pavimento = (erosioni[erosioni["potenza_mw"] == capacita_minima]
                 .set_index("data")[colonna_erosione])
    risultato = erosioni.copy()
    risultato[nome_colonna] = (
        risultato[colonna_erosione] - risultato["data"].map(pavimento)
    ).clip(lower=0.0)
    return risultato


def bootstrap_soglia(
    erosioni: pd.DataFrame,
    soglia: float = 0.10,
    quantile: float = 0.90,
    n_boot: int = 1000,
    colonna_erosione: str = "erosione_relativa",
    strato: str | None = None,
    seme: int | None = 12345,
) -> pd.DataFrame:
    """
    Stima la soglia di capacita' K* e la sua incertezza, ricampionando i giorni storici.

    Parameters
    ----------
    erosioni : pd.DataFrame
        Una riga per coppia (giorno, capacita'), con almeno le colonne `data`, `potenza_mw`
        e quella indicata da `colonna_erosione`. E' l'output dello script che calcola
        `erosione` sulla griglia.
    soglia : float
        Livello di erosione che definisce il passaggio a price maker, per esempio 0,10 per
        il 10% di profitto eroso. E' una scelta dichiarata, non stimata dai dati.
    quantile : float
        Quantile prudenziale della distribuzione dell'erosione fra i giorni (D-27). Si usa
        0,80 o 0,90: piu' in coda la stima diventa instabile perche' poggia su pochi giorni.
    n_boot : int
        Numero di ricampionamenti.
    colonna_erosione : str
        `erosione_relativa` oppure `erosione_assoluta` (D-29).
    strato : str | None
        Nome di una colonna su cui stratificare, per esempio la stagione o l'anno (D-28).
        Se indicata, la stima viene ripetuta separatamente per ciascun livello.
    seme : int | None
        Seme del generatore, per rendere il risultato riproducibile.

    Returns
    -------
    pd.DataFrame
        Una riga per strato, con `K_stella` (stima sul campione osservato), `K_inf` e `K_sup`
        (estremi dell'intervallo di confidenza al 90%), `quota_senza_attraversamento` (quota
        di ricampionamenti in cui l'erosione non raggiunge mai la soglia entro la griglia),
        `n_giorni` e `n_capacita`.

    Come funziona
    -------------
    Si ricampionano **i giorni** con reimmissione, non le singole osservazioni: un giorno
    entra o esce con tutta la sua curva di erosione sulle capacita'. E' la struttura corretta,
    perche' l'unita' statistica e' la giornata di mercato — le erosioni a capacita' diverse
    dello stesso giorno sono fortemente dipendenti fra loro, essendo calcolate sulle stesse
    curve d'asta.

    Per ogni ricampionamento si calcola, a ciascuna capacita' della griglia, il quantile
    dell'erosione fra i giorni estratti; si ottiene cosi' una curva quantile-contro-capacita',
    crescente perche' piu' accumulo erode di piu'; e si individua per interpolazione la
    capacita' a cui quella curva attraversa la soglia dichiarata. La distribuzione delle K*
    cosi' ottenute fornisce l'intervallo di confidenza.

    Perche' il quantile e non la media
    ----------------------------------
    La media descrive il giorno tipico, ma chi investe sopporta il rischio del giorno
    sfavorevole: la soglia rilevante e' quella oltre cui l'erosione diventa grave in una quota
    non trascurabile di giornate. Il quantile risponde a quella domanda, la media no.
    """
    richieste = {"data", "potenza_mw", colonna_erosione}
    mancanti = richieste - set(erosioni.columns)
    if mancanti:
        raise ValueError(f"colonne mancanti in `erosioni`: {sorted(mancanti)}")

    gruppi = [(None, erosioni)] if strato is None else list(erosioni.groupby(strato))
    generatore = np.random.default_rng(seme)
    righe = []

    for etichetta, fetta in gruppi:
        tabella = fetta.pivot_table(index="data", columns="potenza_mw",
                                    values=colonna_erosione, aggfunc="mean")
        tabella = tabella.sort_index(axis=1)
        griglia = tabella.columns.to_numpy(dtype=float)
        valori = tabella.to_numpy(dtype=float)      # giorni x capacita'
        n_giorni = valori.shape[0]
        if n_giorni == 0 or griglia.size == 0:
            continue

        osservata = np.nanquantile(valori, quantile, axis=0)
        k_osservata = _attraversamento(griglia, osservata, soglia)

        stime = np.empty(n_boot, dtype=float)
        for b in range(n_boot):
            estratti = generatore.integers(0, n_giorni, size=n_giorni)
            campione = valori[estratti]
            with np.errstate(invalid="ignore"):
                curva = np.nanquantile(campione, quantile, axis=0)
            stime[b] = _attraversamento(griglia, curva, soglia)

        valide = stime[np.isfinite(stime)]
        righe.append({
            "strato": etichetta if etichetta is not None else "tutti i giorni",
            "K_stella": k_osservata,
            "K_inf": float(np.percentile(valide, 5)) if valide.size else float("nan"),
            "K_sup": float(np.percentile(valide, 95)) if valide.size else float("nan"),
            "quota_senza_attraversamento": float(1 - valide.size / n_boot),
            "n_giorni": int(n_giorni),
            "n_capacita": int(griglia.size),
            "quantile": quantile,
            "soglia": soglia,
        })

    return pd.DataFrame(righe)


def curva_erosione(
    erosioni: pd.DataFrame,
    quantili: tuple[float, ...] = (0.5, 0.8, 0.9),
    colonna_erosione: str = "erosione_relativa",
    strato: str | None = None,
) -> pd.DataFrame:
    """
    Riassume l'erosione osservata in funzione della capacita' installata.

    Returns
    -------
    pd.DataFrame
        Per ciascuna capacita' (ed eventuale strato): mediana e quantili richiesti
        dell'erosione fra i giorni, piu' il numero di giorni su cui sono calcolati.

    A che serve
    -----------
    E' la curva che si porta in tesi accanto alla soglia: mostra **come** l'erosione cresce
    con la capacita', non solo dove attraversa un livello convenzionale. La distanza fra il
    quantile mediano e quello prudenziale dice quanto la transizione dipende dalla giornata.
    """
    chiavi = ["potenza_mw"] if strato is None else [strato, "potenza_mw"]
    aggregazioni = {f"q{int(q * 100)}": (colonna_erosione, lambda s, q=q: s.quantile(q))
                    for q in quantili}
    aggregazioni["media"] = (colonna_erosione, "mean")
    aggregazioni["n_giorni"] = (colonna_erosione, "count")
    return erosioni.groupby(chiavi).agg(**aggregazioni).reset_index()
