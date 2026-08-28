"""
Esecuzione dell'erosione su un campione di giorni, in sequenza o su piu' processi.

Perche' questo modulo esiste
----------------------------
Il calcolo dell'erosione e' **imbarazzantemente parallelo**: ogni giorno di mercato ha le
proprie curve d'asta e non dipende dagli altri. Passando da un mese a un anno intero, e da
nove capacita' a centotrentadue, il costo sequenziale sale da minuti a ore, mentre la
struttura del problema non cambia affatto.

Il modulo **avvolge** il calcolo validato, non lo modifica: `erosioni_giorno` e' la stessa
funzione che stava dentro `scripts/06_soglia_price_maker.py`, spostata qui perche' la logica
riutilizzabile appartiene al package e perche' il runner parallelo deve poterla importare.
Il risultato di un giorno non dipende da chi lo calcola.

Dove NON c'e' parallelismo, ed e' un bene
-----------------------------------------
Il **bootstrap resta sequenziale**. Non e' una rinuncia: e' cio' che rende la
riproducibilita' un fatto strutturale invece di una promessa. Si veda la nota sul seme in
`erosioni_campione`.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd

from . import batteria as bt, config, curve, io_gme

#: Stagione di appartenenza del mese, per la stratificazione (D-28).
STAGIONI = {12: "inverno", 1: "inverno", 2: "inverno", 3: "primavera", 4: "primavera",
            5: "primavera", 6: "estate", 7: "estate", 8: "estate", 9: "autunno",
            10: "autunno", 11: "autunno"}

#: Variabili d'ambiente che limitano il multithreading delle librerie numeriche.
#: Vanno impostate nel processo padre **prima** di generare i figli: su Windows ogni figlio
#: e' un interprete nuovo che eredita l'ambiente e reimporta numpy, quindi le legge in tempo.
_VARIABILI_THREAD = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def erosioni_giorno(
    data: str,
    griglia: Sequence[float] | None = None,
    durata_ore: float = bt.DURATA_RIFERIMENTO_ORE,
) -> pd.DataFrame:
    """
    Calcola l'erosione di una giornata su tutta la griglia di capacita'.

    Parameters
    ----------
    data : str
        Giorno di mercato, formato 'AAAAMMGG'.
    griglia : Sequence[float] | None
        Capacita' aggregate in MW. Default: `batteria.GRIGLIA_CAPACITA_MW`.
    durata_ore : float
        Rapporto energia/potenza della flotta.

    Returns
    -------
    pd.DataFrame
        Una riga per capacita', con profitti, erosione e diagnostica del giorno.

    Le curve d'asta e i prezzi di riferimento si calcolano **una volta sola** e si riusano
    per ogni capacita': cambia solo il profilo che vi si inserisce. E' la ragione per cui
    infittire la griglia costa meno di quanto sembri — la parte fissa non si ripete.

    La funzione e' **pura rispetto alla data**: stesso giorno, stessa griglia, stesso esito,
    indipendentemente dal processo che la esegue. E' questa proprieta' che rende lecito
    distribuirla, e va preservata da qualunque modifica futura.
    """
    griglia = list(bt.GRIGLIA_CAPACITA_MW if griglia is None else griglia)

    granularita = config.granularita_prevalente(data)
    df = io_gme.carica_giorno(data=data, zona=None)
    zone_presenti = set(df["ZONE_CD"].dropna().unique())
    perimetro = ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti]

    offerte_giorno = curve.offerte_giornata(df, granularita, zone=perimetro, con_import=True)
    periodi = sorted(offerte_giorno)
    riferimento = np.array(
        [curve.prezzo_equilibrio(offerte_giorno[p]).prezzo for p in periodi], dtype=float
    )

    mese = int(data[4:6])
    righe = []
    for potenza in griglia:
        e = bt.erosione(df, potenza_aggregata_mw=potenza, granularita=granularita, data=data,
                        durata_ore=durata_ore, zone=perimetro,
                        prezzi_riferimento=riferimento, offerte_giorno=offerte_giorno)
        righe.append({
            "data": data,
            "granularita": granularita,
            "anno": data[:4],
            "mese": data[4:6],
            "stagione": STAGIONI[mese],
            "potenza_mw": potenza,
            "durata_ore": durata_ore,
            "profitto_price_taker": e.profitto_price_taker,
            "profitto_price_maker": e.profitto_price_maker,
            "erosione_assoluta": e.erosione_assoluta,
            "erosione_relativa": e.erosione_relativa,
            "variazione_prezzo_media": e.variazione_prezzo_media,
            "cicli_equivalenti": e.cicli_equivalenti,
            # D-31: giornate in cui il differenziale non copre il costo di degrado e il
            # piano ottimo e' non fare nulla. Restano nel campione con erosione nulla.
            "piano_vuoto": e.piano_vuoto,
            "prezzo_medio_riferimento": float(np.nanmean(riferimento)),
            "spread_giornaliero": float(np.nanmax(riferimento) - np.nanmin(riferimento)),
        })
    return pd.DataFrame(righe)


def _lavoro(argomenti: tuple[str, tuple[float, ...], float]) -> pd.DataFrame:
    """Adattatore per `executor.map`, che passa un solo argomento al lavoratore."""
    data, griglia, durata_ore = argomenti
    return erosioni_giorno(data, griglia=list(griglia), durata_ore=durata_ore)


def erosioni_campione(
    giorni: Iterable[str],
    griglia: Sequence[float] | None = None,
    durata_ore: float = bt.DURATA_RIFERIMENTO_ORE,
    processi: int | None = None,
    avanzamento: Callable[[str], None] | None = None,
    ogni: int = 10,
) -> pd.DataFrame:
    """
    Calcola l'erosione su un campione di giorni, distribuendo il lavoro sui processi.

    Parameters
    ----------
    giorni : Iterable[str]
        Giorni di mercato, formato 'AAAAMMGG'.
    griglia : Sequence[float] | None
        Capacita' aggregate in MW. Default: `batteria.GRIGLIA_CAPACITA_MW`.
    durata_ore : float
        Rapporto energia/potenza della flotta.
    processi : int | None
        Numero di processi. `None` o `1` esegue **in sequenza**, senza generare processi:
        e' il percorso di riferimento con cui si confronta il parallelo. `0` o negativo usa
        tutti i processori logici disponibili.
    avanzamento : Callable[[str], None] | None
        Ricevitore delle righe di avanzamento, per esempio `print`.
    ogni : int
        Ogni quanti giorni riportare l'avanzamento.

    Returns
    -------
    pd.DataFrame
        Le righe di tutti i giorni, **nell'ordine in cui i giorni sono stati passati**,
        indipendentemente dall'ordine in cui i processi li hanno completati.

    Il seme del bootstrap in esecuzione parallela
    ---------------------------------------------
    Domanda legittima e risposta breve: **il problema non si pone, per costruzione**.

    Il parallelismo sta interamente *a monte* del generatore casuale. Qui si calcola una
    tabella deterministica giorno x capacita'; il bootstrap (`batteria.bootstrap_soglia`)
    gira **dopo**, in un solo processo, su quella tabella, con il proprio parametro `seme`.
    Nessun lavoratore estrae numeri casuali, quindi non esiste alcuno stato di generatore da
    dividere fra processi ne' alcuna corsa critica sul seme.

    Restano due condizioni, ed entrambe sono garantite:

    1. **stessi valori**: `erosioni_giorno` e' pura rispetto alla data, quindi il risultato
       di un giorno non dipende dal processo che lo esegue (verificato dal test di non
       regressione, `tests/test_parallelo.py`);
    2. **stesso ordine**: `executor.map` restituisce i risultati nell'ordine degli argomenti
       e non in quello di completamento, quindi la tabella e' identica riga per riga.

    La seconda condizione, va detto, e' piu' forte del necessario:
    `bootstrap_soglia` costruisce una `pivot_table` indicizzata per `data` e ordinata per
    capacita', quindi l'ordine delle righe in ingresso non raggiunge il generatore in alcun
    modo. L'ordinamento deterministico serve percio' alla leggibilita' dei CSV e alla
    riproducibilita' *bit a bit* dei file prodotti, non alla correttezza del bootstrap. Che
    la riproducibilita' poggi su due garanzie indipendenti, e non su una sola, e' voluto.

    Il multithreading delle librerie numeriche
    ------------------------------------------
    Con N processi che eseguono ciascuno codice numerico gia' multithread si ottiene
    **sovrasottoscrizione**: piu' thread che core, e uno speedup che smette di crescere o
    peggiora. Prima di generare i processi si impone quindi un thread per libreria, e
    l'ambiente del padre viene ripristinato all'uscita.
    """
    giorni = list(giorni)
    griglia = tuple(bt.GRIGLIA_CAPACITA_MW if griglia is None else griglia)
    if not giorni:
        return pd.DataFrame()

    if processi is not None and processi <= 0:
        processi = os.cpu_count() or 1

    def segnala(testo: str) -> None:
        if avanzamento is not None:
            avanzamento(testo)

    inizio = time.perf_counter()
    argomenti = [(g, griglia, durata_ore) for g in giorni]
    pezzi: list[pd.DataFrame] = []

    if processi is None or processi == 1:
        segnala(f"Esecuzione in sequenza: {len(giorni)} giorni, "
                f"{len(griglia)} capacita' ciascuno.")
        for i, argomento in enumerate(argomenti, start=1):
            pezzi.append(_lavoro(argomento))
            if i % ogni == 0 or i == len(giorni):
                segnala(f"  [{i:4d}/{len(giorni)}] {giorni[i-1]}  "
                        f"({time.perf_counter() - inizio:.0f} s)")
    else:
        segnala(f"Esecuzione su {processi} processi: {len(giorni)} giorni, "
                f"{len(griglia)} capacita' ciascuno.")
        precedenti = {v: os.environ.get(v) for v in _VARIABILI_THREAD}
        for v in _VARIABILI_THREAD:
            os.environ[v] = "1"
        try:
            with ProcessPoolExecutor(max_workers=processi) as esecutore:
                # `map` conserva l'ordine degli argomenti: la tabella e' deterministica.
                for i, pezzo in enumerate(esecutore.map(_lavoro, argomenti, chunksize=1),
                                          start=1):
                    pezzi.append(pezzo)
                    if i % ogni == 0 or i == len(giorni):
                        segnala(f"  [{i:4d}/{len(giorni)}] {giorni[i-1]}  "
                                f"({time.perf_counter() - inizio:.0f} s)")
        finally:
            for v, valore in precedenti.items():
                if valore is None:
                    os.environ.pop(v, None)
                else:
                    os.environ[v] = valore

    durata = time.perf_counter() - inizio
    segnala(f"Completato in {durata:.0f} s "
            f"({durata / max(len(giorni), 1):.2f} s per giorno).")
    return pd.concat(pezzi, ignore_index=True)
