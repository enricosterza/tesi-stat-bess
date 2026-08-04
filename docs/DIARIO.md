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

## 2026-08-03 — Sciolte le quattro questioni aperte: D-06 e D-10 chiuse

**Nota sulla provenienza di queste decisioni.** Il ricevimento con il relatore non si è
ancora tenuto: le quattro questioni sono state sciolte in autonomia per non fermare il
lavoro, sulla base della conoscenza di dominio e delle evidenze raccolte. Restano quindi
**da sottoporre al relatore** alla prima occasione, in particolare il significato dei codici
`STATUS_CD`, che non è documentato in modo esplicito nei file GME. Se una di queste letture
si rivelasse errata, la decisione andrà superata con una voce nuova.

### D-06 (era aperta) · Significato degli stati e composizione della curva d'asta

Significati adottati:

| Codice | Significato |
|---|---|
| `ACC` | Accettata |
| `REJ` | Rifiutata |
| `PREJ` | **Paradossalmente rifiutata** (riguarda le offerte a blocchi) |
| `INC` | Incongrua |
| `REP` | Sostituita |
| `REV` | Revocata |

La lettura iniziale era corretta su `ACC`, `REJ`, `REP`, `REV`; la precisazione riguarda
`PREJ`, che non è un rifiuto "preliminare" ma il **rifiuto paradossale** tipico dei mercati
con offerte a blocchi: un'offerta può essere in merito sul prezzo e venire comunque
rifiutata perché il vincolo "tutto o niente" del blocco renderebbe inconsistente la
soluzione d'asta.

**Decisione.** Le curve si costruiscono con `ACC` + `REJ`: sono le offerte che hanno
effettivamente partecipato all'asta. Restano fuori `REP` (conterebbe due volte la stessa
offerta, l'originale e la sostituta), `REV` (offerte ritirate) e `INC` (offerte non valide).

**Trattamento di `PREJ`.** Sono anch'esse offerte in gara, quindi in linea di principio
vanno incluse. Nel giorno pilota sono però **20 righe su 568.185** (tutte in NORD, tutte
lato vendita): l'inclusione o l'esclusione non sposta nulla di misurabile. Verranno incluse
insieme a `REJ` e la sensibilità sarà verificata in fase di validazione, riportando il
numero di periodi in cui il prezzo cambia.

C'è però una conseguenza concettuale da annotare per la tesi: l'esistenza stessa dei rifiuti
paradossali conferma che il vero algoritmo d'asta risolve un problema con vincoli di
interezza, mentre la nostra ricostruzione a curve continue tratta i blocchi come offerte
divisibili (D-03). I `PREJ` sono la traccia osservabile di quella differenza.

### D-10 (nuova, supera D-01) · Perimetro zonale

**Decisione.** Alle offerte della zona NORD si aggiungono quelle delle **zone virtuali di
frontiera confinanti**, senza imporre vincoli di capacità di transito.

**Perché.** Il dato mostrava che in NORD la domanda supera l'offerta interna in tutti e 96 i
periodi del giorno pilota: la zona isolata non può chiudere il bilancio e il prezzo
ricostruito risulta troppo alto (400 €/MWh contro 177,87 ufficiale sul periodo 40). L'import
non è un dettaglio, è la parte a basso costo della curva di offerta.

**Cosa resta approssimato.** Non imponendo i limiti di transito si ammette implicitamente
che tutta l'energia offerta sulle frontiere possa entrare in NORD. Nella realtà i transiti
sono vincolati e nelle ore di congestione il vincolo è attivo: ci si attende quindi un
prezzo ricostruito *più basso* di quello reale in quelle ore, cioè un bias di segno opposto
a quello della zona isolata. Le due varianti (isolata / con frontiere) verranno confrontate
sulla stessa metrica di match, così l'errore risulta acquisito da entrambi i lati.

