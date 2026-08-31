"""
Fase 1 dell'impianto a due fasi: prevedere a D-1 il prezzo orario del giorno D.

Che cosa fa questa fase, e che cosa NON e'
------------------------------------------
Non e' una gara di accuratezza. La domanda della tesi resta l'effetto dell'accumulo sul
prezzo; la previsione serve a rendere la batteria **non onnisciente**, cioe' a generare
l'incertezza di cui si vuole studiare la propagazione. Il modello dev'essere realistico e
soprattutto **avere una teoria dell'errore esplicita** — intervalli di previsione, residui
analizzabili — perche' e' l'errore, non la previsione, l'oggetto statistico.

Per questo si adotta un SARIMAX e non un metodo di apprendimento automatico: la struttura
dell'errore e' leggibile, non solo misurabile.

L'orizzonte, e perche' e' esattamente 24
----------------------------------------
Il MGP del giorno D chiude a mezzogiorno di D-1, ma gli esiti di D-1 sono stati pubblicati
verso le 13 di D-2: al momento della decisione l'operatore conosce **tutte** le 24 ore di
D-1. L'origine della previsione e' quindi la fine di D-1 e l'orizzonte h = 1...24. Nessuna
informazione dal futuro, e nessun bisogno di troncare la giornata a meta'.

La specifica
------------
SARIMAX(p, 1, q)(0, 1, 1)_24 con regressori esogeni deterministici.

La parte stagionale non e' una scelta ma una lettura del correlogramma. Sulla serie NORD di
ottobre 2023 - marzo 2024:

* con la sola differenza prima, l'ACF ai multipli di 24 vale +0,62 +0,57 +0,53 +0,53 +0,52 —
  **non decade affatto**, cioe' resta una stagionalita' non rimossa;
* aggiungendo la differenza stagionale, l'ACF ai multipli di 24 diventa
  -0,43 -0,01 -0,05 +0,00 -0,06: una **sola punta negativa a lag 24 che poi taglia netto**,
  con PACF -0,429. E' la firma di una media mobile stagionale di ordine 1.

Da qui D=1, P=0, Q=1, s=24. Restano da scegliere solo p e q, su un insieme piccolo e
dichiarato in anticipo (`ORDINI_CANDIDATI`), con l'AIC calcolato **una volta sola** sull'anno
di addestramento e l'ordine vincitore poi congelato: gli ordini sono un dato dichiarato della
tesi, non un iperparametro riottimizzato a ogni passo.

La stagionalita' **settimanale** non entra come seconda stagionalita' — SARIMA ne ammette
una sola, e differenziare a lag 168 costerebbe una settimana di burn-in — ma come pochi
regressori esogeni: termini di Fourier a periodo 168 piu' dummy per sabato, domenica e
festivi. La scelta e' sostenuta dai dati: tolto il profilo orario, il giorno della settimana
spiega solo il **5,2%** della varianza residua, con un'escursione di 15,8 EUR/MWh. Merita
qualche regressore, non una struttura stagionale.

Nessuna trasformazione logaritmica: sul 2023-2024 il minimo osservato e' 0,10 EUR/MWh e sul
MGP i prezzi negativi sono ammessi fino a -500, quindi il logaritmo e' fragile per
costruzione. Da rivedere solo se i residui mostrassero eteroschedasticita' marcata.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Ordini (p, q) messi a confronto. La parte stagionale (0,1,1)_24 e' fissata dal
#: correlogramma e non entra nel confronto.
ORDINI_CANDIDATI: tuple[tuple[int, int], ...] = ((0, 1), (1, 1), (2, 1), (1, 2))

#: Ordine stagionale, letto dall'ACF della serie doppiamente differenziata.
ORDINE_STAGIONALE: tuple[int, int, int, int] = (0, 1, 1, 24)

#: Ordine non stagionale ADOTTATO e congelato (D-39). Scelto per AIC sul 2023 fra i
#: candidati, con `scripts/13_seleziona_ordine.py`. Non va riottimizzato a ogni passo: e'
#: un dato dichiarato della tesi.
#:
#: Avvertenza sulla selezione: a `maxiter=50` questo ordine risultava il migliore per AIC
#: ma **non convergente**, e un AIC non convergente non e' confrontabile con uno
#: convergente. Rilanciato con `maxiter=200` converge in 55 iterazioni con AIC identico al
#: millesimo (63572,101 contro 63572,104): la stima era gia' all'ottimo, mancava solo la
#: conferma del criterio. Il margine sul secondo classificato, (1,1,2), resta comunque di
#: soli 3,37 punti su 63.572, con lo stesso numero di parametri: i due modelli sono
#: praticamente equivalenti e la scelta non e' delicata.
ORDINE_ADOTTATO: tuple[int, int, int] = (2, 1, 1)

#: Coppie di termini di Fourier per il ciclo settimanale (periodo 168 ore).
N_FOURIER_SETTIMANALE: int = 2

#: Ore in un giorno di mercato normale. I due giorni di cambio dell'ora ne hanno 23 e 25 e
#: vengono riportati a 24 da `serie_regolare`.
ORE_AL_GIORNO: int = 24


# --------------------------------------------------------------------------------------
# I due giorni di cambio dell'ora
# --------------------------------------------------------------------------------------
def serie_regolare(serie: pd.DataFrame, colonna: str = "prezzo") -> pd.DataFrame:
    """
    Riporta a 24 slot per giorno la serie, trattando i due cambi dell'ora legale.

    Parameters
    ----------
    serie : pd.DataFrame
        Colonne `data` (AAAAMMGG), `ora` (posizione del periodo, 0-based) e il prezzo.
    colonna : str
        Nome della colonna del prezzo.

    Returns
    -------
    pd.DataFrame
        Colonne `data`, `slot` (0-23), `prezzo`, `modificato` (True dove il valore e' stato
        costruito o fuso), ordinate nel tempo.

    La regola, e perche' questa
    ---------------------------
    * **giorno da 25 periodi** (fine dell'ora legale): l'ora locale 02:00-03:00 accade due
      volte. Le due occorrenze sono i periodi 3 e 4, e vengono **mediate** in un solo slot.
      Che siano davvero la stessa ora si vede dai dati: il 29/10/2023 valgono 110,00 e
      113,00, il 27/10/2024 95,35 e 97,64.
    * **giorno da 23 periodi** (inizio dell'ora legale): l'ora locale 02:00-03:00 non esiste.
      Si **interpola** uno slot fra i due vicini.

    Perche' 24 slot in ora locale e non un indice in UTC
    ----------------------------------------------------
    In UTC la serie sarebbe perfettamente regolare, ma il profilo giornaliero **si
    sfaserebbe di un'ora** attraverso il cambio, smussando proprio la stagionalita' che il
    modello deve cogliere. Il profilo dei prezzi e' guidato dal comportamento di domanda e
    offerta, che segue l'orologio locale: e' quello che va tenuto allineato.

    E' una **micro-assunzione**: riguarda due giorni su 365 e sposta quattro ore all'anno.
    Vale solo per la serie di previsione; la fase 2 continua a lavorare sui periodi d'asta
    reali, 23 o 25 che siano.
    """
    pezzi = []
    for data, fetta in serie.groupby("data", sort=True):
        valori = fetta.sort_values("ora")[colonna].to_numpy(dtype=float)
        modificato = np.zeros(len(valori), dtype=bool)

        if len(valori) == ORE_AL_GIORNO + 1:
            # Fine dell'ora legale: si fondono le due occorrenze della stessa ora.
            fuso = float(np.mean(valori[2:4]))
            valori = np.concatenate([valori[:2], [fuso], valori[4:]])
            modificato = np.zeros(ORE_AL_GIORNO, dtype=bool)
            modificato[2] = True
        elif len(valori) == ORE_AL_GIORNO - 1:
            # Inizio dell'ora legale: si ricostruisce l'ora che non e' esistita.
            interpolato = float(np.mean(valori[1:3]))
            valori = np.concatenate([valori[:2], [interpolato], valori[2:]])
            modificato = np.zeros(ORE_AL_GIORNO, dtype=bool)
            modificato[2] = True
        elif len(valori) != ORE_AL_GIORNO:
            raise ValueError(
                f"{data}: {len(valori)} periodi, attesi 23, 24 o 25. Un numero diverso non "
                "e' un cambio dell'ora e va capito, non normalizzato in silenzio."
            )

        pezzi.append(pd.DataFrame({"data": data, "slot": np.arange(ORE_AL_GIORNO),
                                   colonna: valori, "modificato": modificato}))

    fuori = pd.concat(pezzi, ignore_index=True)
    fuori["istante"] = (pd.to_datetime(fuori["data"], format="%Y%m%d")
                        + pd.to_timedelta(fuori["slot"], unit="h"))
    return fuori[["istante", "data", "slot", colonna, "modificato"]]


# --------------------------------------------------------------------------------------
# Regressori esogeni deterministici
# --------------------------------------------------------------------------------------
def pasqua(anno: int) -> pd.Timestamp:
    """Domenica di Pasqua secondo l'algoritmo gregoriano anonimo."""
    a, b, c = anno % 19, anno // 100, anno % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return pd.Timestamp(year=anno, month=mese, day=giorno)


def festivi(anni: list[int]) -> set[pd.Timestamp]:
    """
    Festivi civili italiani, che sul mercato elettrico si comportano come domeniche.

    Si includono anche il Lunedi' dell'Angelo (che non e' domenica) e le feste fisse. La
    domenica di Pasqua non serve elencarla, essendo gia' una domenica.
    """
    fissi = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8),
             (12, 25), (12, 26)]
    giorni: set[pd.Timestamp] = set()
    for anno in anni:
        giorni.update(pd.Timestamp(year=anno, month=m, day=g) for m, g in fissi)
        giorni.add(pasqua(anno) + pd.Timedelta(days=1))   # Lunedi' dell'Angelo
    return giorni


