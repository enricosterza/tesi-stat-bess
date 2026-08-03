# Diario metodologico

Registro datato del lavoro di tesi: **cosa** è stato fatto, **perché**, con quali
**assunzioni**, quali **alternative** sono state scartate e cosa è stato **osservato o
validato**. È un file append-only: le voci vecchie non si riscrivono, semmai si aggiunge
una voce nuova che le supera (citando l'ID della decisione).

Tema della tesi: effetto dell'introduzione di capacità di accumulo (batterie che fanno
arbitraggio infra-giornaliero) sul Mercato del Giorno Prima italiano, zona NORD.

---

## 2026-08-03 — Impostazione del progetto

### Cosa è stato fatto
Predisposta la struttura del progetto (`src/mgp` come pacchetto, `scripts/` per le
elaborazioni, `docs/` per la documentazione metodologica, `data/` e `output/` per dati
derivati e risultati), creato un virtual environment Python 3.10 dedicato con le librerie
necessarie, predisposto il versionamento git e scritti i primi due moduli
(`mgp.config`, `mgp.io_gme`) più lo script `scripts/01_carica_ed_esplora.py`.

### Perché questa struttura
La separazione fra **moduli riutilizzabili** (`src/mgp`) e **script eseguibili**
(`scripts/`) serve a un obiettivo concreto della tesi: la funzione che ricostruisce le
curve e il prezzo di equilibrio dovrà essere richiamata migliaia di volte (96 periodi ×
molti giorni × molti scenari di capacità di accumulo). Se vivesse dentro uno script
lineare non sarebbe né testabile né riutilizzabile. I dati grezzi non sono stati spostati
dentro il progetto: sono ~6 GB su una cartella OneDrive e copiarli avrebbe solo duplicato
peso e tempi di sincronizzazione; i percorsi stanno tutti in `mgp/config.py`.

### Note di ambiente
`pip` falliva con `CERTIFICATE_VERIFY_FAILED`: l'antivirus Avast intercetta il traffico
TLS e presenta certificati firmati da una propria CA locale. Risolto indicando a pip il
bundle CA di Avast (`.venv/pip.ini` → `cert = C:\ProgramData\Avast Software\Avast\wscert.pem`)
**senza** disattivare la verifica dei certificati. Se in futuro pip tornasse a fallire dopo
un aggiornamento di Avast, è il primo posto da controllare.

**Git non è installato sul sistema**, quindi il repository non è ancora stato creato:
`.gitignore` è pronto (esclude i dati grezzi, la cache, gli output e il virtual
environment) e appena Git sarà disponibile basteranno `git init` + primo commit. Per una
tesi il versionamento non è un vezzo: permette di tornare a una versione precedente di una
scelta metodologica dopo averne provata un'altra.

---

## 2026-08-03 — Ispezione dei dati grezzi e correzione di alcune assunzioni iniziali

### Cosa è stato fatto
Ispezione diretta del file pilota `20260331MGPOffertePubbliche.xml` (574 MB, 568.185
offerte, tutte le zone) e di un file dell'archivio storico (13/02/2015), con conteggi
esaustivi sui campi categoriali.

### Cosa è stato osservato

**Struttura.** Il documento è un `NewDataSet` con uno schema XSD inline seguito da una
sequenza di elementi `OfferteOperatori`, uno per offerta (una coppia prezzo-quantità per
operatore, zona e periodo).

**Nomi dei campi.** Portano il suffisso `_NO`: `ENERGY_PRICE_NO`, `QUANTITY_NO`,
`AWARDED_QUANTITY_NO`, `MERIT_ORDER_NO`, `AWARDED_PRICE_NO`, `PARTIAL_QTY_ACCEPTED_IN`.

**`PURPOSE_CD`.** Due soli valori: `BID` (acquisto, 265.078 righe) e **`OFF`** (vendita,
303.107). Il codice della vendita, che era da verificare, è quindi `OFF`.