**Da verificare in implementazione.** Quali zone virtuali confinino effettivamente con NORD.
Nel giorno pilota compaiono `SVIZ` (3.357 righe), `MONT` (979), `CORS` (864), `COAC` (864),
`FRAN` (96), `MALT` (28): fra queste, `CORS` e `MALT` sono frontiere di altre zone (Corsica
verso CNOR/SARD, Malta verso SICI) e non vanno incluse. Non compaiono zone per Austria e
Slovenia, che pure confinano con NORD: da capire se i relativi scambi siano rappresentati
altrove (market coupling implicito) e se questo lasci scoperta una parte dell'import. È il
primo controllo da fare prima di usare il perimetro allargato.

### D-13 (era D3) · Granularità minoritaria

Confermato l'orientamento: si resta sulla granularità prevalente in fase di messa a punto,
poi si confrontano sistematicamente le due varianti sulla frequenza di match e si adotta la
migliore, documentando il confronto.

### D-11 · Periodo di studio: gennaio 2025 per validare, poi tutto il 2025

Il campione è l'anno solare **2025**, partendo da **gennaio** per validare il modello.

---

## 2026-08-03 — Il 2025 non è a 15 minuti: il periodo di mercato cambia il 1° ottobre 2025

### Come è emerso
Prima di impostare il lavoro sul 2025 sono stati scanditi i file dell'archivio contando i
valori di `GRANULARITY`. Risultato:

| Giorno | Composizione |
|---|---|
| 15/01/2025, 15/03/2025, 01/06/2025, 01/09/2025 | PT60 100% |
| 26, 28, 29, 30/09/2025 | PT60 100% |
| **01/10/2025** | **PT15 82,8%**, PT60 17,2% |
| 02/10/2025 | PT15 89,3%, PT60 10,7% |
| 15/10, 01/11, 01/12/2025, 15/01/2026 | PT15 ~95,7%, PT60 ~4,3% |

Il passaggio al periodo di mercato da 15 minuti è **netto e cade il 1° ottobre 2025**.

### Perché conta
1. **Il 2025 non è omogeneo**: nove mesi a granularità oraria (24 aste al giorno) e tre mesi
   a quarto d'ora (96 aste al giorno). Un'analisi "sull'anno 2025" mette insieme due
   risoluzioni temporali diverse.
2. **La decisione D-05 ("solo PT15") non è applicabile**: da gennaio a settembre 2025 non
   esiste una sola offerta PT15. Va riformulata → **D-12**: si usa la granularità *nativa
   prevalente del giorno*, quale che sia.
3. **Il mese di validazione scelto (gennaio 2025) è orario**, mentre tutta la messa a punto
   finora è stata fatta su un giorno a quarto d'ora. Non è un problema — il lettore
   normalizza le due granularità e la funzione di clearing lavora comunque su un periodo
   alla volta — ma la validazione va fatta su entrambe le risoluzioni prima di fidarsene.
4. **La risoluzione temporale non è neutrale per l'oggetto della tesi**: la strategia di
   arbitraggio di una batteria dipende da quanto è fine la griglia temporale su cui può
   caricare e scaricare. Confrontare risultati orari e a quarto d'ora richiede cautela; per
   contro, avere entrambe le risoluzioni permette di *misurare* quanto la risoluzione
   incide sul valore dell'arbitraggio, che è un risultato di interesse.

### Copertura dell'archivio
Dal 13/02/2015 al 31/03/2026, 4.065 giorni. Il 2025 è completo (365 giorni su 365), del 2026
ci sono i primi 90 giorni. I giorni a granularità nativa PT15 sono **182**, dal 01/10/2025 al
31/03/2026: non esiste quindi, nei dati disponibili, un anno intero a quarto d'ora.