def regressori(istanti: pd.Series, n_fourier: int = N_FOURIER_SETTIMANALE) -> pd.DataFrame:
    """
    Regressori esogeni deterministici: ciclo settimanale e giorni non lavorativi.

    Parameters
    ----------
    istanti : pd.Series
        Istanti orari, gia' regolari (24 per giorno).
    n_fourier : int
        Coppie seno/coseno per il ciclo settimanale a 168 ore.

    Returns
    -------
    pd.DataFrame
        `2 * n_fourier + 3` colonne: le armoniche settimanali, e tre indicatrici per
        sabato, domenica e festivo.

    Perche' Fourier e non 167 dummy orarie settimanali
    --------------------------------------------------
    Il ciclo settimanale e' liscio e di ampiezza modesta — tolto il profilo giornaliero
    spiega il 5,2% della varianza residua — quindi due o tre armoniche lo descrivono con
    quattro-sei parametri leggibili invece che con centosessantasette. Le dummy restano solo
    dove il fenomeno **non** e' liscio, cioe' sul salto fra giorni lavorativi e non.
    """
    t = pd.to_datetime(pd.Series(istanti).reset_index(drop=True))
    ore_dal_lunedi = (t.dt.dayofweek * 24 + t.dt.hour).to_numpy(dtype=float)

    colonne: dict[str, np.ndarray] = {}
    for k in range(1, n_fourier + 1):
        angolo = 2 * np.pi * k * ore_dal_lunedi / 168.0
        colonne[f"sin{k}_168"] = np.sin(angolo)
        colonne[f"cos{k}_168"] = np.cos(angolo)

    giorni_festivi = festivi(sorted(t.dt.year.unique().tolist()))
    colonne["sabato"] = (t.dt.dayofweek == 5).to_numpy(dtype=float)
    colonne["domenica"] = (t.dt.dayofweek == 6).to_numpy(dtype=float)
    colonne["festivo"] = t.dt.normalize().isin(giorni_festivi).to_numpy(dtype=float)

    return pd.DataFrame(colonne, index=t.index)


