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
| `QUANTITY_NO` | float | **Quantità offerta**, **MW** (potenza) | vedi la nota sulle unità in fondo: **non** è l'energia del periodo |
| `AWARDED_QUANTITY_NO` | float | Quantità effettivamente assegnata, **MW** | 0 se l'offerta non è accettata |
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

## `STATUS_CD` — esiti (significati adottati il 03/08/2026, **da confermare con il relatore**)

| Codice | Significato | In gara? | Righe (31/03/2026, tutte le zone) |
|---|---|---|---|
| `ACC` | Accettata | sì | 240.008 |
| `REJ` | Rifiutata | sì | 50.200 |
| `PREJ` | **Paradossalmente rifiutata**: offerta a blocchi in merito sul prezzo ma rifiutata per il vincolo "tutto o niente" | sì | 20 |
| `REP` | Sostituita da una presentazione successiva dello stesso operatore | no | 217.558 |
| `REV` | Revocata dall'operatore | no | 58.279 |
| `INC` | Incongrua (offerta non valida) | no | 2.120 |

La colonna "in gara" riporta la conseguenza operativa: le curve d'asta si costruiscono con
`ACC` + `REJ` (+ `PREJ`, marginale), perché sono le offerte che hanno effettivamente
partecipato all'asta. `REP` conterebbe due volte la stessa offerta, `REV` offerte ritirate,
`INC` offerte scartate a monte. Vedi decisione **D-06** in [decisioni.md](decisioni.md).

Nota su `PREJ`: il "rifiuto paradossale" è un fenomeno proprio delle offerte a blocchi, che
sono accettabili solo per intero e su tutti i periodi del blocco. Un'offerta può quindi
risultare in merito sul prezzo e venire comunque rifiutata perché accettarla renderebbe
inconsistente la soluzione d'asta. È la stessa ragione per cui trattare i blocchi come
offerte semplici (D-03) è un'approssimazione: nel nostro modello un blocco può essere
accettato parzialmente.

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
`GRANULARITY` → `PT60`).

## Unità delle quantità: sono potenze, non energie

`QUANTITY_NO` e `AWARDED_QUANTITY_NO` sono espresse in **MW** (equivalentemente MWh/h) e
**non** rappresentano l'energia del periodo di riferimento.

Verifica: sommando le quantità assegnate a livello nazionale si ottengono 37.149 in un
quarto d'ora del 31/03/2026. Se fosse energia sarebbero 148 GW di potenza, circa quattro
volte il fabbisogno italiano. Il confronto fra un giorno orario e uno a quarto d'ora lo
conferma: 38.334 in media all'ora il 15/01/2025 contro 31.956 in media al quarto d'ora il
31/03/2026, **rapporto 0,83** anziché 0,25 (la differenza residua è la stagionalità del
fabbisogno, gennaio contro marzo).

Conseguenze operative:

* un'offerta oraria di X MW vale X MW in **ciascuno** dei quarti d'ora che compongono
  l'ora: non va divisa per quattro quando si mescolano le granularità;
* l'energia si ottiene moltiplicando per la durata del periodo (`config.in_energia`), e
  serve solo dove conta davvero, cioè nel bilancio di carica e scarica della batteria.

## Quando l'archivio passa al quarto d'ora

Verificato scandendo i file giorno per giorno intorno al cambio: **il 30/09/2025 le offerte
sono al 100% `PT60`, il 01/10/2025 sono per l'82,8% `PT15`**. Il passaggio al periodo di
mercato da 15 minuti è quindi netto e cade il **1° ottobre 2025**. Da quella data in poi
resta una quota residua di offerte orarie (4-5% nei mesi successivi, 17% nel primo giorno).

Copertura dell'archivio locale: dal 13/02/2015 al 31/03/2026, 4.065 giorni; il 2025 è
completo (365 giorni su 365), del 2026 ci sono i primi 90 giorni. I giorni a granularità
nativa PT15 disponibili sono quindi **182**, dal 01/10/2025 al 31/03/2026.

## Altri dataset GME potenzialmente utili

Dalla `Legend.txt` dell'archivio, per estensioni future:

* `MGP_Prezzi` / `MGP_Prezzi15` — prezzi zonali ufficiali (non necessari: vedi D-07);
* `MGP_LimitiTransito` — limiti di transito fra zone (servirebbero per superare D-01);
* `MGP_Transiti` — transiti effettivi fra zone;
* `MGP_Fabbisogno` / `MGP_StimeFabbisogno` — domanda e domanda prevista;
* `MGP_Quantita`, `MGP_Liquidita`, `MGP_MarketCoupling`.

L'archivio locale contiene già alcuni file `MGPFabbisogno` e `MGPStimeFabbisogno` sciolti
accanto agli zip delle offerte.
