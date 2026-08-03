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
| D-03 | Ogni offerta trattata come **indipendente**: le offerte a blocchi non sono vincolate | adottata | 2026-08-03 | Basso: 0,8% delle righe nel giorno pilota |
| D-04 | Conversione decimale **difensiva** (accetta punto e virgola) | adottata | 2026-08-03 | Nullo: nell'XML il separatore è il punto |
| D-05 | Analisi ristretta alla granularità **PT15** | superata da D-12 | 2026-08-03 | Valida solo per i giorni dal 01/10/2025 |
| D-06 | Le curve d'asta si costruiscono con le offerte **`ACC` + `REJ`** (più `PREJ`, da testare) | adottata | 2026-08-03 | Molto alto: cambia il prezzo ricostruito di un ordine di grandezza |
| D-07 | `AWARDED_PRICE_NO` sulle righe `ACC` usato come **prezzo zonale ufficiale** di riferimento | adottata | 2026-08-03 | Nullo sui risultati; fornisce il benchmark di validazione |
| D-08 | Lettura XML in **streaming** con cache Parquet invece di `pandas.read_xml` | adottata | 2026-08-03 | Nullo sui risultati; scelta tecnica (memoria e tempi) |
| D-09 | La misura di bontà della ricostruzione è la **frequenza di match** con il prezzo ufficiale | adottata | 2026-08-03 | Definisce il criterio di validazione dell'intera pipeline |
| D-10 | Perimetro zonale: **NORD più le zone virtuali di frontiera confinanti**, senza vincoli di capacità di transito | adottata | 2026-08-03 | Alto: recupera la parte a basso costo della curva di offerta (import) |
| D-11 | Periodo di studio: **gennaio 2025** per la validazione, poi estensione a **tutto il 2025** | adottata, con riserva | 2026-08-03 | Definisce il campione; vedi la questione aperta sulla granularità |
| D-12 | Si usa la **granularità nativa prevalente di ciascun giorno** (PT60 fino al 30/09/2025, PT15 dal 01/10/2025); le righe di granularità minoritaria restano escluse e quantificate | adottata | 2026-08-03 | Sostituisce D-05: nel 2025 nove mesi su dodici sono orari |
| D-13 | Confronto sistematico fra "sola granularità prevalente" e "prevalente + minoritaria riscalata", scelta in base alla frequenza di match | aperta | — | Da misurare: sul giorno pilota sposta il prezzo da 400 a 319 €/MWh |