# --------------------------------------------------------------------------------------
# Selezione dell'ordine
# --------------------------------------------------------------------------------------
@dataclass
class EsitoStima:
    """Esito della stima di un candidato: ordine, criteri d'informazione, diagnostica."""

    ordine: tuple[int, int, int]
    aic: float
    bic: float
    log_verosimiglianza: float
    n_parametri: int
    secondi: float
    convergenza: bool
    ljung_box_p: float
    sigma2: float


def stima(y: np.ndarray, esogene: pd.DataFrame | None, ordine: tuple[int, int, int],
          stagionale: tuple[int, int, int, int] = ORDINE_STAGIONALE,
          maxiter: int = 200, start_params=None):
    """
    Stima un SARIMAX. Restituisce l'oggetto risultati di statsmodels.

    `enforce_stationarity` e `enforce_invertibility` restano ai valori predefiniti: su una
    serie doppiamente differenziata i vincoli aiutano il solutore a non finire su radici
    esplosive, che darebbero previsioni divergenti a 24 passi.

    `maxiter` e' 200 e non il valore predefinito di statsmodels: con 50 iterazioni l'ordine
    adottato si fermava **appena prima** di soddisfare il criterio di convergenza (gliene
    servono 55). Una stima non convergente non e' un errore visibile — restituisce numeri
    plausibili — quindi il margine va tenuto largo, soprattutto nelle ristime mensili, dove
    nessuno guarderebbe il diagnostico.
    """
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    modello = SARIMAX(y, exog=esogene, order=ordine, seasonal_order=stagionale,
                      trend="n", enforce_stationarity=True, enforce_invertibility=True)
    return modello.fit(disp=False, maxiter=maxiter, start_params=start_params)