### Decisione provvisoria e questione da portare al prossimo ricevimento
Si procede come stabilito — validazione su gennaio 2025 (orario), poi estensione all'anno
solare 2025 — usando per ogni giorno la sua granularità nativa (D-12) e riportando i
risultati su base oraria, in modo che l'anno resti confrontabile. Resta da decidere se
affiancare a questo un'analisi a quarto d'ora sui 182 giorni disponibili: è la domanda
portata al prossimo ricevimento.

---

## 2026-08-03 — `curve.py`: clearing implementato, e tre correzioni al lavoro precedente

Scritto `src/mgp/curve.py` con le curve aggregate a gradini e `prezzo_equilibrio()`, più
`tests/test_curve.py` (22 test su casi calcolabili a mano) e lo script
`scripts/02_ricostruisci_prezzi.py`, che confronta le varianti della pipeline sui prezzi
ufficiali. Lungo la strada sono emerse tre cose che correggono quanto scritto prima.

### Correzione 1 — `QUANTITY_NO` è una POTENZA (MW), non l'energia del periodo

**Come è emerso.** Sommando le quantità assegnate a livello nazionale nel giorno pilota
venivano 37.149 "MWh" in un quarto d'ora, cioè 148 GW di potenza: un valore impossibile,
circa quattro volte il fabbisogno italiano. Il confronto con un giorno orario ha sciolto il
dubbio: 15/01/2025 → 38.334 in media all'ora; 31/03/2026 → 31.956 in media al quarto d'ora.
Il rapporto è **0,83**, non 0,25: se fossero energie riferite al periodo, passando dall'ora
al quarto d'ora dovrebbero ridursi a un quarto. Sono potenze, e la differenza residua è la
stagionalità del fabbisogno (gennaio contro marzo).

**Conseguenze.**
* Un'offerta oraria di X MW vale X MW in **ciascuno** dei quattro quarti d'ora dell'ora:
  non va divisa per quattro. Il codice che scrivevo lo faceva ed era sbagliato.
* Va corretta l'osservazione registrata il 03/08 nella prima esplorazione, secondo cui
  includere le offerte orarie "riscalate" spostava il prezzo del periodo 40 da 400 a
  319 €/MWh: quel numero era calcolato dividendo per quattro. Con la quantità corretta
  l'effetto è molto maggiore (vedi sotto).
* Tutte le etichette `MWh_*` nei riepiloghi sono state rinominate `MW_*`. L'energia serve
  solo dove conta davvero, cioè nel bilancio della batteria, e si ottiene moltiplicando per
  la durata del periodo (`config.in_energia`).

### Correzione 2 — "la domanda supera l'offerta in tutti e 96 i periodi" era un artefatto

Quell'osservazione era calcolata **su tutte le righe**, comprese `REP` (sostituite) e `REV`
(revocate), che non partecipano all'asta. Con il filtro corretto (D-06) il quadro cambia:

| Selezione | domanda media | offerta media | periodi con domanda > offerta |
|---|---|---|---|
| tutte le righe | 40.377 MW | 31.759 MW | 96 su 96 |
| solo offerte in gara | 19.038 MW | 19.190 MW | 44 su 96 |

Le offerte in gara sono quindi **quasi in pareggio**. Resta vero che NORD importa, ma la
prova non è questa: è il confronto fra quantità *assegnate*, dove gli acquisti superano le
vendite di circa 6.300 MW per periodo. È una lezione metodologica da tenere: un filtro
sbagliato produce un'evidenza convincente e falsa.

### Correzione 3 — l'ambiente non richiede più il certificato di Avast

Il bundle CA `wscert.pem` non esiste più sul sistema e `pip` funziona senza alcuna
configurazione: il file `.venv/pip.ini` è stato rimosso. Se in futuro `pip` tornasse a
fallire con `CERTIFICATE_VERIFY_FAILED`, la causa è l'intercettazione TLS dell'antivirus.

---

## 2026-08-03 — D-16 · L'import netto come blocco esogeno, e i risultati della validazione

