"""
Simulazione di un sistema di accumulo che fa arbitraggio sul MGP.

Che cosa fa questo modulo
-------------------------
Dato un profilo di prezzi e le caratteristiche fisiche di una batteria, calcola il profilo
ottimo di carica e scarica; e, dato l'insieme delle offerte di una giornata, ricalcola i
prezzi di equilibrio con la batteria inserita nel mercato.

La distinzione fra le due cose e' il punto centrale della tesi. Una batteria di taglia
trascurabile prende i prezzi come dati: compra dove costa poco, vende dove costa molto, e il
mercato non se ne accorge. Una batteria di taglia rilevante, invece, **sposta i prezzi che
sta sfruttando**: caricando aggiunge domanda e alza il prezzo di acquisto, scaricando
aggiunge offerta e abbassa quello di vendita. Il margine di arbitraggio si riduce quindi al
crescere della taglia, ed e' questo meccanismo che rende il dimensionamento un problema
economico e non solo tecnico.

Come e' modellata la partecipazione al mercato
----------------------------------------------
La batteria partecipa come **price taker**: presenta la carica come domanda al prezzo
massimo e la scarica come offerta al prezzo minimo. E' l'ipotesi naturale per un accumulo
che ha gia' deciso il proprio profilo e vuole eseguirlo: accetta qualunque prezzo pur di
ottenere il volume. Non e' l'unica possibile — un operatore strategico presenterebbe offerte
a prezzo limite — ed e' un'assunzione da dichiarare.

Il prezzo che ne risulta e' pero' **endogeno**: la batteria e' price taker nel modo in cui
offre, non nell'effetto che produce.
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
    """

    potenza_mw: float
    capacita_mwh: float
    rendimento_carica: float = 0.95
    rendimento_scarica: float = 0.95
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

    Returns
    -------
    (carica, scarica) : tuple[np.ndarray, np.ndarray]
        Potenze in MW per ciascun periodo.

    Il problema risolto
    -------------------
    Massimizza $\\sum_t p_t \\Delta (s_t - c_t)$ sotto i vincoli di potenza, di capacita' e
    di bilancio energetico
    $e_t = e_{t-1} + \\eta^{c} c_t \\Delta - s_t \\Delta / \\eta^{s}$.
    E' un programma lineare: la funzione obiettivo e i vincoli sono lineari nelle variabili
    $c_t$ e $s_t$, e i vincoli di capacita' si scrivono come somme cumulate.

    Il vincolo di non simultaneita' ($c_t s_t = 0$) **non** e' imposto, perche' renderebbe il
    problema non lineare. Con rendimenti minori di uno e prezzi positivi la soluzione ottima
    non carica e scarica mai nello stesso periodo — sarebbe una perdita secca — quindi il
    vincolo non e' vincolante. Puo' esserlo con prezzi negativi, situazione ammessa dal
    mercato: la funzione segnala il caso restituendo profili in cui entrambe le variabili
    sono positive, ed e' un controllo da fare a valle.

    Assunzione forte
    ----------------
    Il profilo e' calcolato conoscendo i prezzi di tutti i periodi della giornata, cioe' in
    condizioni di **previsione perfetta**. Il ricavo che ne risulta e' quindi un limite
    superiore, non un risultato conseguibile: serve come termine di confronto. Il
    trattamento dell'incertezza e' una questione aperta.
    """
    prezzi = np.asarray(prezzi, dtype=float)
    n = len(prezzi)
    delta = durata_periodo_ore

    # Variabili: [c_1..c_n, s_1..s_n]. linprog minimizza, quindi si cambia segno.
    costo = np.concatenate([prezzi * delta, -prezzi * delta])

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

    Interpretazione economica
    -------------------------
    Il punto fisso, quando esiste, e' l'equilibrio di un operatore che **non internalizza**
    il proprio effetto sul prezzo: ottimizza credendo di essere price taker e poi subisce lo
    spostamento che ha causato. E' il comportamento di una pluralita' di operatori in
    concorrenza fra loro.

    La selezione per ricavo realizzato, usata quando il punto fisso non esiste, corrisponde
    invece a un operatore che **internalizza** l'effetto, cioe' sceglie il profilo sapendo
    come muovera' i prezzi: e' piu' vicino al caso di un monopolista dell'accumulo. Le due
    letture non coincidono, e nel riportare i risultati va detto quale delle due si sta
    usando per ciascuna giornata.
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
