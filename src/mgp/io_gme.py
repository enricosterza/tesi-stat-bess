"""
Lettura e normalizzazione dei file XML "OffertePubbliche" del MGP (GME).

Perche' un modulo dedicato invece di `pandas.read_xml`
-----------------------------------------------------
`pandas.read_xml` costruisce in memoria l'intero albero DOM del documento. Il file del
31/03/2026 pesa 574 MB e contiene 568.185 offerte: l'albero occuperebbe diversi GB di RAM
e la lettura andrebbe rifatta da capo a ogni esecuzione. Qui si usa invece
`lxml.etree.iterparse`, che scorre il documento in streaming (memoria costante), applica
il filtro di zona *durante* il parsing (cosi' delle 568k righe se ne materializzano solo le
137k della zona NORD) e salva il risultato in cache Parquet: dalla seconda esecuzione in poi
il caricamento e' immediato.

Struttura dei dati GME (verificata sui file 2015 e 2026)
-------------------------------------------------------
Il documento e' un `NewDataSet` che contiene prima uno schema XSD inline e poi una sequenza
di elementi `OfferteOperatori`, uno per ciascuna offerta. Ogni offerta e' una coppia
(prezzo, quantita') presentata da un operatore per una singola zona e un singolo periodo.

Due schemi convivono nell'archivio 2015-2026:

* schema "recente" (visto sul 2026): campi `PERIOD` (1-96 con `GRANULARITY`='PT15') e
  `GRANULARITY`, piu' `OFFER_TYPE` e `BLOCK_ID` per le offerte a blocchi;
* schema "storico" (visto sul 2015): campo `INTERVAL_NO` (ora 1-24), nessuna `GRANULARITY`,
  nessun `OFFER_TYPE`/`BLOCK_ID`.

Il lettore normalizza il secondo nel primo (`INTERVAL_NO` -> `PERIOD`, `GRANULARITY`='PT60'),
in modo che il resto della pipeline lavori su un unico schema. La data esatta del passaggio
di granularita' non e' ancora stata mappata su tutto l'archivio: e' un controllo da fare
quando si estendera' l'analisi oltre il giorno pilota (vedi docs/DIARIO.md, D-05).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd
from lxml import etree

from . import config


# --------------------------------------------------------------------------------------
# Conversioni difensive
# --------------------------------------------------------------------------------------
def _to_float(valore: str | None) -> float | None:
    """
    Converte in float un valore numerico proveniente dall'XML GME.

    Parameters
    ----------
    valore : str | None
        Testo del nodo XML (es. '146.800', '1100.00', '' oppure None).

    Returns
    -------
    float | None
        Il valore numerico, oppure None se il campo e' vuoto/assente (diventera' NaN
        nel DataFrame).

    Assunzioni e note
    -----------------
    Nell'XML di GME il separatore decimale e' il **punto**: verificato sia sul file del
    31/03/2026 ('146.800', '1100.00', '149.45') sia su un file del 2015 ('2.256', '50.82').
    La virgola compare invece negli export Excel/CSV dello stesso dato. La conversione qui
    resta comunque difensiva (normalizza un'eventuale virgola) perche' l'archivio copre
    undici anni e non e' stato ispezionato file per file: se in qualche annata comparisse
    la virgola, la lettura non si romperebbe silenziosamente producendo NaN.

    Il separatore delle migliaia non e' presente nei dati GME; se lo fosse, questa
    funzione lo interpreterebbe male: per questo `riepilogo()` controlla range e NaN
    delle colonne numeriche a ogni caricamento.
    """
    if valore is None:
        return None
    v = valore.strip()
    if not v:
        return None
    if "," in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _normalizza_record(d: dict[str, str]) -> dict[str, str]:
    """
    Riporta un record dello schema storico (2015) allo schema recente (2026).

    Trasformazioni
    --------------
    * `INTERVAL_NO` -> `PERIOD` (nei file storici il periodo e' l'ora del giorno, 1-24);
    * `GRANULARITY` assente -> 'PT60' (granularita' oraria, coerente con `INTERVAL_NO`).

    Il record viene modificato sul posto e restituito.
    """
    if "PERIOD" not in d and "INTERVAL_NO" in d:
        d["PERIOD"] = d["INTERVAL_NO"]
    if not d.get("GRANULARITY"):
        d["GRANULARITY"] = "PT60"
    return d


# --------------------------------------------------------------------------------------
# Lettura in streaming
# --------------------------------------------------------------------------------------
def _apri_sorgente(path: Path):
    """
    Restituisce un file-like leggibile dall'XML, gestendo sia .xml sia .zip.

    L'archivio storico GME e' distribuito come uno .zip al giorno contenente l'XML omonimo.
    Lo zip viene letto in streaming, senza estrarlo su disco (evita di scrivere GB inutili).
    """
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        nomi = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not nomi:
            raise ValueError(f"Lo zip {path.name} non contiene alcun file .xml")
        return zf.open(nomi[0])
    return open(path, "rb")


def itera_offerte(
    path: Path,
    zona: str | None = None,
    granularita: str | None = None,
) -> Iterator[dict[str, str]]:
    """
    Scorre in streaming le offerte di un file GME, restituendo un dizionario per offerta.

    Parameters
    ----------
    path : Path
        File `.xml` o `.zip` delle offerte pubbliche MGP.
    zona : str | None
        Se valorizzata (es. 'NORD'), restituisce solo le offerte con quel `ZONE_CD`.
        Il filtro e' applicato *durante* il parsing: e' il primo dei due livelli di filtro
        adottati nella tesi (prima la zona, poi il singolo periodo).
    granularita : str | None
        Se valorizzata (es. 'PT15'), restituisce solo le offerte con quella `GRANULARITY`.

    Yields
    ------
    dict[str, str]
        Record grezzo (valori ancora testuali) gia' normalizzato di schema.

    Note implementative
    -------------------
    Dopo aver consumato ciascun elemento si esegue `el.clear()` e si eliminano i fratelli
    precedenti: senza questa pulizia lxml manterrebbe in memoria l'intero documento,
    vanificando lo streaming.
    """
    sorgente = _apri_sorgente(path)
    try:
        contesto = etree.iterparse(sorgente, events=("end",), tag=config.TAG_OFFERTA)
        for _, el in contesto:
            d = {figlio.tag: (figlio.text or "") for figlio in el}
            _normalizza_record(d)

            # Pulizia della memoria: elemento corrente e fratelli gia' processati.
            el.clear()
            parent = el.getparent()
            if parent is not None:
                while el.getprevious() is not None:
                    del parent[0]

            if zona is not None and d.get("ZONE_CD") != zona:
                continue
            if granularita is not None and d.get("GRANULARITY") != granularita:
                continue
            yield d
    finally:
        sorgente.close()


def leggi_offerte_xml(
    path: Path,
    zona: str | None = None,
    granularita: str | None = None,
    colonne: Iterable[str] | None = None,
) -> pd.DataFrame:
    """
    Legge un file di offerte pubbliche MGP e restituisce un DataFrame tipizzato.

    Parameters
    ----------
    path : Path
        File `.xml` o `.zip` delle offerte pubbliche.
    zona : str | None
        Filtro su `ZONE_CD` applicato in fase di parsing (default: nessun filtro).
    granularita : str | None
        Filtro su `GRANULARITY` applicato in fase di parsing (default: nessun filtro).
    colonne : Iterable[str] | None
        Colonne da conservare. Default: `config.COLONNE_UTILI`. Le colonne assenti nel
        file (tipicamente `OFFER_TYPE`/`BLOCK_ID` nei file storici) vengono create vuote,
        cosi' lo schema del DataFrame e' stabile fra annate diverse.

    Returns
    -------
    pd.DataFrame
        Una riga per offerta. Le colonne di `config.COLONNE_NUMERICHE` sono `float64`
        (`PERIOD` e' `Int64` nullable); le altre restano stringhe.

    Assunzioni
    ----------
    * Ogni elemento `OfferteOperatori` e' una coppia (prezzo, quantita') indipendente.
      Le offerte a blocchi (`OFFER_TYPE`='B', ~0,8% delle righe nel file pilota) sono
      in realta' vincolate fra loro "tutto o niente" su piu' periodi: qui vengono
      trattate come offerte semplici. Scelta registrata in docs/decisioni.md (D-03).
    * Non viene applicato alcun filtro su `STATUS_CD`: la selezione degli status che
      concorrono alla ricostruzione delle curve e' una decisione metodologica a valle
      (D-06), non una scelta di lettura del dato.
    """
    colonne = list(colonne) if colonne is not None else list(config.COLONNE_UTILI)

    record = list(itera_offerte(path, zona=zona, granularita=granularita))
    df = pd.DataFrame.from_records(record)

    # Schema stabile: colonne mancanti create vuote, colonne extra scartate.
    for c in colonne:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[colonne]

    for c in config.COLONNE_NUMERICHE:
        if c in df.columns:
            df[c] = df[c].map(_to_float)
    if "PERIOD" in df.columns:
        df["PERIOD"] = df["PERIOD"].astype("Int64")

    return df


# --------------------------------------------------------------------------------------
# Caricamento con cache
# --------------------------------------------------------------------------------------
def carica_giorno(
    data: str = config.DATA_PILOTA,
    zona: str | None = config.ZONA_DEFAULT,
    granularita: str | None = None,
    usa_cache: bool = True,
) -> pd.DataFrame:
    """
    Carica le offerte di un giorno (con cache Parquet).

    Parameters
    ----------
    data : str
        Data in formato 'YYYYMMDD'. Default: giorno pilota della tesi (31/03/2026).
    zona : str | None
        Zona di mercato da estrarre (default 'NORD').
    granularita : str | None
        Granularita' da estrarre. Default None = tutte, cosi' la cache conserva anche le
        righe PT60/PT30 e resta possibile quantificare cosa si sta escludendo.
    usa_cache : bool
        Se True e la cache esiste, la rilegge invece di riparsare l'XML.

    Returns
    -------
    pd.DataFrame
        Le offerte del giorno/zona richiesti.

    Note
    ----
    La cache vive in `data/interim/` (esclusa da git perche' rigenerabile). Il parsing del
    file pilota richiede alcuni minuti; la rilettura da Parquet e' dell'ordine dei secondi.
    """
    config.assicura_cartelle()
    suffisso_zona = zona or "TUTTE"
    suffisso_gran = granularita or "ALL"
    cache = config.INTERIM_DIR / f"offerte_{data}_{suffisso_zona}_{suffisso_gran}.parquet"

    if usa_cache and cache.exists():
        return pd.read_parquet(cache)

    df = leggi_offerte_xml(config.path_giorno(data), zona=zona, granularita=granularita)
    df.to_parquet(cache, index=False)
    return df


# --------------------------------------------------------------------------------------
# Controlli di validazione
# --------------------------------------------------------------------------------------
def riepilogo(df: pd.DataFrame) -> dict[str, pd.DataFrame | pd.Series]:
    """
    Produce le tabelle di controllo del caricamento.

    Parameters
    ----------
    df : pd.DataFrame
        Output di `carica_giorno` / `leggi_offerte_xml`.

    Returns
    -------
    dict
        Chiavi:
        * 'per_granularita'  : righe per `GRANULARITY` x `PURPOSE_CD`;
        * 'per_status'       : righe per `STATUS_CD` x `PURPOSE_CD`;
        * 'per_periodo'      : per ciascun periodo PT15, righe totali, righe BID/OFF e
                               quantita' offerte in acquisto/vendita (MW: le quantita' GME
                               sono potenze, vedi `config.DURATA_ORE`);
        * 'numeriche'        : statistiche descrittive e conteggio NaN delle colonne numeriche;
        * 'qualita'          : indicatori di qualita' del dato (offerte a blocchi, bilaterali,
                               price taker, quota di righe e di MW non PT15).

    Motivazione
    -----------
    Questi controlli non sono cosmetici: servono a verificare che la lettura non abbia
    perso righe, che la conversione numerica non abbia generato NaN silenziosi e a
    misurare *quanto* pesano le semplificazioni adottate (granularita' non PT15,
    offerte a blocchi trattate come indipendenti). I numeri finiscono nel diario
    metodologico e, in tesi, nella sezione sui dati.
    """
    out: dict[str, pd.DataFrame | pd.Series] = {}

    out["per_granularita"] = (
        df.groupby(["GRANULARITY", "PURPOSE_CD"], dropna=False)
        .size()
        .unstack(fill_value=0)
    )
    out["per_status"] = (
        df.groupby(["STATUS_CD", "PURPOSE_CD"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .sort_values(by=list(df["PURPOSE_CD"].dropna().unique())[:1], ascending=False)
    )

    pt15 = df[df["GRANULARITY"] == "PT15"]
    per_periodo = pd.DataFrame({
        "righe": pt15.groupby("PERIOD").size(),
        "righe_BID": pt15[pt15["PURPOSE_CD"] == config.PURPOSE_ACQUISTO].groupby("PERIOD").size(),
        "righe_OFF": pt15[pt15["PURPOSE_CD"] == config.PURPOSE_VENDITA].groupby("PERIOD").size(),
        "MW_domanda": pt15[pt15["PURPOSE_CD"] == config.PURPOSE_ACQUISTO]
            .groupby("PERIOD")["QUANTITY_NO"].sum(),
        "MW_offerta": pt15[pt15["PURPOSE_CD"] == config.PURPOSE_VENDITA]
            .groupby("PERIOD")["QUANTITY_NO"].sum(),
    }).fillna(0)
    out["per_periodo"] = per_periodo

    num = [c for c in config.COLONNE_NUMERICHE if c in df.columns]
    desc = df[num].describe().T
    desc["n_NaN"] = df[num].isna().sum()
    desc["dtype"] = [str(df[c].dtype) for c in num]
    out["numeriche"] = desc

    mw_tot = df["QUANTITY_NO"].sum()
    mw_pt15 = pt15["QUANTITY_NO"].sum()
    qualita = pd.Series({
        "righe_totali": len(df),
        "righe_PT15": len(pt15),
        "quota_righe_non_PT15_%": round(100 * (1 - len(pt15) / len(df)), 3) if len(df) else 0.0,
        "MW_totali": round(mw_tot, 1),
        "MW_PT15": round(mw_pt15, 1),
        "quota_MW_non_PT15_%": round(100 * (1 - mw_pt15 / mw_tot), 3) if mw_tot else 0.0,
        "offerte_a_blocchi": int((df.get("OFFER_TYPE", pd.Series(dtype=object)) == "B").sum()),
        "BLOCK_ID_valorizzati": int(df.get("BLOCK_ID", pd.Series(dtype=object)).fillna("").ne("").sum()),
        "bilaterali": int(df.get("BILATERAL_IN", pd.Series(dtype=object)).astype(str).str.lower().eq("true").sum()),
        # Price taker: acquisti al prezzo massimo e vendite al prezzo minimo accettano
        # qualunque prezzo di mercato. Le vendite offerte a 0 (bilaterali, must-run) sono
        # price taker "di fatto" ma non al limite: contate a parte.
        "price_taker_acquisto_a_Pmax": int(
            ((df["PURPOSE_CD"] == config.PURPOSE_ACQUISTO)
             & (df["ENERGY_PRICE_NO"] >= config.PREZZO_MASSIMO)).sum()
        ),
        "price_taker_vendita_a_Pmin": int(
            ((df["PURPOSE_CD"] == config.PURPOSE_VENDITA)
             & (df["ENERGY_PRICE_NO"] <= config.PREZZO_MINIMO)).sum()
        ),
        "vendite_a_prezzo_zero": int(
            ((df["PURPOSE_CD"] == config.PURPOSE_VENDITA)
             & (df["ENERGY_PRICE_NO"] == 0.0)).sum()
        ),
        "MW_bilaterali": round(
            df.loc[df.get("BILATERAL_IN", pd.Series(dtype=object)).astype(str).str.lower().eq("true"),
                   "QUANTITY_NO"].sum(), 1),
        "prezzo_min": df["ENERGY_PRICE_NO"].min(),
        "prezzo_max": df["ENERGY_PRICE_NO"].max(),
    })
    out["qualita"] = qualita

    return out


def prezzi_ufficiali(df: pd.DataFrame, granularita: str = "PT15") -> pd.DataFrame:
    """
    Estrae il prezzo zonale ufficiale per periodo dal campo `AWARDED_PRICE_NO`.

    Parameters
    ----------
    df : pd.DataFrame
        Offerte di una singola zona.
    granularita : str
        Granularita' dei periodi da considerare (default 'PT15').

    Returns
    -------
    pd.DataFrame
        Colonne: `PERIOD`, `prezzo_ufficiale` (€/MWh), `n_valori_distinti`, `n_righe_ACC`.

    Perche' funziona
    ----------------
    Il MGP e' un'asta a prezzo uniforme: tutte le offerte accettate in una zona e in un
    periodo sono remunerate allo stesso prezzo zonale. Di conseguenza, sulle righe con
    `STATUS_CD`='ACC' il campo `AWARDED_PRICE_NO` e' costante entro (zona, periodo) e
    coincide con il prezzo zonale pubblicato da GME. Verificato sul file pilota: NORD,
    periodo PT15 40 -> 177,87 €/MWh; periodo 76 -> 180,20 €/MWh.

    Questo evita di dover scaricare e allineare i file `MGP_Prezzi`: il benchmark contro
    cui misurare il prezzo ricostruito dal nostro algoritmo di clearing e' gia' dentro
    lo stesso file. La colonna `n_valori_distinti` e' il controllo dell'assunzione: deve
    valere 1 per ogni periodo.
    """
    acc = df[(df["STATUS_CD"] == "ACC") & (df["GRANULARITY"] == granularita)]
    g = acc.groupby("PERIOD")["AWARDED_PRICE_NO"]
    fuori = (
        pd.DataFrame({
            "prezzo_ufficiale": g.median(),
            "n_valori_distinti": g.nunique(),
            "n_righe_ACC": g.size(),
        })
        .reset_index()
        .sort_values("PERIOD")
    )
    return fuori