### Il problema, misurato
Ricostruendo la curva della sola zona NORD il prezzo risulta **sistematicamente più alto**
di quello ufficiale: errore mediano 128,43 €/MWh a zona isolata, 100,79 aggiungendo le
frontiere confinanti, 99,31 aggiungendo tutte le zone virtuali. Il bias è sempre positivo,
la frequenza di match è zero a qualunque tolleranza.

La diagnosi sul periodo 40 spiega perché. Al prezzo ufficiale di 177,87 €/MWh:

* la **domanda ricostruita coincide con quella ufficialmente assegnata**: 37.152,6 MW
  contro 37.149,3. Su tutti i 96 periodi lo scarto è sotto lo 0,1% in **94 periodi su 96**
  (media 0,02%). La curva di domanda è ricostruita correttamente;
* l'**offerta no**: in NORD gli acquisti assegnati (21.304 MW) superano le vendite assegnate
  (10.920 MW) di oltre 10 GW. Quella differenza è energia che entra in NORD dalle altre zone
  e dall'estero, e **non compare fra le offerte con `ZONE_CD = NORD`**.

Le zone virtuali di frontiera non colmano il vuoto: sull'intero giorno pilota `SVIZ` offre
in vendita 121.796 MW cumulati e `FRAN` 960, contro 1.842.251 di NORD. Aggiungerle riduce
l'errore da 128 a 101 €/MWh, ma il grosso dell'import resta fuori dai dati: passa dal market
coupling e da meccanismi (offerte integrative GSE) pubblicati in dataset diversi.

### La decisione (D-16)
Si introduce nella curva di offerta un **blocco price taker di import netto**, pari alla
differenza fra acquisti e vendite assegnate nel perimetro, collocato al prezzo minimo di
mercato. È energia già allocata altrove, che entra comunque: si comporta da offerta
anelastica e trasla la curva verso destra senza cambiarne la forma.

**Limite da dichiarare.** L'import è calcolato dall'esito osservato dell'asta, quindi è una
grandezza **calibrata**, non prevista dal modello. Quando si simulerà la batteria si
assumerà che i flussi di import non reagiscano alla variazione di prezzo indotta: è
un'assunzione forte. Il prezzo resta comunque un esito del modello, non un dato: emerge
dall'incrocio delle curve, e lo scarto residuo misura quanto bene sono ricostruite.

### Risultati della validazione

**31/03/2026 (96 aste da 15 minuti), perimetro NORD + frontiere, offerte in gara,
inclusa l'altra granularità:**

| Variante | Errore mediano | Bias mediano | Match ±1 € | Match ±5 € |
|---|---|---|---|---|
| NORD isolata | 128,43 | +128,43 | 0% | 0% |
| NORD + frontiere | 100,79 | +100,79 | 0% | 0% |
| … + offerte all'altra granularità | 24,57 | +24,57 | 5,2% | 11,5% |
| … + blocco di import netto | **5,25** | **+1,52** | 12,5% | 50,0% |

**15/01/2025 (24 aste orarie), stessa pipeline:**

| Variante | Errore mediano | Match esatto (±0,01 €) | Match ±1 € | Match ±5 € |
|---|---|---|---|---|
| NORD + frontiere, senza import | 38,26 | 0% | 0% | 0% |
| NORD + frontiere + import netto | **0,05** | **45,8%** | 75,0% | 91,7% |

Il giorno orario si ricostruisce nettamente meglio di quello a quarto d'ora: 11 ore su 24
sono riprodotte **esattamente**. Due possibili spiegazioni, da verificare: il mercato a 15
minuti è più recente e potrebbe avere una quota maggiore di offerte gestite fuori dalle
offerte pubbliche; oppure la ripartizione delle offerte orarie residue sui quarti d'ora
introduce un errore che sulle aste orarie non esiste. È il primo controllo della prossima
settimana, da fare su più giorni prima di trarne conclusioni.