**Composizione per zona** (giorno pilota, tutte le righe): NORD 137.039, SUD 106.948,
CSUD 98.237, SICI 69.066, CNOR 57.363, SARD 47.324, CALA 46.020, e le zone "virtuali" di
frontiera SVIZ 3.357, MONT 979, CORS 864, COAC 864, FRAN 96, MALT 28.

**Zona NORD**: 137.039 offerte, di cui per granularità e finalità

| | BID (acquisto) | OFF (vendita) | totale |
|---|---|---|---|
| PT15 | 51.782 | 79.495 | **131.277** |
| PT60 | 2.691 | 2.775 | **5.466** |
| PT30 | 0 | 296 | **296** |

e per stato: `ACC` 60.714, `REP` 49.667, `REJ` 12.600, `REV` 13.559, `INC` 479, `PREJ` 20
(valori sull'intero file: ACC 240.008, REP 217.558, REV 58.279, REJ 50.200, INC 2.120,
PREJ 20).

### Assunzioni iniziali che sono risultate da correggere

1. **Il separatore decimale non è la virgola, è il punto.** Nell'XML i valori sono scritti
   `146.800`, `1100.00`, `149.45`; lo stesso vale nel file 2015 (`2.256`, `50.82`). La
   virgola compare negli export Excel/CSV di GME, non nell'XML. La conversione implementata
   resta comunque difensiva su entrambi i separatori → **D-04**.
2. **`STATUS_CD` non ha due valori ma sei**: `ACC`, `REP`, `REJ`, `REV`, `INC`, `PREJ`.
   Non è un dettaglio: cambia radicalmente quali offerte entrano nelle curve → **D-06**.
3. **La granularità è mista anche nei dati recenti**: nel giorno pilota, zona NORD,
   convivono PT15 (96 periodi), PT60 (24 periodi) e PT30 (48 periodi). `PERIOD` non è
   quindi interpretabile da solo: va sempre letto insieme a `GRANULARITY`, altrimenti
   filtrando `PERIOD == 10` si mescolano il decimo quarto d'ora e la decima ora → **D-05**.
4. **Le offerte a blocchi esistono e sono identificabili**: `OFFER_TYPE` vale `S`
   (semplice, 563.606) o `B` (a blocchi, 4.579), e i 4.579 `BLOCK_ID` valorizzati
   coincidono esattamente con le righe `B`. Quindi `BLOCK_ID` non è "quasi sempre vuoto"
   per caso: è vuoto per costruzione sulle offerte semplici → **D-03**.
5. **L'archivio storico ha uno schema diverso.** I file 2015 usano `INTERVAL_NO` (ora
   1-24) e non hanno `PERIOD`, `GRANULARITY`, `OFFER_TYPE`, `BLOCK_ID`. Hanno invece
   `BILATERAL_IN = true` con `OPERATORE = "Bilateralista"`: i contratti bilaterali sono
   registrati come offerte a prezzo 0, cioè come quantità *price taker*. Il lettore
   normalizza lo schema storico su quello recente. Resta da mappare, quando si estenderà
   l'analisi a più anni, **in che data** avviene il passaggio a PT15 e se e quando compaia
   la virgola come separatore.

### Scoperta utile: il benchmark di validazione è già dentro il file
Il MGP è un'asta a **prezzo uniforme**: tutte le offerte accettate in una zona e in un
periodo sono remunerate allo stesso prezzo. Coerentemente, sulle righe con `STATUS_CD='ACC'`
il campo `AWARDED_PRICE_NO` è costante entro (zona, periodo) e coincide con il prezzo
zonale ufficiale. Verificato: NORD, periodo PT15 40 → 177,87 €/MWh su 661 righe accettate;
periodo 76 → 180,20 €/MWh su 684 righe. Non serve quindi scaricare e allineare i file
`MGP_Prezzi`: il confronto fra prezzo ricostruito e prezzo ufficiale si può fare sullo
stesso dataset → **D-07**, e la frequenza di match diventa la misura di bontà della
ricostruzione → **D-09**.

---

## 2026-08-03 — D-01 · Zona NORD modellata come isolata

### Decisione
La zona NORD viene modellata come un mercato a sé stante: si ricostruiscono domanda e
offerta usando le sole offerte con `ZONE_CD = 'NORD'`, ignorando i limiti di transito con
le zone confinanti e gli scambi con l'estero.

