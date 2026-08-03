# Registro delle decisioni metodologiche

Indice sintetico delle scelte che influenzano i risultati. Ogni voce ha un identificativo
stabile (D-xx) citabile dal codice, dal diario e dai capitoli della tesi. La discussione
estesa (contesto, alternative, evidenze) sta in [DIARIO.md](DIARIO.md), alla data indicata.

Stato: **adottata** = in uso nella pipeline · **aperta** = da decidere/validare ·
**superata** = sostituita da una decisione successiva.

| ID | Decisione | Stato | Dal | Impatto atteso |
|----|-----------|-------|-----|----------------|
| D-01 | Zona NORD modellata come **isolata**: nessun vincolo di transito, nessun import/export dalle zone confinanti | adottata | 2026-08-03 | Alto: il prezzo ricostruito sovrastima quello ufficiale nelle ore in cui NORD importa |
| D-02 | Filtro dei dati **a due livelli**: prima `ZONE_CD`, poi un singolo `PERIOD` alla volta | adottata | 2026-08-03 | Nullo sui risultati; organizza il codice e la memoria |
| D-03 | Ogni offerta trattata come **indipendente**: le offerte a blocchi non sono vincolate | adottata | 2026-08-03 | Basso: 0,8% delle righe nel giorno pilota |
| D-04 | Conversione decimale **difensiva** (accetta punto e virgola) | adottata | 2026-08-03 | Nullo: nell'XML il separatore è il punto |
| D-05 | Analisi ristretta alla granularità **PT15**; PT60/PT30 esclusi ma quantificati | adottata | 2026-08-03 | Da misurare: nel giorno pilota il 4,2% delle righe NORD non è PT15 |
| D-06 | Quali `STATUS_CD` entrano nelle curve di domanda/offerta | **aperta** | — | Molto alto: il prezzo ricostruito cambia di centinaia di €/MWh |
| D-07 | `AWARDED_PRICE_NO` sulle righe `ACC` usato come **prezzo zonale ufficiale** di riferimento | adottata | 2026-08-03 | Nullo sui risultati; fornisce il benchmark di validazione |
| D-08 | Lettura XML in **streaming** con cache Parquet invece di `pandas.read_xml` | adottata | 2026-08-03 | Nullo sui risultati; scelta tecnica (memoria e tempi) |
| D-09 | La misura di bontà della ricostruzione è la **frequenza di match** con il prezzo ufficiale | adottata | 2026-08-03 | Definisce il criterio di validazione dell'intera pipeline |