### Effetto degli stati ammessi (chiude la verifica di D-06)
A parità di perimetro, sul giorno pilota: `ACC+REJ+PREJ` e `ACC+REJ` danno lo stesso
risultato (i 20 `PREJ` non spostano nulla, come atteso); aggiungere `REP` peggiora l'errore
da 100,79 a 358,53; usare tutti gli stati lo porta a 281,84; con i soli `ACC` le curve si
incrociano in 2 periodi su 96. La scelta di D-06 è quindi confermata dai dati, non solo dal
ragionamento.

### Effetto della granularità minoritaria (chiude D-13)
Includere le offerte presentate all'altra granularità **migliora nettamente**: errore
mediano da 100,79 a 24,57 sul giorno a quarto d'ora. Sul giorno orario non cambia nulla,
perché non ci sono offerte a 15 minuti da includere. La variante adottata è quindi quella
con le offerte di tutte le granularità, senza riscalare le quantità (sono potenze).

---

## 2026-08-04 — Validazione su gennaio 2025 (744 aste) e correzione di D-16

Scritto `scripts/03_valida_mese.py`, che esegue la ricostruzione su tutti i giorni di un
mese e ne analizza l'errore per giorno, per ora del giorno e per presenza di congestione.
Eseguito su **gennaio 2025**: 31 giorni, 744 aste orarie, tutte con equilibrio esistente.

### Il primo passaggio ha rivelato un difetto del modello: mancava l'export

Nella prima esecuzione i dieci periodi con l'errore più grande erano **tutti** periodi in cui
NORD **esporta** (import netto negativo), con scarti fino a **-85 €/MWh** la sera del
20/01/2025, quando NORD esportava circa 3.700 MW. Il motivo era nel codice: `aggiungi_import`
inseriva il blocco solo quando la quantità era positiva, quindi nei periodi di export non
succedeva nulla e l'offerta interna risultava sovrastimata, con prezzo ricostruito troppo
basso.

**Correzione (D-16 riformulata).** Lo scambio netto con l'esterno del perimetro entra in modo
**simmetrico**:

* import (scambio > 0) → offerta di vendita al prezzo minimo: energia già allocata altrove
  che si colloca comunque, quindi offerta anelastica;
* export (scambio < 0) → offerta di acquisto al prezzo massimo: domanda proveniente da fuori
  il perimetro, che compra a qualunque prezzo.

Il nome della grandezza resta "import netto" ma il segno conta, ed è per questo che nel
codice il blocco è etichettato `SCAMBIO`.

### Effetto della correzione

| Indicatore (gennaio 2025, 744 aste) | Prima | Dopo |
|---|---|---|
| Scarto medio | -1,09 €/MWh | **-0,35** |
| Deviazione standard dello scarto | 5,65 | **1,65** |
| Scarto massimo in valore assoluto | 85,00 | **15,88** |
| Match entro ±0,01 €/MWh | 41,0% | **44,5%** |
| Match entro ±1 €/MWh | 73,1% | **76,7%** |
| Match entro ±5 €/MWh | 95,4% | **98,1%** |
| Errore mediano della giornata peggiore | 3,92 | **1,81** |

Sul giorno pilota a quarto d'ora (31/03/2026) non cambia nulla, perché NORD importa in tutti
i 96 periodi: resta errore mediano 5,25 €/MWh.

### Risultati della validazione mensile

**Complessivo:** mediana dello scarto **0,00 €/MWh**, media -0,35, deviazione standard 1,65.
Il prezzo ricostruito è **esatto al centesimo nel 44,5% delle ore**, entro 1 €/MWh nel 76,7%
ed entro 5 €/MWh nel 98,1%. Prezzo ufficiale medio del mese 143,32 €/MWh, ricostruito 142,97.

