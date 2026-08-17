"""
Conto economico dell'investitore: dal margine lordo di mercato al valore attuale netto.

Il livello 2 dell'analisi
-------------------------
Il progetto e' organizzato su **due livelli**, e questo modulo e' il secondo (D-34).

Il **livello 1** — `curve` e `batteria` — misura l'effetto dell'accumulo sul prezzo di
equilibrio: erosione di profitto e soglia price taker/price maker. E' un fenomeno di
**mercato**, e come tale non dipende da come l'investitore sia tassato o da quanto costi
costruire l'impianto. I profitti che quel livello restituisce sono percio' **margini lordi
di mercato**, e devono restarlo: mescolarvi i costi renderebbe la soglia funzione del regime
fiscale, il che sarebbe economicamente sbagliato.

Il **livello 2** e' questo: prende il margine lordo e vi applica, in un unico punto e una
volta sola, tutti i costi dell'investitore — degrado, oneri sull'energia prelevata, capitale
investito, costi operativi — scontandoli sulla vita utile.

Il degrado, che sta a cavallo
-----------------------------
Il costo di degrado e' l'unico parametro che compare in entrambi i livelli, con due ruoli
diversi che conviene tenere distinti:

* nel **piano** (`batteria.profilo_ottimo`) e' un **segnale operativo**: serve a decidere
  quando valga la pena ciclare, ed e' cio' che genera le giornate a piano vuoto (D-31). Li'
  non e' un esborso, e' una soglia di convenienza;
* qui e' un **costo monetario**, sottratto una volta sola dal margine.

Non e' quindi una duplicazione: e' lo stesso parametro usato prima per decidere e poi per
contare.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config


@dataclass
class ContoEconomico:
    """
    Esito del conto economico di un progetto di accumulo.

    Attributes
    ----------
    margine_lordo_annuo : float
        Somma sui giorni del margine di mercato, riportata su base annua.
    costo_degrado_annuo : float
        Costo monetario del degrado sull'energia ciclata in un anno.
    onere_acquisto_annuo : float
        Maggior costo dell'energia prelevata dovuto a K > 1. E' nullo in regime net-settled.
    opex_annuo : float
    capex : float
    ricavo_netto_primo_anno : float
        Margine lordo meno degrado, oneri e costi operativi, prima dello sconto.
    van : float
        Valore attuale netto sull'intera vita utile.
    tempo_di_ritorno_anni : float
        Anni necessari perche' i flussi cumulati non scontati coprano il capitale investito;
        `inf` se non accade entro la vita utile.
    """

    margine_lordo_annuo: float
    costo_degrado_annuo: float
    onere_acquisto_annuo: float
    opex_annuo: float
    capex: float
    ricavo_netto_primo_anno: float
    van: float
    tempo_di_ritorno_anni: float


def annualizza(giornaliero: float, giorni_campione: int) -> float:
    """
    Porta su base annua una grandezza misurata su un campione di giorni.

    Assunzione dichiarata: i giorni del campione sono rappresentativi dell'anno. Finche' il
    campione e' un solo mese invernale l'estrapolazione e' grossolana, ed e' una delle
    ragioni per cui i risultati economici restano preliminari fino all'estensione a dodici
    mesi (D-28).
    """
    if giorni_campione <= 0:
        return float("nan")
    return giornaliero / giorni_campione * 365.0


def conto_economico(
    margine_lordo_annuo: float,
    energia_scaricata_annua_mwh: float,
    energia_caricata_annua_mwh: float,
    prezzo_medio_acquisto: float,
    capacita_mwh: float,
    parametri: dict[str, float] | None = None,
    parametri_bess: dict[str, float] | None = None,
) -> ContoEconomico:
    """
    Calcola il valore attuale netto di un progetto di accumulo.

    Parameters
    ----------
    margine_lordo_annuo : float
        Margine di mercato annuo, in euro. **Va calcolato sul profitto price maker** alla
        capacita' aggregata di scenario, non su quello price taker: quest'ultimo ignora
        l'effetto dell'accumulo sul prezzo e sovrastima sistematicamente il ricavo (D-36).
    energia_scaricata_annua_mwh, energia_caricata_annua_mwh : float
        Energia immessa e prelevata in un anno, in MWh.
    prezzo_medio_acquisto : float
        Prezzo medio dell'energia prelevata, in €/MWh. Serve a monetizzare l'onere K.
    capacita_mwh : float
        Capacita' energetica installata, su cui si commisurano CapEx e OpEx.
    parametri : dict, opzionale
        Parametri economici; se omesso si usa `config.PARAMETRI_ECONOMICI`.
    parametri_bess : dict, opzionale
        Parametri tecnici; se omesso si usa `config.PARAMETRI_BESS`.

    Returns
    -------
    ContoEconomico

    Come sono applicati i costi
    ---------------------------
    Tutti in questo punto e una volta sola:

    * **degrado**: costo variabile per MWh ciclato, sull'energia scaricata;
    * **oneri sull'energia prelevata**: $(K - 1)$ volte il valore di mercato dell'energia
      caricata. Con $K = 1$ il termine e' nullo per costruzione, ed e' il regime net-settled;
    * **costi operativi**: per MWh installato, ogni anno;
    * **capitale**: per MWh installato, all'anno zero.

    I ricavi decadono di `degrado_ricavi_annuo` l'anno, perche' la capacita' utile si riduce,
    e si scontano al tasso indicato sulla vita utile.

    Che cosa NON e' incluso
    -----------------------
    Ricavi da servizi diversi dall'arbitraggio sul mercato del giorno prima — riserva,
    regolazione di frequenza, capacity market, aste MACSE per il time-shifting. Un impianto
    reale li cumula, quindi il valore attuale netto calcolato qui e' un **limite inferiore**
    della redditivita' complessiva, ed e' un limite dichiarato del lavoro.
    """
    p = dict(config.PARAMETRI_ECONOMICI if parametri is None else parametri)
    pb = dict(config.PARAMETRI_BESS if parametri_bess is None else parametri_bess)

    costo_degrado = pb["costo_variabile_eur_mwh"] * energia_scaricata_annua_mwh
    onere_acquisto = ((pb["rapporto_prezzo_acquisto"] - 1.0)
                      * prezzo_medio_acquisto * energia_caricata_annua_mwh)
    opex = p["opex_eur_mwh_anno"] * capacita_mwh
    capex = p["capex_eur_mwh"] * capacita_mwh

    netto_primo_anno = margine_lordo_annuo - costo_degrado - onere_acquisto - opex

    anni = int(round(p["vita_utile_anni"]))
    tasso = p["tasso_sconto"]
    decadimento = p["degrado_ricavi_annuo"]

    van = -capex
    cumulato = 0.0
    ritorno = float("inf")
    for anno in range(1, anni + 1):
        # Il decadimento colpisce i ricavi, non i costi fissi.
        margine = margine_lordo_annuo * (1.0 - decadimento) ** (anno - 1)
        degrado = costo_degrado * (1.0 - decadimento) ** (anno - 1)
        onere = onere_acquisto * (1.0 - decadimento) ** (anno - 1)
        flusso = margine - degrado - onere - opex
        van += flusso / (1.0 + tasso) ** anno
        cumulato += flusso
        if ritorno == float("inf") and cumulato >= capex:
            ritorno = float(anno)

    return ContoEconomico(
        margine_lordo_annuo=float(margine_lordo_annuo),
        costo_degrado_annuo=float(costo_degrado),
        onere_acquisto_annuo=float(onere_acquisto),
        opex_annuo=float(opex),
        capex=float(capex),
        ricavo_netto_primo_anno=float(netto_primo_anno),
        van=float(van),
        tempo_di_ritorno_anni=ritorno,
    )


def da_erosioni(
    erosioni: pd.DataFrame,
    potenza_mw: float,
    prezzo_medio_acquisto: float,
    durata_ore: float | None = None,
    **parametri,
) -> ContoEconomico:
    """
    Costruisce il conto economico a partire dalla tabella delle erosioni di una capacita'.

    Usa la colonna `profitto_price_maker`, cioe' il margine effettivamente realizzabile una
    volta che l'accumulo ha spostato i prezzi. E' la scelta corretta: usare il price taker
    equivarrebbe a promettere all'investitore un ricavo che la sua stessa presenza sul
    mercato distrugge.
    """
    if durata_ore is None:
        durata_ore = config.PARAMETRI_BESS["durata_ore"]
    fetta = erosioni[erosioni["potenza_mw"] == potenza_mw]
    if fetta.empty:
        raise ValueError(f"Nessuna riga per potenza_mw = {potenza_mw}")

    giorni = int(fetta["data"].nunique())
    margine = annualizza(float(fetta["profitto_price_maker"].sum()), giorni)
    scaricata = annualizza(float(fetta["energia_ciclata_mwh"].sum()), giorni)
    # L'energia prelevata eccede quella immessa per la perdita di ciclo.
    rendimento = config.PARAMETRI_BESS["rendimento_ciclo"]
    caricata = scaricata / rendimento if rendimento else float("nan")

    return conto_economico(
        margine_lordo_annuo=margine,
        energia_scaricata_annua_mwh=scaricata,
        energia_caricata_annua_mwh=caricata,
        prezzo_medio_acquisto=prezzo_medio_acquisto,
        capacita_mwh=potenza_mw * durata_ore,
        **parametri,
    )