### Perché
È la semplificazione minima che rende trattabile il problema: il vero algoritmo di GME
risolve un problema di ottimizzazione zonale con vincoli di transito su tutte le zone
simultaneamente, e replicarlo esattamente non è l'obiettivo della tesi. L'oggetto di studio
è l'**effetto marginale** dell'accumulo sul prezzo, cioè una differenza fra due scenari
(con e senza batteria) calcolata sulla stessa curva: buona parte dell'errore di livello si
compensa nella differenza.

### Cosa comporta (limite noto, misurato)
Il prezzo ricostruito su NORD isolata risulta **sistematicamente più alto** di quello
ufficiale. Test preliminare sul periodo PT15 40 (prezzo ufficiale 177,87 €/MWh), con
diverse selezioni di stato:

| selezione di `STATUS_CD` | offerte usate | prezzo ricostruito |
|---|---|---|
| solo `ACC` | 661 | nessuna intersezione |
| `ACC` + `REJ` | 755 | 400,00 |
| `ACC` + `REJ` + `REP` | 1.299 | 2.000,00 |
| tutti gli stati | 1.445 | 853,00 |
| `ACC` + `REJ`, con PT60 riscalato su 15 min | 911 | 319,00 |

Stesso quadro sul periodo 76 (ufficiale 180,20; `ACC`+`REJ` → 319,00). La lettura economica
è coerente: NORD è strutturalmente **importatrice**, e l'energia importata non compare fra
le offerte con `ZONE_CD='NORD'` ma nelle zone virtuali di frontiera (`SVIZ`, `FRAN`, `MONT`,
…). Togliendo l'import si toglie la parte a basso costo della curva di offerta, e il prezzo
di equilibrio sale.

### Alternative considerate e non adottate (per ora)
* **Modello multi-zonale con vincoli di transito**: fedele ma sproporzionato rispetto
  all'obiettivo; richiederebbe i file `MGP_LimitiTransito` e un solutore di flusso.
* **Aggiunta delle sole zone estere confinanti con NORD** (`SVIZ`, `FRAN`, …) come offerte
  addizionali senza vincolo di capacità: molto più economico e probabilmente sufficiente a
  ridurre gran parte del bias. **Da testare** appena la funzione di clearing sarà pronta:
  è la prima estensione da provare se la frequenza di match risultasse troppo bassa.

### Da fare
Misurare il bias su tutti i 96 periodi (media, mediana, distribuzione per fascia oraria) e
verificare se sia costante: se lo fosse, l'effetto marginale della batteria resterebbe
attendibile anche con il livello sbagliato.

---

## 2026-08-03 — D-02 · Filtro a due livelli (zona → periodo)

