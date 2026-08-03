# Glossario dei dati GME — MGP OffertePubbliche

Dizionario dei campi dei file XML delle offerte pubbliche del Mercato del Giorno Prima,
ricostruito ispezionando direttamente i file (31/03/2026 e 13/02/2015) e la `Legend.txt`
distribuita da GME nell'archivio. Dove il significato è dedotto e non confermato da
documentazione ufficiale, è segnalato con **(da confermare)**.

## Struttura del file

```xml
<NewDataSet>
  <xs:schema .../>                <!-- schema XSD inline: va saltato in lettura -->
  <OfferteOperatori>              <!-- una per offerta: coppia (prezzo, quantità) -->
    <PURPOSE_CD>BID</PURPOSE_CD>
    ...
  </OfferteOperatori>
  ...
</NewDataSet>
```

Un file = un giorno di mercato = tutte le zone e tutti i periodi.
Giorno pilota (31/03/2026): 568.185 elementi `OfferteOperatori`, 574 MB.

## Campi

| Campo | Tipo | Significato | Note |
|---|---|---|---|
| `PURPOSE_CD` | str | Finalità dell'offerta | `BID` = acquisto (→ curva di domanda), `OFF` = vendita (→ curva di offerta) |
| `TYPE_CD` | str | Tipo di offerta | `REG` = regolare; `STND` = standard, usata sulle frontiere estere |
| `STATUS_CD` | str | Esito dell'offerta | vedi tabella sotto |
| `MARKET_CD` | str | Mercato | sempre `MGP` in questi file |
| `UNIT_REFERENCE_NO` | str | Unità di produzione/consumo che presenta l'offerta | es. `UC_0000002_01` |
| `MARKET_PARTECIPANT_XREF_NO` | str | Identificativo dell'operatore | quasi sempre vuoto nei file pubblici |
| `INTERVAL_NO` | int | Ora del giorno (1-24) | **solo schema storico** (2015); normalizzato in `PERIOD` |
| `BID_OFFER_DATE_DT` | int | Giorno di competenza | formato `YYYYMMDD` |
| `TRANSACTION_REFERENCE_NO` | str | Identificativo univoco della transazione | |
| `BALANCED_REFERENCE_NO` | str | Riferimento per offerte bilanciate | quasi sempre vuoto |
| `QUANTITY_NO` | float | **Quantità offerta**, MWh | riferita al periodo indicato da `PERIOD`+`GRANULARITY` |
| `AWARDED_QUANTITY_NO` | float | Quantità effettivamente assegnata, MWh | 0 se l'offerta non è accettata |
| `ENERGY_PRICE_NO` | float | **Prezzo offerto**, €/MWh | separatore decimale: punto; range osservato **-500 … 4000** (prezzi negativi ammessi) |
| `MERIT_ORDER_NO` | float | Posizione nell'ordine di merito | |
| `PARTIAL_QTY_ACCEPTED_IN` | str | Ammessa accettazione parziale | `Y`/`N` (nel giorno pilota, NORD: 554 `Y` su 137.039) |
| `ADJ_QUANTITY_NO` | float | Quantità rettificata | |
| `ADJ_ENERGY_PRICE_NO` | float | Prezzo rettificato | presente nello schema, assente dai record ispezionati |
| `GRID_SUPPLY_POINT_NO` | str | Punto di prelievo/immissione sulla rete | es. `NORD`, `PSR_CNOR` |
| `ZONE_CD` | str | **Zona di mercato** | vedi elenco sotto |
| `AWARDED_PRICE_NO` | float | Prezzo di assegnazione, €/MWh | sulle righe `ACC` = **prezzo zonale ufficiale** (D-07) |
| `OPERATORE` | str | Ragione sociale | `Bilateralista` per i contratti bilaterali |
| `SUBMITTED_DT` | str | Istante di presentazione | `YYYYMMDDhhmmssmmm` |
| `BILATERAL_IN` | bool | L'offerta registra un contratto bilaterale | i bilaterali entrano a prezzo 0 (price taker) |
| `OFFER_TYPE` | str | `S` = semplice, `B` = a blocchi | **solo schema recente** |
| `BLOCK_ID` | str | Identificativo del blocco | valorizzato **solo** sulle righe `OFFER_TYPE='B'` |
| `PERIOD` | int | **Periodo del giorno** | 1-96 con PT15, 1-48 con PT30, 1-24 con PT60 |
| `GRANULARITY` | str | Granularità temporale | `PT15` / `PT30` / `PT60`; **solo schema recente** |
| `MINIMUM_ACCEPTANCE_RATIO` | str | Quota minima di accettazione | presente nello schema, assente dai record ispezionati |

## `STATUS_CD` — esiti (lettura **da confermare** su documentazione GME)

| Codice | Lettura | Righe (31/03/2026, tutte le zone) |
|---|---|---|
| `ACC` | Accettata | 240.008 |
| `REP` | Sostituita da una presentazione successiva dello stesso operatore | 217.558 |
| `REV` | Revocata | 58.279 |
| `REJ` | Respinta: offerta valida in gara ma fuori mercato | 50.200 |
| `INC` | Incongruente | 2.120 |
| `PREJ` | Respinta in fase preliminare | 20 |

La scelta di quali stati entrino nelle curve è la decisione aperta **D-06**
([decisioni.md](decisioni.md)): incide sul prezzo ricostruito di un ordine di grandezza.

## Zone (`ZONE_CD`) nel giorno pilota

**Zone fisiche italiane**: `NORD` (137.039 righe), `CNOR`, `CSUD`, `SUD`, `CALA`, `SICI`, `SARD`.

**Zone virtuali di frontiera / estere**: `SVIZ` (3.357), `MONT` (979), `CORS` (864),
`COAC` (864), `FRAN` (96), `MALT` (28). Qui si registrano import ed export: sono la ragione
per cui una zona modellata come isolata (D-01) perde la parte a basso costo della curva di
offerta quando è importatrice.

## Differenze di schema fra annate

| | file 2015 | file 2026 |
|---|---|---|
| Periodo | `INTERVAL_NO` (1-24) | `PERIOD` + `GRANULARITY` |
| Granularità | assente (oraria) | `PT15` / `PT30` / `PT60` |
| Offerte a blocchi | nessun campo | `OFFER_TYPE`, `BLOCK_ID` |
| Bilaterali | `BILATERAL_IN=true`, `OPERATORE='Bilateralista'` | presenti |
| Separatore decimale | punto | punto |

`mgp.io_gme` normalizza lo schema storico su quello recente (`INTERVAL_NO` → `PERIOD`,
`GRANULARITY` → `PT60`). **Da mappare**: la data esatta in cui l'archivio passa alla
granularità a quarto d'ora.

## Altri dataset GME potenzialmente utili

Dalla `Legend.txt` dell'archivio, per estensioni future:

* `MGP_Prezzi` / `MGP_Prezzi15` — prezzi zonali ufficiali (non necessari: vedi D-07);
* `MGP_LimitiTransito` — limiti di transito fra zone (servirebbero per superare D-01);
* `MGP_Transiti` — transiti effettivi fra zone;
* `MGP_Fabbisogno` / `MGP_StimeFabbisogno` — domanda e domanda prevista;
* `MGP_Quantita`, `MGP_Liquidita`, `MGP_MarketCoupling`.

L'archivio locale contiene già alcuni file `MGPFabbisogno` e `MGPStimeFabbisogno` sciolti
accanto agli zip delle offerte.