**Stabilità nel tempo:** l'errore mediano giornaliero ha mediana 0,11 €/MWh e non supera mai
1,81. Undici giornate su 31 sono ricostruite con errore mediano nullo. Non c'è deriva né
dipendenza dal livello dei prezzi: il 20/01, giornata più cara del mese (193,93 €/MWh medi),
ha errore mediano 0,23.

**Per ora del giorno:** l'accuratezza è uniforme. Nelle ore di picco serale (18-21), che sono
quelle in cui una batteria scaricherebbe, l'errore mediano sta fra 0,00 e 0,21 €/MWh e il
match entro 1 €/MWh fra il 67,7% e il 90,3% — in linea con le ore notturne. È un punto
importante: se il modello fosse impreciso proprio nelle ore di picco, la stima del ricavo da
arbitraggio ne risentirebbe in modo sistematico.

### Risultato controintuitivo: la congestione non peggiora la ricostruzione

Definendo "congestionato" un periodo in cui le sette zone italiane non hanno tutte lo stesso
prezzo (133 periodi su 744, con spread zonale mediano 15,79 €/MWh e punte di 152,42):

| | Periodi | Errore mediano | Match ±1 € | Match ±5 € |
|---|---|---|---|---|
| Non congestionati | 611 | 0,17 | 75,9% | 97,9% |
| Congestionati | 133 | **0,00** | **80,5%** | **99,3%** |

La correlazione fra spread zonale ed errore assoluto è **0,03**, cioè nulla. Mi aspettavo il
contrario: ignorando i limiti di transito (D-10) il modello dovrebbe soffrire proprio quando
i vincoli sono attivi.

**La spiegazione è che il blocco di scambio netto assorbe la congestione.** Lo scambio è
calibrato sulle quantità effettivamente assegnate, e quelle quantità sono già l'esito
dell'ottimizzazione con i vincoli di transito: il vincolo entra nel modello sotto forma di
quantità osservata anziché di vincolo esplicito. Non è quindi vero che il modello "regge alla
congestione"; è vero che **la congestione è stata calibrata via**, il che va detto con
chiarezza in tesi. La conseguenza pratica è sulla simulazione della batteria: assumere lo
scambio fisso significa assumere che una batteria in NORD non modifichi i flussi con le altre
zone, e questa assunzione è tanto più forte quanto più il periodo è congestionato.

### Errori residui
Il caso peggiore è ora -15,88 €/MWh (03/01/2025 ore 5). Gli errori superstiti sono in
prevalenza **negativi** (prezzo ricostruito più basso dell'ufficiale) e concentrati in poche
giornate: 31/01 compare quattro volte fra i dieci scarti maggiori. Da capire la settimana
prossima; una pista è la quota di offerte a granularità non prevalente in quelle giornate.

---

## Prossimi passi

1. Verificare quali zone virtuali di frontiera confinano con NORD e cosa aggiungono in
   quantità e in prezzo alla curva di offerta (presupposto di D-10).
2. `src/mgp/curve.py`: costruzione delle curve aggregate a gradini e funzione
   `prezzo_equilibrio(offerte_periodo)`, con test su casi giocattolo in `tests/`.
3. Validazione sul giorno pilota con il perimetro allargato (D-10) e le offerte `ACC`+`REJ`
   (D-06): confronto fra prezzo ricostruito e prezzo ufficiale sui 96 periodi.
4. Estendere la validazione a gennaio 2025 (granularità oraria) e misurare la frequenza di
   match sulle due risoluzioni temporali; confronto delle varianti di D-13.
5. Elaborazione dell'anno 2025 completo, con caricamento incrementale dei 365 file.
6. Simulazione della batteria: domanda addizionale nelle ore di carica, offerta addizionale in
   quelle di scarica, ricalcolo del prezzo di equilibrio (effetto di feedback).
7. Dimensionamento ottimale (capacità in MWh, potenza in MW, durata di carica/scarica) via
   ottimizzazione, tenendo conto dell'effetto di feedback sul prezzo.