# --------------------------------------------------------------------------------------
# Previsione a origine mobile
# --------------------------------------------------------------------------------------
def previsioni_giornaliere(
    serie: pd.DataFrame,
    da: str,
    a: str,
    ordine: tuple[int, int, int] = ORDINE_ADOTTATO,
    stagionale: tuple[int, int, int, int] = ORDINE_STAGIONALE,
    alpha: float = 0.10,
    ristima_mensile: bool = True,
    finestra_giorni: int | None = None,
    avanzamento=None,
) -> pd.DataFrame:
    """
    Previsione a 24 passi per ogni giorno dell'intervallo, con origine alla fine di D-1.

    Parameters
    ----------
    serie : pd.DataFrame
        Serie gia' regolarizzata da `serie_regolare`: colonne `istante`, `data`, `slot`,
        `prezzo`.
    da, a : str
        Primo e ultimo giorno da prevedere, formato 'AAAAMMGG'. Tutto cio' che precede `da`
        e' storia di addestramento.
    ordine, stagionale : tuple
        Ordini del SARIMAX. Il default e' quello congelato (D-39).
    alpha : float
        Livello dell'intervallo di previsione: 0,10 da' un intervallo al 90%.
    ristima_mensile : bool
        Se True i coefficienti si ristimano all'inizio di ogni mese; fra una ristima e
        l'altra lo stato si aggiorna senza toccare i parametri.
    finestra_giorni : int | None
        Lunghezza della finestra di stima, in giorni. Con `None` la finestra e' **crescente**
        e ogni ristima usa tutta la storia disponibile; con un valore la stima usa solo gli
        ultimi `finestra_giorni` giorni. La finestra mobile mantiene il costo di ristima
        costante invece di farlo crescere con l'avanzare dell'anno, ed e' anche piu' vicina
        a cio' che fa un operatore, che non ripondera anni di storia.
    avanzamento : callable | None
        Ricevitore delle righe di avanzamento.

    Returns
    -------
    pd.DataFrame
        Una riga per ora prevista, con `previsione`, `errore_standard`, gli estremi
        dell'intervallo, il `prezzo` realmente osservato e l'`errore`.

    Perche' si ristima al mese e non ogni giorno
    -------------------------------------------
    Per due ragioni che convergono. La prima e' di costo: una stima completa richiede
    minuti, e farne 366 costerebbe giorni di calcolo per un guadagno previsivo trascurabile.
    La seconda e' di realismo: **nessun operatore ristima un modello ogni notte**. Fra una
    ristima e l'altra si usa `append(..., refit=False)`, che fa passare i dati nuovi
    attraverso il filtro di Kalman aggiornando lo **stato** senza toccare i **coefficienti**.
    E' esattamente la distinzione fra "il modello ha visto ieri" e "il modello e' stato
    ricalibrato", e sono due cose diverse.

    Perche' ogni ristima riparte da zero
    ------------------------------------
    Ripartire dai coefficienti del mese precedente farebbe risparmiare circa il 10% del tempo
    di ristima, e per un periodo la docstring lo dichiarava: il codice pero' non lo faceva, e
    quando la cosa e' stata corretta il comportamento e' stato **verificato invece che
    adottato**.

    La verifica ha mostrato che i due punti di partenza portano alla **stessa**
    verosimiglianza (scarto relativo 8e-8, quindi non due ottimi locali) ma a coefficienti
    ESOGENI diversi fino al 2,5%, mentre quelli ARMA restano identici alla quinta cifra. E'
    una cresta piatta: i termini di Fourier a 168 ore e le indicatrici di sabato e domenica
    descrivono lo stesso ciclo settimanale e si compensano a vicenda, quindi il blocco
    esogeno e' debolmente identificato.

    Non e' un errore, ma renderebbe i coefficienti dipendenti dall'ordine in cui i mesi sono
    stati stimati. Dieci per cento di tempo non vale questa dipendenza in un lavoro che
    dichiara la propria riproducibilita': ogni ristima riparte quindi da zero. `stima`
    accetta comunque `start_params`, che resta disponibile e testato.

    Nessuna informazione dal futuro
    -------------------------------
    Ogni previsione usa solo dati fino alla fine di D-1. I regressori esogeni del giorno D
    sono **deterministici** — calendario e armoniche — quindi conoscerli in anticipo non e'
    un'anticipazione: lo sono anche per l'operatore reale.
    """
    def segnala(testo: str) -> None:
        if avanzamento is not None:
            avanzamento(testo)

    serie = serie.sort_values("istante").reset_index(drop=True)
    esogene_tutte = regressori(serie["istante"])
    giorni = sorted(serie.loc[(serie["data"] >= da) & (serie["data"] <= a), "data"].unique())
    if not giorni:
        raise ValueError(f"nessun giorno fra {da} e {a} nella serie")

    inizio_valutazione = int(serie.index[serie["data"] == giorni[0]][0])
    if inizio_valutazione == 0:
        raise ValueError("serve almeno un giorno di storia prima del periodo da prevedere")

    y = serie["prezzo"].to_numpy(dtype=float)
    segnala(f"Storia iniziale: {inizio_valutazione:,} ore. "
            f"Giorni da prevedere: {len(giorni)}.")

    import time as _time

    def _da(posizione: int) -> int:
        """Primo indice della finestra di stima che termina in `posizione`."""
        if finestra_giorni is None:
            return 0
        return max(0, posizione - finestra_giorni * ORE_AL_GIORNO)

    t0 = _time.perf_counter()
    avvio = _da(inizio_valutazione)
    risultati = stima(y[avvio:inizio_valutazione],
                      esogene_tutte.iloc[avvio:inizio_valutazione], ordine, stagionale)
    segnala(f"Finestra di stima: "
            + (f"{finestra_giorni} giorni (mobile)" if finestra_giorni else "crescente")
            + f" — {inizio_valutazione - avvio:,} ore nella stima iniziale.")
    segnala(f"Stima iniziale in {_time.perf_counter() - t0:.0f} s "
            f"(convergenza {bool(risultati.mle_retvals.get('converged', False))}).")

    posizione = inizio_valutazione
    mese_corrente = giorni[0][:6]
    pezzi = []

    for i, giorno in enumerate(giorni, start=1):
        n = int((serie["data"] == giorno).sum())
        fetta = slice(posizione, posizione + n)
        esogene_giorno = esogene_tutte.iloc[fetta]

        ristimato = False
        if ristima_mensile and giorno[:6] != mese_corrente:
            mese_corrente = giorno[:6]
            t1 = _time.perf_counter()
            avvio = _da(posizione)
            # Ogni ristima riparte DA ZERO, deliberatamente: si veda la nota su
            # `start_params` nella docstring.
            risultati = stima(y[avvio:posizione], esogene_tutte.iloc[avvio:posizione],
                              ordine, stagionale)
            ristimato = True
            segnala(f"  ristima a {giorno}: {_time.perf_counter() - t1:.0f} s, "
                    f"convergenza {bool(risultati.mle_retvals.get('converged', False))}")

        previsione = risultati.get_forecast(steps=n, exog=esogene_giorno)
        estremi = np.asarray(previsione.conf_int(alpha=alpha))

        pezzi.append(pd.DataFrame({
            "data": giorno,
            "slot": serie["slot"].to_numpy()[fetta],
            "istante": serie["istante"].to_numpy()[fetta],
            "orizzonte": np.arange(1, n + 1),
            "previsione": np.asarray(previsione.predicted_mean, dtype=float),
            "errore_standard": np.asarray(previsione.se_mean, dtype=float),
            "ic_inf": estremi[:, 0],
            "ic_sup": estremi[:, 1],
            "prezzo": y[fetta],
            "ristimato": ristimato,
        }))

        # Lo stato assorbe il giorno appena osservato, i coefficienti restano quelli.
        risultati = risultati.append(y[fetta], exog=esogene_giorno, refit=False)
        posizione += n

        if i % 30 == 0 or i == len(giorni):
            segnala(f"  [{i:4d}/{len(giorni)}] {giorno}  "
                    f"({_time.perf_counter() - t0:.0f} s)")

    fuori = pd.concat(pezzi, ignore_index=True)
    fuori["errore"] = fuori["prezzo"] - fuori["previsione"]
    fuori["ampiezza_ic"] = fuori["ic_sup"] - fuori["ic_inf"]
    fuori["dentro_ic"] = (fuori["prezzo"] >= fuori["ic_inf"]) & (fuori["prezzo"] <= fuori["ic_sup"])
    return fuori
