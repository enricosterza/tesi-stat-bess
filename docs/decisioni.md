# Registro delle decisioni metodologiche

Indice sintetico delle scelte che influenzano i risultati. Ogni voce ha un identificativo
stabile (D-xx) citabile dal codice, dal diario e dai capitoli della tesi. La discussione
estesa (contesto, alternative, evidenze) sta in [DIARIO.md](DIARIO.md), alla data indicata.

Stato: **adottata** = in uso nella pipeline · **aperta** = da decidere/validare ·
**superata** = sostituita da una decisione successiva.

| ID | Decisione | Stato | Dal | Impatto atteso |
|----|-----------|-------|-----|----------------|
| D-01 | Zona NORD modellata come **isolata**: nessun import dalle zone confinanti | superata da D-10 | 2026-08-03 | Alto: prezzo ricostruito sistematicamente sopra l'ufficiale |
| D-02 | Filtro dei dati **a due livelli**: prima `ZONE_CD`, poi un singolo `PERIOD` alla volta | adottata | 2026-08-03 | Nullo sui risultati; organizza il codice e la memoria |
| D-03 | Ogni offerta trattata come **indipendente**: le offerte a blocchi non sono vincolate | adottata, ma **impatto rivalutato** il 04/08 | 2026-08-03 | **Alto sulle aste a quarto d'ora**: i blocchi sono il 2,8% delle offerte ma spostano ~880 MW per asta (5% del volume) e causano il 99,2% delle incoerenze. Trattarli correttamente dimezzerebbe la dispersione dello scarto (9,11 → 5,09). Sulle aste orarie resta basso (0,54% delle offerte) |
| D-04 | Conversione decimale **difensiva** (accetta punto e virgola) | adottata | 2026-08-03 | Nullo: nell'XML il separatore è il punto |
| D-05 | Analisi ristretta alla granularità **PT15** | superata da D-12 | 2026-08-03 | Valida solo per i giorni dal 01/10/2025 |
| D-06 | Le curve d'asta si costruiscono con le offerte **`ACC` + `REJ`** (più `PREJ`, da testare) | adottata | 2026-08-03 | Molto alto: cambia il prezzo ricostruito di un ordine di grandezza |
| D-07 | `AWARDED_PRICE_NO` sulle righe `ACC` usato come **prezzo zonale ufficiale** di riferimento | adottata | 2026-08-03 | Nullo sui risultati; fornisce il benchmark di validazione |
| D-08 | Lettura XML in **streaming** con cache Parquet invece di `pandas.read_xml` | adottata | 2026-08-03 | Nullo sui risultati; scelta tecnica (memoria e tempi) |
| D-09 | La misura di bontà della ricostruzione è la **frequenza di match** con il prezzo ufficiale | adottata | 2026-08-03 | Definisce il criterio di validazione dell'intera pipeline |
| D-10 | Perimetro zonale: **NORD più le zone virtuali di frontiera confinanti**, senza vincoli di capacità di transito | adottata | 2026-08-03 | Alto: recupera la parte a basso costo della curva di offerta (import) |
| D-11 | Periodo di studio: **gennaio 2025** per la validazione, poi estensione a **tutto il 2025** | adottata, con riserva | 2026-08-03 | Definisce il campione; vedi la questione aperta sulla granularità |
| D-12 | Si usa la **granularità nativa prevalente di ciascun giorno** (PT60 fino al 30/09/2025, PT15 dal 01/10/2025); le righe di granularità minoritaria restano escluse e quantificate | adottata | 2026-08-03 | Sostituisce D-05: nel 2025 nove mesi su dodici sono orari |
| D-13 | Nelle curve entrano le offerte di **tutte le granularità**, senza riscalare le quantità (sono potenze, non energie di periodo) | adottata | 2026-08-03 | Alto: errore mediano da 100,79 a 24,57 €/MWh sul giorno pilota |
| D-16 | Lo **scambio netto** del perimetro entra come blocco price taker, **simmetrico**: l'import come offerta al prezzo minimo, l'export come acquisto al prezzo massimo. È calibrato sulle quantità assegnate osservate | adottata (riformulata il 04/08) | 2026-08-03 | Decisivo: errore mediano da 24,57 a 5,25 €/MWh (giorno a 15 min) e a 0,05 (giorno orario); la simmetria porta lo scarto massimo di gennaio 2025 da 85 a 15,88 €/MWh |
| D-17 | La validazione si fa su **un mese intero**, analizzando l'errore per giorno, per ora del giorno e per presenza di congestione | adottata | 2026-08-04 | Definisce il protocollo: una giornata singola non dice se il modello è affidabile |
| D-18 | Clearing **consapevole dei blocchi**: euristica iterativa a livello di giornata, con rivalutazione di ciascun blocco sul prezzo medio ponderato dei periodi che copre | adottata | 2026-08-04 | Aste orarie: raggiunge il limite dell'oracolo (errore mediano 0,08 contro 0,07). Aste a quarto d'ora: recupero parziale (8,81 → 8,36 di dev. standard contro 5,15 ottenibile), perché l'euristica oscilla in 4 giornate su 7 |
| D-19 | Gestione dell'oscillazione dell'euristica: scegliere fra le configurazioni visitate con un criterio esplicito invece di fermarsi all'ultima | aperta | — | È ciò che separa il risultato attuale dal limite ottenibile sulle aste a quarto d'ora |
| D-14 | Doppio campione: analisi principale sull'anno 2025 riportata su base oraria, più analisi di confronto sui 182 giorni a quarto d'ora (01/10/2025-31/03/2026) | adottata | 2026-08-03 | L'effetto della risoluzione temporale sul valore dell'arbitraggio diventa un risultato, non un limite |
| D-15 | La funzione di clearing è **indipendente dalla granularità**: opera su un insieme di offerte già filtrato per zona e periodo | adottata | 2026-08-03 | Permette PT15, PT30 e PT60 con lo stesso codice e senza rami condizionali |

**Attenzione:** le decisioni D-06, D-10, D-11, D-12, D-14 sono state prese in autonomia per
non fermare il lavoro e **non sono ancora state discusse con il relatore**. In particolare i
significati dei codici `STATUS_CD` non sono documentati esplicitamente da GME.
