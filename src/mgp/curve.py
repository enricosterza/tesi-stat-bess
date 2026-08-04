"""
Curve aggregate di domanda e offerta e prezzo di equilibrio del MGP.

Che cosa fa questo modulo
-------------------------
Dato l'insieme delle offerte di **una zona e un periodo**, costruisce le due curve a
gradini — offerta crescente, domanda decrescente — e ne trova l'intersezione, che e' il
prezzo di equilibrio dell'asta a prezzo uniforme.

Il modulo e' **indipendente dalla granularita'** (decisione D-15): non sa e non deve sapere
se il periodo che sta elaborando dura 15, 30 o 60 minuti. Riceve un insieme di offerte gia'
filtrato e lavora su quello. La granularita' entra solo nella *selezione* delle offerte
(`offerte_periodo`) e nella conversione fra energia e potenza (`mgp.config.DURATA_ORE`).
Questo tiene il codice unico per tutto il campione, che a cavallo del 01/10/2025 cambia
risoluzione temporale (D-12).

Il modello d'asta implementato
------------------------------
Il MGP e' un'asta marginale a prezzo uniforme. Ordinando le offerte di vendita per prezzo
crescente e quelle di acquisto per prezzo decrescente si ottengono due funzioni a gradini:

    S(p) = somma delle quantita' offerte in vendita a prezzo <= p   (non decrescente)
    D(p) = somma delle quantita' offerte in acquisto a prezzo >= p  (non crescente)

Il prezzo di equilibrio e' il piu' piccolo prezzo al quale l'offerta cumulata raggiunge la
domanda cumulata: `p* = min { p : S(p) >= D(p) }`. Tutte le offerte in merito vengono
remunerate a `p*`, indipendentemente dal prezzo a cui erano state presentate.

Assunzioni e scostamenti dalle regole d'asta reali
-------------------------------------------------
1. **Accettazione parziale dell'offerta marginale.** Al prezzo di equilibrio la quantita'
   domandata e quella offerta in generale non coincidono esattamente: l'offerta marginale
   viene accettata solo in parte. E' l'approssimazione standard nella ricostruzione delle
   curve, ma nei dati `PARTIAL_QTY_ACCEPTED_IN` vale 'Y' solo su una minoranza di offerte
   (554 righe su 137.039 nel giorno pilota): il mercato vero accetta o rifiuta per intero e
   ricorre ad altri meccanismi. Lo scostamento riguarda una sola offerta per periodo.
2. **Offerte a blocchi trattate come divisibili** (D-03): il vincolo "tutto o niente" su
   piu' periodi non e' modellato.
3. **Nessun vincolo di transito** fra le zone incluse nel perimetro (D-10).

Queste assunzioni sono la ragione per cui il prezzo ricostruito non coincide sempre con
quello ufficiale; la loro misura complessiva e' la frequenza di match (D-09).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config


# --------------------------------------------------------------------------------------
# Selezione delle offerte di un periodo
# --------------------------------------------------------------------------------------
def offerte_periodo(
    df: pd.DataFrame,
    periodo: int,
    granularita: str,
    zone: list[str] | str | None = None,
    stati: list[str] | None = None,
    includi_altra_granularita: bool = False,
) -> pd.DataFrame:
    """
    Estrae le offerte che concorrono a una singola asta (una zona-perimetro, un periodo).

    Parameters
    ----------
    df : pd.DataFrame
        Offerte di un giorno, come restituite da `mgp.io_gme.carica_giorno`.
    periodo : int
        Numero del periodo, da interpretare secondo `granularita` (1-96 per PT15,
        1-48 per PT30, 1-24 per PT60).
    granularita : str
        Granularita' di riferimento dell'asta ('PT15', 'PT30', 'PT60').
    zone : list[str] | str | None
        Zone da includere nel perimetro. Default None = tutte le zone presenti nel
        DataFrame (utile quando il filtro di zona e' gia' stato fatto in lettura).
    stati : list[str] | None
        Valori di `STATUS_CD` ammessi. Default: `config.STATUS_IN_GARA` (D-06).
    includi_altra_granularita : bool
        Se True include anche le offerte presentate a granularita' diversa, riscalandone
        la quantita' sul periodo di riferimento (vedi `_riscala_quantita`). E' la variante
        da confrontare per sciogliere D-13.

    Returns
    -------
    pd.DataFrame
        Le offerte dell'asta, con la colonna `QUANTITY_NO` gia' riscalata dove necessario.

    Note
    ----
    Il filtro su `PERIOD` senza il filtro su `GRANULARITY` sarebbe un errore: nei file
    convivono periodi 1-96 (quarti d'ora), 1-48 (mezz'ore) e 1-24 (ore), e il numero da
    solo non identifica un istante.
    """
    stati = list(stati) if stati is not None else list(config.STATUS_IN_GARA)

    sel = df[df["STATUS_CD"].isin(stati)]
    if zone is not None:
        zone = [zone] if isinstance(zone, str) else list(zone)
        sel = sel[sel["ZONE_CD"].isin(zone)]

    principale = sel[(sel["GRANULARITY"] == granularita) & (sel["PERIOD"] == periodo)]
    if not includi_altra_granularita:
        return principale.copy()

    pezzi = [principale.copy()]
    for altra in sel["GRANULARITY"].dropna().unique():
        if altra == granularita:
            continue
        pezzi.append(_riscala_quantita(sel, altra, granularita, periodo))
    return pd.concat(pezzi, ignore_index=True)


def periodo_contenitore(periodo: int, da: str, a: str) -> int:
    """
    Trova il periodo di granularita' `da` che contiene il periodo `periodo` di
    granularita' `a`.

    Esempio: il quarto d'ora 40 e' contenuto nell'ora 10 (i quarti 37-40 formano l'ora 10).

    Parameters
    ----------
    periodo : int
        Numero del periodo nella granularita' di riferimento `a`.
    da : str
        Granularita' dell'offerta da collocare (es. 'PT60').
    a : str
        Granularita' dell'asta (es. 'PT15').

    Returns
    -------
    int
        Numero del periodo nella granularita' `da`.
    """
    istante_iniziale = (periodo - 1) * config.DURATA_ORE[a]   # ore dall'inizio del giorno
    return int(istante_iniziale // config.DURATA_ORE[da]) + 1


def _riscala_quantita(
    sel: pd.DataFrame, da: str, a: str, periodo: int
) -> pd.DataFrame:
    """
    Porta nell'asta di un periodo le offerte presentate a un'altra granularita'.

    Esempio: un'offerta oraria (PT60) copre quattro quarti d'ora. Per farla concorrere
    all'asta del quarto d'ora 40 si individua l'ora che lo contiene (l'ora 10) e si usa la
    sua quantita' **invariata**, con lo stesso prezzo.

    Perche' la quantita' NON va divisa per quattro
    ----------------------------------------------
    `QUANTITY_NO` e' una **potenza** (MW, equivalentemente MWh/h), non l'energia del
    periodo. Verificato confrontando le quantita' assegnate a livello nazionale fra un
    giorno orario e uno a quarto d'ora: se fossero energie riferite al periodo, passando
    da PT60 a PT15 dovrebbero scendere a un quarto, mentre il rapporto osservato e' 0,83
    (15/01/2025: 38.334 in media all'ora; 31/03/2026: 31.956 in media al quarto d'ora — la
    differenza residua e' la stagionalita' del fabbisogno, gennaio contro marzo).

    Un'offerta oraria di X MW e' quindi X MW in ciascuno dei quattro quarti d'ora che
    compongono l'ora, e la conversione in energia (MWh) si fa moltiplicando per la durata
    del periodo (`config.DURATA_ORE`) solo quando serve un'energia, per esempio nel
    calcolo del ciclo della batteria.
    """
    fetta = sel[
        (sel["GRANULARITY"] == da)
        & (sel["PERIOD"] == periodo_contenitore(periodo, da, a))
    ]
    return fetta.copy()


# --------------------------------------------------------------------------------------
# Curve a gradini
# --------------------------------------------------------------------------------------
def curva_offerta(offerte: pd.DataFrame) -> pd.DataFrame:
    """
    Costruisce la curva di offerta aggregata (vendite, `PURPOSE_CD` = 'OFF').

    Returns
    -------
    pd.DataFrame
        Colonne `prezzo` (crescente) e `quantita_cumulata`: quantita' complessivamente
        offerta in vendita a un prezzo minore o uguale a `prezzo`.

    Perche' crescente
    -----------------
    Un produttore accetta di vendere a qualunque prezzo maggiore o uguale a quello che ha
    offerto: al crescere del prezzo di mercato si aggiungono impianti disposti a produrre,
    ordinati per costo. E' il merit order.
    """
    return _curva(offerte, config.PURPOSE_VENDITA, crescente=True)


def curva_domanda(offerte: pd.DataFrame) -> pd.DataFrame:
    """
    Costruisce la curva di domanda aggregata (acquisti, `PURPOSE_CD` = 'BID').

    Returns
    -------
    pd.DataFrame
        Colonne `prezzo` (decrescente) e `quantita_cumulata`: quantita' complessivamente
        domandata a un prezzo maggiore o uguale a `prezzo`.

    Perche' decrescente
    -------------------
    Un consumatore accetta di comprare a qualunque prezzo minore o uguale a quello che ha
    offerto: al crescere del prezzo la domanda si riduce. Le offerte di acquisto presentate
    al prezzo massimo (4.000 €/MWh) sono price taker e restano dentro a qualunque prezzo:
    e' il "gradino" rigido che rende la domanda molto anelastica.
    """
    return _curva(offerte, config.PURPOSE_ACQUISTO, crescente=False)


def _curva(offerte: pd.DataFrame, purpose: str, crescente: bool) -> pd.DataFrame:
    """Aggrega le offerte di un lato del mercato in una funzione a gradini cumulata."""
    lato = offerte[offerte["PURPOSE_CD"] == purpose]
    if lato.empty:
        return pd.DataFrame({"prezzo": [], "quantita_cumulata": []})

    # Offerte allo stesso prezzo: un solo gradino, quantita' sommate.
    per_prezzo = (
        lato.groupby("ENERGY_PRICE_NO", as_index=False)["QUANTITY_NO"]
        .sum()
        .sort_values("ENERGY_PRICE_NO", ascending=crescente)
    )
    return pd.DataFrame({
        "prezzo": per_prezzo["ENERGY_PRICE_NO"].to_numpy(),
        "quantita_cumulata": per_prezzo["QUANTITY_NO"].cumsum().to_numpy(),
    })


# --------------------------------------------------------------------------------------
# Prezzo di equilibrio
# --------------------------------------------------------------------------------------
@dataclass
class Equilibrio:
    """
    Esito del clearing di una singola asta.

    Attributes
    ----------
    prezzo : float | None
        Prezzo di equilibrio (€/MWh). None se le curve non si intersecano.
    quantita : float | None
        Quantita' scambiata (MWh): il minimo fra offerta e domanda cumulate al prezzo di
        equilibrio, cioe' la quantita' effettivamente scambiabile.
    offerta_cumulata : float | None
        Offerta cumulata al prezzo di equilibrio, prima del razionamento dell'offerta
        marginale.
    domanda_cumulata : float | None
        Domanda cumulata al prezzo di equilibrio.
    motivo : str
        'ok' se l'equilibrio esiste; altrimenti la ragione del fallimento
        ('curva_vuota', 'domanda_sempre_superiore', 'offerta_sempre_superiore').

    Perche' una dataclass e non una tupla
    -------------------------------------
    Il clearing viene chiamato decine di migliaia di volte e i suoi esiti vanno aggregati:
    avere campi con un nome rende il codice chiamante leggibile e permette di distinguere
    un equilibrio mancante da un equilibrio a prezzo zero, che sono cose diverse.
    """

    prezzo: float | None
    quantita: float | None
    offerta_cumulata: float | None
    domanda_cumulata: float | None
    motivo: str

    @property
    def esiste(self) -> bool:
        return self.prezzo is not None


def prezzo_equilibrio(offerte: pd.DataFrame) -> Equilibrio:
    """
    Trova il prezzo di equilibrio di una singola asta.

    Parameters
    ----------
    offerte : pd.DataFrame
        Offerte di una zona-perimetro e di un periodo, come restituite da
        `offerte_periodo`. Devono contenere `PURPOSE_CD`, `ENERGY_PRICE_NO`, `QUANTITY_NO`.

    Returns
    -------
    Equilibrio
        Prezzo, quantita' scambiata e diagnostica.

    Algoritmo
    ---------
    Si valutano le due curve cumulate sull'insieme di **tutti i prezzi presenti nell'asta**
    (unione dei prezzi di acquisto e di vendita) e si cerca il piu' piccolo prezzo al quale
    l'offerta cumulata raggiunge la domanda cumulata. L'insieme dei prezzi offerti e'
    sufficiente: le curve sono costanti a tratti e cambiano valore solo in corrispondenza
    di un prezzo offerto, quindi l'intersezione cade sempre su uno di questi punti.

    Il costo e' O(n log n) per l'ordinamento piu' O(n) per le somme cumulate, con n numero
    di offerte del periodo (dell'ordine del migliaio): trascurabile anche moltiplicato per
    le ~35.000 aste di un anno.

    Casi limite
    -----------
    * **Un lato del mercato e' vuoto** -> nessun equilibrio ('curva_vuota').
    * **La domanda supera l'offerta a ogni prezzo** -> nessun equilibrio
      ('domanda_sempre_superiore'). E' il caso di una zona importatrice modellata come
      isolata: nessun prezzo, per quanto alto, richiama abbastanza offerta interna.
    * **L'offerta supera la domanda gia' al prezzo minimo** -> l'equilibrio esiste e cade
      sul prezzo piu' basso presente nell'asta; e' la situazione di eccesso di offerta che
      genera i prezzi molto bassi o negativi.
    """
    vendita = offerte[offerte["PURPOSE_CD"] == config.PURPOSE_VENDITA]
    acquisto = offerte[offerte["PURPOSE_CD"] == config.PURPOSE_ACQUISTO]
    if vendita.empty or acquisto.empty:
        return Equilibrio(None, None, None, None, "curva_vuota")

    p_off = vendita["ENERGY_PRICE_NO"].to_numpy(dtype=float)
    q_off = vendita["QUANTITY_NO"].to_numpy(dtype=float)
    p_dom = acquisto["ENERGY_PRICE_NO"].to_numpy(dtype=float)
    q_dom = acquisto["QUANTITY_NO"].to_numpy(dtype=float)

    prezzi = np.unique(np.concatenate([p_off, p_dom]))

    # S(p): offerta cumulata a prezzo <= p. D(p): domanda cumulata a prezzo >= p.
    ordine_off = np.argsort(p_off, kind="stable")
    p_off_ord, q_off_ord = p_off[ordine_off], q_off[ordine_off]
    cum_off = np.cumsum(q_off_ord)
    # searchsorted 'right' -> quante offerte hanno prezzo <= p
    idx_off = np.searchsorted(p_off_ord, prezzi, side="right")
    S = np.where(idx_off > 0, cum_off[np.clip(idx_off - 1, 0, None)], 0.0)

    ordine_dom = np.argsort(p_dom, kind="stable")
    p_dom_ord, q_dom_ord = p_dom[ordine_dom], q_dom[ordine_dom]
    totale_dom = q_dom_ord.sum()
    cum_dom_sotto = np.cumsum(q_dom_ord)          # domanda con prezzo <= p
    idx_dom = np.searchsorted(p_dom_ord, prezzi, side="left")  # prezzo < p
    dom_sotto = np.where(idx_dom > 0, cum_dom_sotto[np.clip(idx_dom - 1, 0, None)], 0.0)
    D = totale_dom - dom_sotto                    # domanda con prezzo >= p

    incrocio = np.flatnonzero(S >= D)
    if incrocio.size == 0:
        return Equilibrio(None, None, None, None, "domanda_sempre_superiore")

    i = incrocio[0]
    p_star = float(prezzi[i])
    offerta_cum = float(S[i])
    domanda_cum = float(D[i])
    # La quantita' scambiata e' il minimo fra i due lati: l'offerta marginale entra solo
    # per la parte necessaria a pareggiare la domanda.
    quantita = float(min(offerta_cum, domanda_cum))

    return Equilibrio(p_star, quantita, offerta_cum, domanda_cum, "ok")


def curva_eccesso(offerte: pd.DataFrame) -> pd.DataFrame:
    """
    Calcola l'eccesso di offerta S(p) - D(p) su tutti i prezzi presenti nell'asta.

    Returns
    -------
    pd.DataFrame
        Colonne `prezzo`, `offerta_cumulata`, `domanda_cumulata`, `eccesso`.

    Proprieta' utile
    ----------------
    L'eccesso e' **monotono non decrescente**: S non decresce e D non cresce al crescere del
    prezzo. Ne segue che l'insieme dei prezzi che pareggiano il mercato, cioe' quelli con
    eccesso non negativo, e' sempre una semiretta [p*, +inf). Il prezzo di equilibrio e' il
    suo estremo inferiore.

    Quando pero' l'eccesso vale **esattamente zero su un tratto**, ogni prezzo di quel tratto
    pareggia domanda e offerta: l'equilibrio non e' unico e serve una regola per sceglierne
    uno. Questa funzione serve a misurare quanto spesso accade e quanto e' ampio il tratto.
    """
    vendita = offerte[offerte["PURPOSE_CD"] == config.PURPOSE_VENDITA]
    acquisto = offerte[offerte["PURPOSE_CD"] == config.PURPOSE_ACQUISTO]
    if vendita.empty or acquisto.empty:
        return pd.DataFrame(columns=["prezzo", "offerta_cumulata", "domanda_cumulata", "eccesso"])

    p_off = vendita["ENERGY_PRICE_NO"].to_numpy(dtype=float)
    q_off = vendita["QUANTITY_NO"].to_numpy(dtype=float)
    p_dom = acquisto["ENERGY_PRICE_NO"].to_numpy(dtype=float)
    q_dom = acquisto["QUANTITY_NO"].to_numpy(dtype=float)
    prezzi = np.unique(np.concatenate([p_off, p_dom]))

    ordine = np.argsort(p_off, kind="stable")
    p_o, q_o = p_off[ordine], q_off[ordine]
    cum_o = np.cumsum(q_o)
    idx = np.searchsorted(p_o, prezzi, side="right")
    S = np.where(idx > 0, cum_o[np.clip(idx - 1, 0, None)], 0.0)

    ordine = np.argsort(p_dom, kind="stable")
    p_d, q_d = p_dom[ordine], q_dom[ordine]
    cum_d = np.cumsum(q_d)
    idx = np.searchsorted(p_d, prezzi, side="left")
    D = q_d.sum() - np.where(idx > 0, cum_d[np.clip(idx - 1, 0, None)], 0.0)

    return pd.DataFrame({
        "prezzo": prezzi,
        "offerta_cumulata": S,
        "domanda_cumulata": D,
        "eccesso": S - D,
    })


def intervallo_equilibrio(offerte: pd.DataFrame, tolleranza: float = 1e-6) -> dict[str, float]:
    """
    Individua l'intervallo di prezzi che pareggiano il mercato.

    Parameters
    ----------
    offerte : pd.DataFrame
        Offerte dell'asta.
    tolleranza : float
        Ampiezza entro cui un eccesso e' considerato nullo (MW).

    Returns
    -------
    dict
        `prezzo_minimo` (quello scelto da `prezzo_equilibrio`), `prezzo_massimo` (l'estremo
        superiore del tratto a eccesso nullo, uguale al minimo se l'equilibrio e' unico),
        `ampiezza` (€/MWh), `eccesso_al_minimo` (MW), `degenere` (bool).

    A che serve
    -----------
    Se l'equilibrio non e' unico, la scelta della regola (prezzo piu' basso, piu' alto, punto
    medio) sposta il prezzo ricostruito senza che nulla sia sbagliato nei dati. Confrontando
    l'intervallo con il prezzo ufficiale si capisce se uno scarto e' un errore di
    ricostruzione oppure solo una convenzione diversa nella scelta del punto.
    """
    ec = curva_eccesso(offerte)
    if ec.empty:
        return {"prezzo_minimo": float("nan"), "prezzo_massimo": float("nan"),
                "ampiezza": float("nan"), "eccesso_al_minimo": float("nan"),
                "degenere": False}

    ammissibili = ec[ec["eccesso"] >= -tolleranza]
    if ammissibili.empty:
        return {"prezzo_minimo": float("nan"), "prezzo_massimo": float("nan"),
                "ampiezza": float("nan"), "eccesso_al_minimo": float("nan"),
                "degenere": False}

    p_min = float(ammissibili["prezzo"].iloc[0])
    eccesso_min = float(ammissibili["eccesso"].iloc[0])

    # Tratto piatto: prezzi successivi in cui l'eccesso resta nullo.
    if abs(eccesso_min) <= tolleranza:
        piatto = ammissibili[ammissibili["eccesso"].abs() <= tolleranza]
        # Il tratto e' contiguo perche' l'eccesso e' monotono.
        p_max = float(piatto["prezzo"].iloc[-1])
    else:
        p_max = p_min

    return {
        "prezzo_minimo": p_min,
        "prezzo_massimo": p_max,
        "ampiezza": p_max - p_min,
        "eccesso_al_minimo": eccesso_min,
        "degenere": p_max > p_min,
    }


def import_netto(
    df: pd.DataFrame,
    periodo: int,
    granularita: str,
    zone: list[str] | str | None = None,
) -> float:
    """
    Calcola l'import netto del perimetro in un periodo, dalle quantita' assegnate.

    Parameters
    ----------
    df : pd.DataFrame
        Offerte del giorno (tutte le zone).
    periodo, granularita : int, str
        Asta di riferimento.
    zone : list[str] | str | None
        Zone del perimetro.

    Returns
    -------
    float
        Acquisti assegnati meno vendite assegnate nel perimetro (MW). Se positivo, il
        perimetro compra piu' di quanto vende: la differenza arriva da fuori.

    Perche' serve
    -------------
    Le offerte pubbliche di una zona non contengono l'energia che vi arriva dalle altre
    zone o dall'estero: nel giorno pilota, in NORD, gli acquisti assegnati superano le
    vendite assegnate di circa 6.300 MW per periodo. Ricostruendo la curva con le sole
    offerte interne manca quindi la parte a basso costo dell'offerta, e il prezzo risulta
    sistematicamente troppo alto (di circa 100 €/MWh sul giorno pilota).

    Le granularita' vengono sommate senza riscalare le quantita', perche' `QUANTITY_NO` e
    `AWARDED_QUANTITY_NO` sono potenze (MW): un'offerta oraria di X MW contribuisce X MW a
    ciascuno dei quarti d'ora che compongono l'ora.

    Limite
    ------
    L'import e' calcolato **dall'esito osservato dell'asta**, quindi e' una grandezza
    calibrata e non prevista dal modello. Va trattato come un blocco esogeno e inelastico:
    quando si simulera' la batteria si assumera' che i flussi di import non reagiscano alla
    variazione di prezzo che essa induce. E' un'assunzione forte, da dichiarare fra i limiti.
    """
    zone_sel = (
        None if zone is None else ([zone] if isinstance(zone, str) else list(zone))
    )
    totali: dict[str, float] = {}
    for g in df["GRANULARITY"].dropna().unique():
        per = periodo if g == granularita else periodo_contenitore(periodo, g, granularita)
        fetta = df[(df["GRANULARITY"] == g) & (df["PERIOD"] == per)]
        if zone_sel is not None:
            fetta = fetta[fetta["ZONE_CD"].isin(zone_sel)]
        for lato, valore in fetta.groupby("PURPOSE_CD")["AWARDED_QUANTITY_NO"].sum().items():
            totali[lato] = totali.get(lato, 0.0) + float(valore)
    return totali.get(config.PURPOSE_ACQUISTO, 0.0) - totali.get(config.PURPOSE_VENDITA, 0.0)


def aggiungi_import(offerte: pd.DataFrame, quantita: float) -> pd.DataFrame:
    """
    Aggiunge lo scambio netto del perimetro con l'esterno come blocco price taker.

    Parameters
    ----------
    offerte : pd.DataFrame
        Offerte dell'asta.
    quantita : float
        Scambio netto in MW, con segno: positivo se il perimetro importa, negativo se
        esporta (vedi `import_netto`).

    Returns
    -------
    pd.DataFrame
        Le offerte con in piu' il blocco di scambio.

    Trattamento simmetrico dei due segni
    ------------------------------------
    * **Import** (quantita' > 0): entra come **offerta di vendita al prezzo minimo**.
      E' energia gia' allocata altrove che viene collocata comunque, quindi si comporta da
      offerta anelastica e trasla la curva di offerta verso destra.
    * **Export** (quantita' < 0): entra come **offerta di acquisto al prezzo massimo**.
      E' domanda proveniente da fuori il perimetro, che compra a qualunque prezzo: trasla
      la curva di domanda verso destra.

    Perche' la simmetria conta
    --------------------------
    Trattando solo l'import e ignorando l'export si sovrastima l'offerta disponibile
    all'interno del perimetro e il prezzo ricostruito risulta troppo basso. Sul mese di
    gennaio 2025, prima di introdurre il caso negativo, i dieci periodi con l'errore piu'
    grande erano **tutti** periodi di export netto (fino a -85 €/MWh di scarto nella sera
    del 20/01/2025, quando NORD esportava circa 3.700 MW).
    """
    if quantita == 0:
        return offerte
    if quantita > 0:
        blocco = {
            "PURPOSE_CD": config.PURPOSE_VENDITA,
            "ENERGY_PRICE_NO": config.PREZZO_MINIMO,
            "QUANTITY_NO": float(quantita),
        }
    else:
        blocco = {
            "PURPOSE_CD": config.PURPOSE_ACQUISTO,
            "ENERGY_PRICE_NO": config.PREZZO_MASSIMO,
            "QUANTITY_NO": float(-quantita),
        }
    blocco.update({"STATUS_CD": "SCAMBIO", "ZONE_CD": "SCAMBIO"})
    return pd.concat([offerte, pd.DataFrame([blocco])], ignore_index=True)


def impatto_prezzo(offerte: pd.DataFrame, delta_mw: float) -> dict[str, float]:
    """
    Misura di quanto si sposta il prezzo di equilibrio iniettando o sottraendo potenza.

    Parameters
    ----------
    offerte : pd.DataFrame
        Offerte dell'asta, blocco di scambio gia' incluso.
    delta_mw : float
        Potenza aggiunta, con segno: positiva = offerta addizionale (una batteria che
        scarica), negativa = domanda addizionale (una batteria che carica).

    Returns
    -------
    dict
        `prezzo_base`, `prezzo_modificato`, `variazione` (€/MWh) e `sensibilita`, cioe' la
        variazione di prezzo per 100 MW immessi, in valore assoluto.

    Perche' questa funzione e' centrale
    -----------------------------------
    E' esattamente l'effetto di feedback che la tesi vuole misurare: una batteria che
    scarica aggiunge offerta e abbassa il prezzo, una che carica aggiunge domanda e lo
    alza. La stessa grandezza spiega pero' anche l'accuratezza della ricostruzione: dove
    le curve sono quasi tangenti, cioe' dove l'eccesso di offerta varia lentamente con il
    prezzo, un piccolo errore di quantita' si traduce in un grande errore di prezzo.
    Misurare la sensibilita' significa quindi sapere sia quanto conta la batteria sia
    quanto ci si puo' fidare del prezzo ricostruito, che sono due facce della stessa cosa.
    """
    base = prezzo_equilibrio(offerte)
    modificato = prezzo_equilibrio(aggiungi_import(offerte, delta_mw))
    if base.prezzo is None or modificato.prezzo is None:
        return {"prezzo_base": float("nan"), "prezzo_modificato": float("nan"),
                "variazione": float("nan"), "sensibilita": float("nan")}
    variazione = modificato.prezzo - base.prezzo
    return {
        "prezzo_base": base.prezzo,
        "prezzo_modificato": modificato.prezzo,
        "variazione": variazione,
        "sensibilita": abs(variazione) * 100.0 / abs(delta_mw),
    }


def clearing_giorno(
    df: pd.DataFrame,
    granularita: str,
    zone: list[str] | str | None = None,
    stati: list[str] | None = None,
    includi_altra_granularita: bool = False,
    con_import: bool = False,
) -> pd.DataFrame:
    """
    Esegue il clearing su tutti i periodi di un giorno.

    Parameters
    ----------
    df : pd.DataFrame
        Offerte del giorno.
    granularita : str
        Granularita' delle aste da ricostruire ('PT15', 'PT30', 'PT60').
    zone, stati, includi_altra_granularita
        Come in `offerte_periodo`.
    con_import : bool
        Se True aggiunge alla curva di offerta il blocco esogeno di import netto del
        perimetro (vedi `import_netto`). Senza di esso il prezzo di una zona importatrice
        risulta sistematicamente troppo alto.

    Returns
    -------
    pd.DataFrame
        Una riga per periodo, con: `PERIOD`, `prezzo`, `quantita`, `offerta_cumulata`,
        `domanda_cumulata`, `motivo`, `n_offerte`, `import_netto`.

    Note
    ----
    I periodi sono quelli effettivamente presenti nei dati, non quelli teorici: se un
    giorno di cambio ora legale ha 92 o 100 quarti d'ora, la funzione se ne accorge dai
    dati invece di assumerne 96.
    """
    periodi = sorted(
        df.loc[df["GRANULARITY"] == granularita, "PERIOD"].dropna().unique().tolist()
    )
    righe = []
    for periodo in periodi:
        off = offerte_periodo(
            df, int(periodo), granularita,
            zone=zone, stati=stati,
            includi_altra_granularita=includi_altra_granularita,
        )
        imp = import_netto(df, int(periodo), granularita, zone=zone) if con_import else 0.0
        if con_import:
            off = aggiungi_import(off, imp)
        eq = prezzo_equilibrio(off)
        righe.append({
            "PERIOD": int(periodo),
            "prezzo": eq.prezzo,
            "quantita": eq.quantita,
            "offerta_cumulata": eq.offerta_cumulata,
            "domanda_cumulata": eq.domanda_cumulata,
            "motivo": eq.motivo,
            "n_offerte": len(off),
            "import_netto": imp,
        })
    return pd.DataFrame(righe)


def confronta_con_ufficiale(
    ricostruito: pd.DataFrame,
    ufficiale: pd.DataFrame,
    tolleranze: tuple[float, ...] = (0.01, 0.5, 1.0, 5.0),
) -> dict[str, float]:
    """
    Confronta i prezzi ricostruiti con quelli ufficiali e calcola la frequenza di match.

    Parameters
    ----------
    ricostruito : pd.DataFrame
        Output di `clearing_giorno` (colonne `PERIOD`, `prezzo`).
    ufficiale : pd.DataFrame
        Output di `mgp.io_gme.prezzi_ufficiali` (colonne `PERIOD`, `prezzo_ufficiale`).
    tolleranze : tuple[float, ...]
        Soglie in €/MWh entro cui considerare i due prezzi coincidenti.

    Returns
    -------
    dict
        `n_periodi`, `n_ricostruiti`, `errore_mediano`, `errore_medio`, `bias_mediano`
        (ricostruito meno ufficiale, con segno) e una voce `match_<tolleranza>` per ciascuna
        soglia, espressa in percentuale sui periodi ricostruiti.

    Perche' piu' tolleranze
    -----------------------
    Un match a 0,01 €/MWh dice che l'algoritmo replica l'asta; un match a 1 o 5 €/MWh dice
    che la ricostruzione e' utilizzabile per valutare l'effetto di una batteria, che e'
    l'uso che ce ne faremo. Le due cose vanno tenute distinte (D-09).
    """
    unito = ricostruito.merge(ufficiale[["PERIOD", "prezzo_ufficiale"]], on="PERIOD", how="left")
    validi = unito.dropna(subset=["prezzo", "prezzo_ufficiale"])
    scarto = validi["prezzo"] - validi["prezzo_ufficiale"]

    esito: dict[str, float] = {
        "n_periodi": len(unito),
        "n_ricostruiti": len(validi),
        "errore_mediano": float(scarto.abs().median()) if len(validi) else float("nan"),
        "errore_medio": float(scarto.abs().mean()) if len(validi) else float("nan"),
        "bias_mediano": float(scarto.median()) if len(validi) else float("nan"),
    }
    for t in tolleranze:
        esito[f"match_{t}"] = (
            float(100 * (scarto.abs() <= t).sum() / len(validi)) if len(validi) else 0.0
        )
    return esito