Le curve di domanda e offerta esistono solo **entro una zona e un periodo**: il MGP è una
sequenza di aste indipendenti. Il filtro è quindi prima su `ZONE_CD` (applicato già durante
il parsing dell'XML: delle 568.185 offerte se ne materializzano 137.039) e poi su un singolo
`PERIOD`, che è l'unità su cui opera la funzione di clearing. Attenzione: `PERIOD` va sempre
filtrato **insieme** a `GRANULARITY` (vedi D-05).

---

## 2026-08-03 — D-03 · Offerte trattate come indipendenti

Ogni riga è trattata come una coppia (prezzo, quantità) a sé stante. Le offerte a blocchi
(`OFFER_TYPE='B'`) sono in realtà vincolate "tutto o niente" su più periodi consecutivi:
trattarle come semplici significa poterle accettare parzialmente o su un solo quarto d'ora.

**Costo dell'assunzione, misurato**: 4.579 righe su 568.185 nel giorno pilota, pari allo
**0,8%**. Accettabile per la costruzione delle curve. Da rivedere solo se in fase di
validazione i periodi con match mancato risultassero concentrati dove i blocchi pesano di più.

---

## 2026-08-03 — D-04 · Conversione decimale difensiva

La conversione accetta sia il punto sia la virgola come separatore decimale, pur avendo
verificato che nell'XML si usa il punto (vedi sopra). Il motivo è che l'archivio copre
undici anni e non è stato ispezionato file per file: se in qualche annata comparisse la
virgola, una conversione rigida produrrebbe NaN silenziosi, cioè offerte che scompaiono
dalle curve senza segnalazione. Il controllo di qualità (`riepilogo()`) conta esplicitamente
i NaN e i range di prezzi e quantità a ogni caricamento.

---

## 2026-08-03 — D-05 · Analisi ristretta alla granularità PT15

### Decisione
La ricostruzione delle curve usa le sole offerte con `GRANULARITY = 'PT15'` (96 periodi da
15 minuti). Le righe PT60 e PT30 vengono caricate e **contate**, ma escluse dal clearing.

### Perché
Mescolare granularità richiede un'assunzione forte: una quantità PT60 è energia riferita a
un'ora intera, quindi per confrontarla con offerte su un quarto d'ora bisogna deciderne la
ripartizione (uniforme? con lo stesso prezzo su tutti e quattro i quarti?). È un'assunzione
che va validata, non introdotta di soppiatto al primo passo.

### Quanto si sta escludendo (giorno pilota, NORD)
5.762 righe su 137.039, pari al **4,2%** delle righe. La quota in MWh è riportata dallo
script `01_carica_ed_esplora.py` a ogni esecuzione.

### Da fare
Il test preliminare mostra che aggiungere le righe PT60 riscalate (quantità divisa per 4)
sposta il prezzo ricostruito da 400 a 319 €/MWh sul periodo 40: **non è trascurabile**.
Una volta pronta la funzione di clearing, confrontare sistematicamente le due varianti
(solo PT15 vs PT15 + PT60 riscalato) sulla frequenza di match e decidere di conseguenza.

---

## 2026-08-03 — D-06 · Quali `STATUS_CD` entrano nelle curve · **QUESTIONE APERTA**

### Il problema
Nel file convivono sei stati. La lettura corrente dei codici — **da confermare** con la
documentazione GME — è: `ACC` accettata, `REJ` respinta (offerta valida che ha partecipato
all'asta ma è rimasta fuori mercato), `REP` sostituita da una successiva presentazione dello
stesso operatore, `REV` revocata, `INC` incongruente, `PREJ` respinta in fase preliminare.

Se questa lettura è corretta, la curva d'asta va costruita con **`ACC` + `REJ`**: sono le
offerte effettivamente in gara. Includere `REP` significherebbe contare due volte la stessa
offerta (l'originale e la sostituta); includere `REV` conterebbe offerte ritirate.

### Perché è la decisione più delicata del progetto
I prezzi ricostruiti sul periodo 40 vanno da 400 (`ACC`+`REJ`) a 2.000 (`ACC`+`REJ`+`REP`)
a 853 (tutti) €/MWh, contro un prezzo ufficiale di 177,87. La scelta cambia il risultato di
un ordine di grandezza. Con i soli `ACC` non esiste intersezione, ed è atteso: le offerte
accettate sono per costruzione quelle "dentro" il mercato, la curva risulta troncata proprio
dove servirebbe il punto di incrocio.

### Piano di validazione
Costruire la funzione di clearing, poi eseguirla su tutti i 96 periodi del giorno pilota per
ciascuna combinazione di stati, e scegliere quella che massimizza la frequenza di match con
`AWARDED_PRICE_NO` (D-09) e minimizza l'errore assoluto mediano. Da fare **in parallelo**
alla verifica di D-01 (zona isolata), perché i due effetti si sommano e vanno separati.

---

## 2026-08-03 — D-07 · `AWARDED_PRICE_NO` come prezzo zonale ufficiale

Vedi sopra ("Scoperta utile"). Il controllo dell'assunzione è che il numero di valori
distinti di `AWARDED_PRICE_NO` fra le righe `ACC` sia esattamente 1 per ogni periodo:
verificato dallo script `01_carica_ed_esplora.py` a ogni esecuzione. Il file
`data/processed/prezzi_ufficiali_NORD_20260331.csv` contiene la serie dei 96 prezzi.

---

## 2026-08-03 — D-08 · Lettura XML in streaming con cache Parquet

`pandas.read_xml` costruisce in memoria l'intero albero del documento: sui 574 MB del file
pilota significa diversi GB di RAM e un riparsing completo a ogni esecuzione. Si usa invece
`lxml.etree.iterparse`, che scorre il file in streaming a memoria costante, applica il
filtro di zona durante il parsing e salva l'esito in Parquet dentro `data/interim/`. È una
scelta puramente tecnica — non tocca i risultati — ma abilita il lavoro su più giorni: con
5.251 file nell'archivio, un caricamento non incrementale renderebbe l'analisi multi-anno
impraticabile.

---

## 2026-08-03 — D-09 · Criterio di validazione: frequenza di match

La bontà della ricostruzione si misura come **frequenza di match**: quota dei periodi in cui
il prezzo ricostruito coincide con quello ufficiale entro una tolleranza (da fissare, es.
±0,01 e ±1 €/MWh), affiancata dall'errore assoluto mediano e dalla sua distribuzione per
fascia oraria. Nelle ore di congestione lo scarto è atteso per costruzione (D-01): la
frequenza di match è quindi anche una misura indiretta di quanto la zona NORD sia
effettivamente isolata, ora per ora.

---

## 2026-08-03 — Passo 1 eseguito: caricamento e validazione del giorno pilota

Esecuzione di `scripts/01_carica_ed_esplora.py` sul 31/03/2026, zona NORD. Report completo
in `output/tabelle/01_riepilogo_20260331_NORD.txt`.

### Controlli superati
* **137.039** righe caricate = esattamente il conteggio di `ZONE_CD='NORD'` ottenuto con una
  scansione indipendente del file grezzo: la lettura in streaming non perde righe.
* `ZONE_CD` ha un solo valore (`NORD`) e `MARKET_CD` un solo valore (`MGP`): il filtro di
  primo livello funziona.
* **Zero NaN** su tutte le colonne numeriche: la conversione decimale non perde valori.
* **96 periodi PT15** presenti, PERIOD da 1 a 96; PT30 1-48; PT60 1-24: coerente con D-05.
* `AWARDED_PRICE_NO` ha **un solo valore distinto per periodo** (0 periodi ambigui su 96):
  l'assunzione di D-07 regge. I controlli puntuali sui periodi 40 (177,87) e 76 (180,20)
  tornano esatti.
* Seconda esecuzione: la cache Parquet viene riletta in pochi secondi contro i minuti del
  parsing XML (D-08).

### Cosa si è osservato di nuovo

**I limiti di prezzo non sono 0-3000.** Il range osservato è **-500 … 4000 €/MWh**: i prezzi
negativi sono ammessi (fenomeno tipico dei mercati con forte penetrazione rinnovabile:
conviene pagare per immettere piuttosto che spegnere l'impianto). La costante in
`mgp/config.py` è stata corretta di conseguenza. Composizione degli estremi in NORD:

| | righe |
|---|---|
| acquisti a 4000 (price taker) | 28.504, cioè il **52% delle offerte di acquisto** |
| vendite a -500 (price taker) | 2.197 |
| vendite a 0 €/MWh | 37.705 |

Le vendite a 0 non sono al limite di prezzo ma si comportano da price taker: sono in buona
parte contratti bilaterali e impianti must-run. **Implicazione metodologica**: una quota
molto alta della domanda è rigida (price taker), quindi la curva di domanda è ripida e
l'effetto della batteria sul prezzo passerà quasi tutto dalla curva di offerta. Da tenere
presente quando si interpreteranno gli scenari.

**Squilibrio strutturale domanda-offerta in NORD.** Sui 96 periodi, la quantità media
offerta in acquisto è **40.377 MWh** contro **31.759 MWh** in vendita: la domanda supera
l'offerta interna in *ogni* periodo. È la conferma quantitativa del limite di D-01: NORD
importa, e l'import non compare fra le offerte `ZONE_CD='NORD'`. La zona isolata non può
chiudere il bilancio con le sole offerte interne, ed è il motivo per cui il prezzo
ricostruito risulta troppo alto.

**Contratti bilaterali**: 12.316 righe (9% del totale) per **742.957 MWh**, il 10,3% delle
quantità offerte. Entrano nel mercato come quantità a prezzo 0 (vendite) o a prezzo massimo
(acquisti), cioè come domanda/offerta rigida. Da non escludere: fanno parte del bilancio.

**Offerte a blocchi in NORD**: 2.117 righe (1,5% della zona), tutte con `BLOCK_ID`
valorizzato — coerente con D-03, il costo dell'assunzione resta contenuto.

**Accettazione parziale**: `PARTIAL_QTY_ACCEPTED_IN` vale `Y` solo su 554 righe. Quindi
quasi tutte le offerte sono "tutto o niente" sulla singola coppia prezzo-quantità: nella
funzione di clearing l'offerta marginale andrà comunque accettata parzialmente (è
l'approssimazione standard nella ricostruzione delle curve a gradini), ma va segnalato come
scostamento dalle regole d'asta effettive.

### Da fare
Confermare la lettura dei codici `STATUS_CD` sulla documentazione ufficiale GME: è il
presupposto di D-06, la decisione ancora aperta.

---

## 2026-08-03 — Impostato il flusso dei report settimanali per il relatore

### Cosa è stato fatto
Predisposto il meccanismo per il ricevimento settimanale: il testo del report si scrive in
Markdown in `docs/report/AAAA-MM-GG_report.md` e lo script `scripts/90_genera_report.py`
(modulo `mgp.report`) lo converte in un `.docx` dentro `output/report/`. Scritto il modello
`docs/report/_modello.md` e il primo report, quello di questa settimana.

### Perché Markdown come sorgente e Word come consegna
Il relatore commenta e annota in Word, quindi il documento che riceve dev'essere un `.docx`.
Ma un `.docx` è un file binario: non si confronta fra una settimana e l'altra, non si
versiona in modo utile e il suo testo non è riusabile per i capitoli della tesi. Tenendo il
sorgente in Markdown si ottengono entrambe le cose, e i report diventano una traccia
cronologica del lavoro che si può rileggere in sequenza.

### Alternative scartate
* **Scrivere direttamente in Word**: il testo resterebbe fuori dal versionamento e
  disallineato rispetto al diario.
* **Convertire con pandoc**: risultato migliore ma richiede l'installazione di uno strumento
  esterno; `python-docx` è già nel virtual environment e il sottoinsieme di Markdown che
  serve a un report metodologico è limitato (titoli, elenchi, tabelle, blocchi di codice).

### Convenzione adottata
Un file per settimana, non un unico documento cumulativo: il relatore deve poter vedere
subito che cosa è nuovo, senza rileggere lo storico. La continuità è garantita dal diario e
dal registro delle decisioni, che restano cumulativi. Struttura fissa del report: sintesi →
lavoro svolto → cosa dicono i dati → decisioni adottate → domande per il ricevimento →
estratti di codice → programma della settimana successiva. Le domande vanno presentate con
problema, alternative, evidenza numerica e orientamento personale: il ricevimento serve a
decidere, non a raccogliere l'istruttoria.

---

## Prossimi passi

1. `src/mgp/curve.py`: costruzione delle curve aggregate a gradini e funzione
   `prezzo_equilibrio(offerte_periodo)`, con test su casi giocattolo in `tests/`.
2. Validazione su tutti i 96 periodi del giorno pilota → scioglie D-06 e misura il bias di D-01.
3. Estensione: sensibilità al perimetro delle zone (NORD isolata vs NORD + frontiere) e alla
   granularità (D-05).
4. Simulazione della batteria: domanda addizionale nelle ore di carica, offerta addizionale in
   quelle di scarica, ricalcolo del prezzo di equilibrio (effetto di feedback).
5. Dimensionamento ottimale (capacità in MWh, potenza in MW, durata di carica/scarica) via
   ottimizzazione, tenendo conto dell'effetto di feedback sul prezzo.
