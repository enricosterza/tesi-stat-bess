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
7. **La granularità è mista anche nei dati recenti**: nel giorno pilota, zona NORD,
   convivono PT15 (96 periodi), PT60 (24 periodi) e PT30 (48 periodi). `PERIOD` non è
   quindi interpretabile da solo: va sempre letto insieme a `GRANULARITY`, altrimenti
   filtrando `PERIOD == 10` si mescolano il decimo quarto d'ora e la decima ora → **D-05**.
8. **Le offerte a blocchi esistono e sono identificabili**: `OFFER_TYPE` vale `S`
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

## 2026-08-04 — Perché le aste a quarto d'ora si ricostruiscono peggio: sono le offerte a blocchi

Scritto `scripts/04_diagnosi_scarti.py`, che scompone lo scarto fra prezzo ricostruito e
ufficiale nelle sue possibili cause. Confrontati **gennaio 2025** (744 aste orarie) e la
settimana **12-18 gennaio 2026** (672 aste a quarto d'ora), scelta nello stesso mese
dell'anno per non confondere l'effetto della risoluzione con quello della stagionalità.

### Il divario, confermato su più giorni

| | Gennaio 2025 (oraria) | 12-18 gennaio 2026 (quarto d'ora) |
|---|---|---|
| Aste | 744 | 672 |
| Scarto mediano | 0,00 €/MWh | +0,25 |
| Deviazione standard dello scarto | 1,65 | **8,81** |
| Match entro ±1 €/MWh | 76,7% | **22,3%** |
| Match entro ±5 €/MWh | 98,1% | 64,6% |

Il bias è quasi nullo in entrambi i casi: il problema è la **dispersione**, non una
distorsione sistematica.

### Prima ipotesi, scartata dai dati: le curve quasi tangenti

Avevo ipotizzato che nelle aste a quarto d'ora le curve fossero più piatte attorno
all'equilibrio, cosicché un piccolo errore di quantità si traducesse in un grande errore di
prezzo. Per verificarlo ho aggiunto `curve.impatto_prezzo()`, che misura di quanto si sposta
il prezzo iniettando 100 MW di offerta — la stessa grandezza che servirà per l'effetto di
feedback della batteria.

La misura smentisce l'ipotesi: la sensibilità mediana è **0,10 €/MWh per 100 MW nelle aste
orarie e 0,00 in quelle a quarto d'ora**. Le curve a quarto d'ora sono semmai più ripide.
L'ipotesi era plausibile ma sbagliata, e la funzione scritta per verificarla resta utile.

Scartata anche l'ipotesi dell'equilibrio non unico: succede nello 0,8% delle aste orarie e
nello 0,0% di quelle a quarto d'ora, e nei 6 casi osservati il prezzo ufficiale cade dentro
l'intervallo in 5, quindi non è una fonte di errore rilevante.

### Dove sta davvero l'errore: sul lato offerta

Confrontando domanda e offerta **ricostruite al prezzo ufficiale** con le quantità
effettivamente assegnate (scarto in valore assoluto, mediano):

| | Errore sulla domanda | Errore sull'offerta | Errore sul prezzo |
|---|---|---|---|
| Aste orarie | 0,000% | 0,40% | 0,12 €/MWh |
| Aste a quarto d'ora | 0,095% | **4,62%** | 3,24 €/MWh |

La domanda resta ricostruita quasi esattamente in entrambi i mercati. L'errore sull'offerta è
**undici volte più grande** nelle aste a quarto d'ora.

### La causa: le offerte a blocchi

Contando quante offerte di vendita risultano incoerenti con il prezzo del proprio periodo
(in merito sul prezzo ma non assegnate, o viceversa):

| | Aste orarie | Aste a quarto d'ora |
|---|---|---|
| Offerte a blocchi sul totale | 0,54% | **2,82%** |
| Righe incoerenti | 0,06% | 0,52% |
| MW incoerenti per asta | 33 | **882** |
| Quota di quei MW dovuta ai blocchi | 55,1% | **99,2%** |
| Quantità media: offerte coerenti / incoerenti | 49,7 / 91,2 MW | 40,2 / **385,3 MW** |

Nel mercato a quarto d'ora le offerte a blocchi sono cinque volte più frequenti e quasi dieci
volte più grandi della media. Trattarle come offerte divisibili — decisione **D-03** — sposta
l'offerta di circa 880 MW per asta, il 5% del volume scambiato.

### Prova di controllo

Confronto di tre trattamenti dei blocchi sulle stesse aste (l'ultimo usa l'esito osservato
dell'asta, quindi non è un modello utilizzabile: serve solo a misurare il guadagno massimo
ottenibile risolvendo il problema).

**Gennaio 2026, quarto d'ora (576 aste):**

| Trattamento dei blocchi | Errore mediano | Dev. standard | Match ±1 € | Match ±5 € |
|---|---|---|---|---|
| come offerte semplici (attuale) | 2,91 | 9,11 | 24,1% | 67,4% |
| esclusi dalle curve | 36,76 | 37,77 | 0,3% | 12,0% |
| con l'esito osservato (diagnostico) | **2,30** | **5,09** | 30,4% | 74,5% |

**Gennaio 2025, orario (144 aste):**

| Trattamento dei blocchi | Errore mediano | Dev. standard | Match ±1 € |
|---|---|---|---|
| come offerte semplici (attuale) | 0,09 | 1,36 | 77,8% |
| esclusi dalle curve | 1,21 | 3,70 | 43,8% |
| con l'esito osservato (diagnostico) | 0,06 | 1,28 | 79,2% |

Tre letture.

1. **Escludere i blocchi è molto peggio che trattarli come semplici**: portano volume che
   deve stare nella curva. L'assunzione attuale, per quanto imperfetta, è meglio della
   sua alternativa banale.
2. **I blocchi sono la causa principale identificata**: trattandoli correttamente la
   deviazione standard dello scarto quasi si dimezza (9,11 → 5,09).
3. **Non spiegano tutto.** Anche con il trattamento perfetto, le aste a quarto d'ora restano
   molto meno accurate di quelle orarie (dev. standard 5,09 contro 1,36). Un residuo non
   spiegato rimane, e va indagato: candidati sono l'accettazione parziale e i vincoli
   inter-temporali fra quarti d'ora consecutivi.

### Conseguenza su D-03: la valutazione precedente era sbagliata

Il 03/08 avevo classificato l'impatto di D-03 come "basso: 0,8% delle righe". Contato in
righe sembra trascurabile; contato in **MW e in effetto sul prezzo** è la causa principale
dell'errore nel mercato a quarto d'ora. La valutazione è stata corretta nel registro delle
decisioni. È esattamente l'errore contro cui mette in guardia il metodo di lavoro adottato:
il costo di una semplificazione va misurato nell'unità in cui produce l'effetto, non in
quella più comoda da contare.

### Perché gli errori si concentrano in poche giornate
La correlazione fra l'errore mediano della giornata e le sue caratteristiche, sulla settimana
a quarto d'ora: errore sull'offerta 0,72, quota di offerte a granularità non prevalente 0,49,
quota di offerte a blocchi 0,41, congestione 0,05, scambio netto 0,03. Le giornate peggiori
sono quelle con più blocchi e più offerte orarie, non quelle congestionate né quelle con
scambi più intensi. Nel mese orario vale lo stesso: la correlazione fra errore sul prezzo ed
errore sull'offerta è 0,99.

### Da fare
Implementare un clearing consapevole dei blocchi: risolvere l'asta senza blocchi, accettare i
blocchi in merito, ripetere fino a convergenza. Il guadagno atteso è quantificato sopra
(deviazione standard da 9,11 a circa 5,09 nel caso migliore).

---

## 2026-08-04 — D-18 implementata: clearing iterativo con i blocchi, e residuo ancora aperto

### Il clearing consapevole dei blocchi
Implementata in `curve.clearing_giorno_con_blocchi()` l'euristica iterativa: si parte con
tutti i blocchi accettati, si risolvono tutte le aste della giornata, si rivaluta ogni blocco
sul **prezzo medio ponderato dei periodi che copre**, e si ripete fino a stabilità. Il
criterio del prezzo medio è quello degli algoritmi d'asta europei: un blocco è in the money se
il ricavo complessivo copre il prezzo offerto, non se lo copre in ogni singolo periodo.

La struttura del dato giustifica l'impostazione a livello di giornata: un `BLOCK_ID` copre da
4 a 96 periodi, ha un prezzo unico, e nessun blocco risulta accettato solo su una parte dei
suoi periodi. Il vincolo è quindi genuinamente multi-periodo e non si può risolvere un'asta
alla volta.

### Risultati

**Gennaio 2025, 744 aste orarie:**

| Trattamento dei blocchi | Errore mediano | Dev. standard | Match ±1 € |
|---|---|---|---|
| come offerte semplici | 0,11 | 1,65 | 76,8% |
| esclusi | 0,39 | 2,63 | 67,3% |
| **clearing iterativo (D-18)** | **0,08** | **1,45** | **78,4%** |
| con esito osservato (limite) | 0,07 | 1,42 | 79,2% |

**12-18 gennaio 2026, 672 aste a quarto d'ora:**

| Trattamento dei blocchi | Errore mediano | Dev. standard | Match ±1 € |
|---|---|---|---|
| come offerte semplici | 3,23 | 8,81 | 22,3% |
| esclusi | 28,45 | 36,01 | 0,3% |
| **clearing iterativo (D-18)** | **2,94** | **8,36** | **25,6%** |
| con esito osservato (limite) | 2,44 | 5,15 | 30,2% |

Sulle aste orarie l'euristica **raggiunge praticamente il limite dell'oracolo** (0,08 contro
0,07). Sulle aste a quarto d'ora recupera invece solo una parte del guadagno disponibile:
la deviazione standard scende da 8,81 a 8,36 contro il 5,15 ottenibile.

**Perché la differenza.** L'euristica **non converge in 4 giornate su 7** nel campione a
quarto d'ora: oscilla fra due configurazioni di blocchi accettati e si ferma al limite di
iterazioni. Sulle giornate orarie converge quasi sempre in una o due iterazioni, perché i
blocchi sono pochi (da 2 a 12 al giorno) contro i 30-34 delle giornate a quarto d'ora.

Attenzione a non generalizzare da un caso: sulla prima giornata provata (12/01/2026)
l'euristica raggiungeva esattamente l'oracolo, e sembrava un risultato pieno. Sulla settimana
completa il quadro è più modesto. È la stessa lezione del mese di gennaio: una giornata
singola non basta a giudicare.

**Da fare.** Gestire l'oscillazione: fra le configurazioni visitate, sceglierne una con un
criterio esplicito — per esempio quella che massimizza il benessere sociale, o che minimizza
il numero di blocchi accettati fuori merito — invece di fermarsi all'ultima raggiunta.

### Il residuo delle aste a quarto d'ora: due candidati esclusi

**Accettazione parziale.** Il mercato accetta parzialmente 2,7 offerte per asta, per 94 MW su
31.427 assegnati: lo **0,3%**. Ed è simile nei due mercati (0,27% delle offerte accettate a
quarto d'ora contro 0,36% orarie). Non è la spiegazione.

**Vincoli fra quarti d'ora consecutivi.** A prima vista promettente: l'80,3% delle unità ha la
stessa quantità assegnata nei quattro quarti dell'ora. Ma è un artefatto — un'offerta lontana
dal margine viene accettata in tutti e quattro i quarti comunque. Il test discriminante è
sulle offerte identiche nei quattro quarti il cui **prezzo cade fra il minimo e il massimo dei
quattro prezzi dell'ora**, le uniche per cui la decisione corretta cambierebbe da un quarto
all'altro:

| Posizione dell'offerta rispetto ai quattro prezzi | Gruppi | Assegnazione identica nei 4 quarti |
|---|---|---|
| sotto tutti e quattro (sempre in merito) | 40.125 (84,0%) | 99,8% |
| **a cavallo** | **877 (1,8%)** | **0,7%** |
| sopra tutti e quattro (mai in merito) | 6.776 (14,2%) | 100,0% |

Il 99,3% delle offerte a cavallo viene assegnato in modo diverso fra i quarti, esattamente
come prevede un clearing indipendente: **il mercato decide davvero quarto per quarto**. I sei
gruppi che si comportano diversamente valgono 4 MW per asta.

Entrambi i candidati indicati sono quindi da escludere. È un risultato negativo, ma chiude due
strade in modo pulito: il residuo va cercato altrove.

---

## 2026-08-04 — Creata la struttura LaTeX della tesi

Creata la cartella `latex/` con un documento modulare: `main.tex` contiene preambolo,
frontespizio segnaposto, indice ed elenco delle figure, e richiama con `\input{}` un file per
capitolo dalla sottocartella `capitoli/`. Aggiunti `bibliografia.bib` (vuoto, con l'elenco
commentato delle voci da reperire) e `latex/README.md` con le istruzioni di compilazione.

**Struttura dei capitoli** (sei capitoli, con le sezioni fissate dall'indice della tesi):
1. Introduzione e Contesto · 2. Il Mercato Elettrico Italiano · 3. Formulazione Teorica della
Strategia Ottima · 4. Simulazione e Analisi Pratica · 5. Valutazione Economica per gli
Investitori · 6. Conclusioni.

**Criterio di riempimento.** Dove il lavoro è stato fatto, il testo riporta contenuti e numeri
reali attinti da questo diario e dagli script, ciascuno riproducibile: il capitolo 2 descrive
il meccanismo d'asta, il periodo di mercato e le tipologie di offerta; il capitolo 4 contiene
il dataset (campi, granularità mista, unità di misura, stati delle offerte), la ricostruzione
delle curve con l'estratto di codice della funzione di clearing, il perimetro zonale con la
tabella dell'errore per variante, il blocco di scambio netto e i risultati della validazione
su gennaio 2025. Il capitolo 3 formalizza la funzione obiettivo con l'effetto di retroazione
e il modello fisico della batteria. Dove il lavoro non è ancora stato fatto — degrado,
incertezza, metriche finanziarie, analisi di sensitività, definizione degli scenari — ci sono
**23 segnaposto** marcati `% DA COMPLETARE`, ciascuno con l'indicazione di cosa andrà scritto.

**Scelte tecniche.** `listings` invece di `minted`, che richiederebbe Python e la compilazione
con `--shell-escape`; `biblatex` con backend biber; `textcomp` per il simbolo dell'euro,
perché il comando `\euro` non è definito di base e ne avrebbe fatto fallire la compilazione.
`\graphicspath` punta anche a `../output/figure/`, così i grafici prodotti dagli script si
includono senza doverli copiare.

**Compilazione: non verificata.** Sul sistema non è installata alcuna distribuzione LaTeX
(né pdflatex, né lualatex, né latexmk). Il documento va quindi compilato su Overleaf o dopo
aver installato MiKTeX. Per ridurre il rischio sono stati usati solo pacchetti di larga
diffusione ed è stato scritto un controllo statico che verifica ambienti chiusi, graffe
bilanciate, riferimenti con etichetta corrispondente e comandi personalizzati definiti: passa
senza segnalazioni su tutti e sette i file. Non sostituisce la compilazione, ma intercetta gli
errori più comuni.

---

## 2026-08-04 — Due campi del tracciato che avevo classificato male, e la chiusura del residuo

### Come sono emersi
La scomposizione esatta dell'errore sulla curva di offerta — contributi A (offerte in merito
mai assegnate), B (assegnate in parte) e C (fuori merito ma assegnate), la cui somma
riproduce lo scarto per identità contabile, verificata a 0,0000 MW — mostrava che, tolti i
blocchi e le zone di frontiera, restavano 151 MW per asta di offerte **della sola zona NORD**
incoerenti con il proprio prezzo. Cercandone la ragione ho riesaminato due campi che il
03/08 avevo annotato come "presenti nello schema ma assenti dai record": l'annotazione era
sbagliata, derivava dall'aver guardato solo i primi record del file.

### D-20 · `ADJ_QUANTITY_NO` è la quantità su cui l'asta si risolve
Quando la quantità rettificata differisce da quella offerta, la quantità assegnata coincide
con la **rettificata** in 199 casi su 200 (12/01/2026) e in 46 su 46 (15/01/2025), e non
coincide mai con quella offerta. Le curve usavano il campo sbagliato.

Sono poche righe — 348 su 123.785 — ma l'effetto è misurabile, perché si tratta di offerte
quasi tutte in merito. Su gennaio 2025, a parità di tutto il resto:

| Indicatore | Con `QUANTITY_NO` | Con `ADJ_QUANTITY_NO` |
|---|---|---|
| Match esatto (±0,01 €) | 44,5% | **49,7%** |
| Match entro ±1 €/MWh | 76,7% | **80,8%** |
| Deviazione standard | 1,65 | **1,43** |
| Scarto medio | −0,35 | **+0,04** |
| Scarto massimo | 15,88 | **11,20** |

Un effetto collaterale conferma la lettura: le offerte che risultavano "accettate solo in
parte" passano da 2,7 a 0,5 per asta, perché molte erano in realtà accettate per intero
sulla quantità rettificata. Sulle aste a quarto d'ora invece non cambia nulla (dev. standard
8,81 → 8,83): lì il problema è altrove.

Per non lasciare in giro cache incoerenti, `carica_giorno` ora rigenera automaticamente una
cache che non contenga tutte le colonne attese.

### `MINIMUM_ACCEPTANCE_RATIO`: ipotesi formulata e smentita
Il campo è valorizzato, e nel mercato a quarto d'ora riguarda volumi trentaquattro volte
maggiori che in quello orario (8.011 MW per asta contro 237). Sembrava il candidato ideale
per il residuo: è una forma di indivisibilità che può far rifiutare un'offerta in merito.

**È falso, ed è già contato.** La tabella di contingenza è perfettamente diagonale: su
123.785 righe della zona NORD, il campo è valorizzato su tutte e sole le 2.409 righe che sono
offerte a blocchi. Non è un meccanismo separato, è un attributo dei blocchi — che spiega
anche perché i blocchi siano indivisibili in modo più fine di quanto pensassi. Il contributo
al residuo, misurato al netto dei blocchi, è **zero MW**.

### D-19 · L'oscillazione dell'euristica sui blocchi, risolta
L'euristica non restituisce più l'ultima configurazione raggiunta. Fra tutte quelle visitate
scarta quelle con **accettazioni paradossali** — blocchi accettati che non coprono il proprio
prezzo, che il mercato reale non ammette — e fra le rimanenti sceglie quella con il
**surplus complessivo più alto**, che è la grandezza massimizzata dall'algoritmo d'asta.
Aggiunta a questo scopo `curve.surplus()`.

| Trattamento dei blocchi (672 aste a quarto d'ora) | Errore mediano | Dev. standard | Match ±1 € |
|---|---|---|---|
| come offerte semplici | 3,24 | 8,83 | 22,2% |
| esclusi | 29,36 | 36,08 | 0,3% |
| **iterativo, D-18 + D-19** | **2,52** | **5,40** | **28,3%** |
| con esito osservato (limite) | 2,29 | 5,01 | 31,4% |

L'euristica recupera ora l'86% della riduzione di dispersione ottenibile, contro il 13% della
versione precedente. Sulle aste
orarie raggiunge o supera di un soffio il limite (dev. standard 1,06 contro 1,07 dell'oracolo:
la selezione per surplus può scegliere una configurazione che si adatta meglio dell'esito
osservato, il che non è un paradosso ma il segno che le due soluzioni sono ormai equivalenti).

### Stato della ricostruzione, configurazione adottata
Perimetro NORD più frontiere confinanti, offerte in gara, tutte le granularità, quantità
rettificata, scambio netto simmetrico, clearing iterativo con blocchi.

| | Gennaio 2025 (744 aste orarie) | 12-18 gen 2026 (672 aste a quarto d'ora) |
|---|---|---|
| Prezzo ufficiale medio | 143,32 €/MWh | 136,14 |
| Prezzo ricostruito medio | 143,53 | 137,47 |
| Errore mediano | **0,00** | 2,52 |
| Deviazione standard | **1,06** | 5,40 |
| Match esatto (±0,01 €) | **52,3%** | 6,1% |
| Match entro ±1 €/MWh | **83,7%** | 28,3% |
| Match entro ±5 €/MWh | **99,5%** | 69,8% |
| Scarto massimo | **6,61** | 26,51 |

Rispetto al punto di partenza del 03/08 sulle aste orarie: match esatto dal 44,5% al 52,3%,
deviazione standard da 1,65 a 1,06, scarto massimo da 15,88 a 6,61 €/MWh.

### Attribuzione finale del residuo (aste a quarto d'ora)
Sui 990 MW per asta di scarto complessivo, i MW incoerenti si attribuiscono così:

| Causa | MW per asta | Quota |
|---|---|---|
| Offerte a blocchi (D-03) | 875,8 | 80,7% |
| Zone di frontiera senza vincoli di transito (D-10) | 76,6 | 7,1% |
| Offerte con quota minima di accettazione | 0,0 | 0,0% |
| **Non spiegato** | **132,8** | **12,2%** |

Il non spiegato è sceso a 133 MW per asta, cioè lo **0,74% del volume scambiato**. Le due
cause note sono entrambe semplificazioni già dichiarate e misurate, non errori.

---

## 2026-08-04 — `batteria.py`: profilo ottimo ed effetto di retroazione

Scritto `src/mgp/batteria.py` con quattordici test su casi calcolabili a mano.

### Le due parti
`profilo_ottimo()` risolve un programma lineare (HiGHS via scipy) che massimizza
$\sum_t p_t \Delta (s_t - c_t)$ sotto i vincoli di potenza, capacità e bilancio energetico,
con l'opzione di ciclo giornaliero chiuso. Il vincolo di non simultaneità $c_t s_t = 0$ non è
imposto perché renderebbe il problema non lineare: con rendimenti minori di uno e prezzi
positivi non è vincolante, ma può esserlo con prezzi negativi, e la funzione lo segnala.

`simula_giorno()` cerca il punto fisso fra profilo e prezzi: ottimizza sui prezzi correnti,
reinserisce carica e scarica nelle curve d'asta, ricalcola i prezzi, ri-ottimizza.

### D-21 · Il punto fisso può non esistere, e la ragione è economica
La batteria carica dove il prezzo è basso, ma **caricando lo alza**, e sul prezzo alzato non
converrebbe più caricare. Su un mercato in cui la batteria pesa molto la successione oscilla
fra due configurazioni e nessun punto fisso esiste.

Quando accade non si restituisce l'ultimo profilo raggiunto — dipenderebbe solo da dove si è
interrotta l'iterazione — ma quello con il **ricavo effettivamente realizzato** più alto, cioè
valutato ai prezzi che quel profilo stesso genera. Le due situazioni hanno però
interpretazioni economiche diverse, e nei risultati va detto quale vale: il punto fisso
descrive un operatore che **non internalizza** il proprio effetto sul prezzo (concorrenza fra
più operatori), la selezione per ricavo un operatore che lo **internalizza** (più vicino a un
monopolista dell'accumulo).

### Una lezione dai test
Tre test fallivano e ho cercato l'errore nel codice, mentre era nella **giornata di prova**:
l'equilibrio cadeva esattamente sullo spigolo fra due gradini della curva di offerta, quindi
qualunque quantità aggiunta spingeva il prezzo al massimo di mercato, e il comportamento
osservato era un artefatto della costruzione. Rifatta con gradini regolari e equilibrio a
metà gradino, così l'effetto atteso si calcola a mano: una batteria da 100 MW consuma un
gradino e sposta il prezzo di un passo.

Il test più importante verifica il meccanismo su cui poggia la tesi: **raddoppiando la taglia
il ricavo non raddoppia**, e il ricavo per MW installato scende, perché ogni gradino consumato
peggiora sia il prezzo di acquisto sia quello di vendita.

### D-22 · Previsione perfetta
Il profilo è ottimizzato conoscendo i prezzi di tutti i periodi della giornata. Il ricavo che
ne risulta è quindi un **limite superiore**, non un risultato conseguibile, e serve come
termine di confronto. Il trattamento dell'incertezza resta da impostare.

---

## 2026-08-04 — D-23 · Le righe bilaterali restano nelle curve

### La domanda
Le righe con `OPERATORE = "Bilateralista"` registrano contratti conclusi fuori dal mercato.
L'ipotesi era di escluderle dal clearing, sul presupposto che di quelle offerte non si
conosca il prezzo ma solo la quantità.

### Il presupposto non regge: un prezzo ce l'hanno
Sul giorno del 12/01/2026, zona NORD (12.422 righe bilaterali, il 10,5% delle righe e il
13,1% delle quantità):

| Lato | Prezzo minimo | Mediana | Massimo |
|---|---|---|---|
| Acquisto (`BID`) | 300 | **4.000** | 4.000 |
| Vendita (`OFF`) | 0 | **0** | 219 |

Sono cioè presentate ai **limiti di prezzo del mercato**: acquisto al massimo, vendita al
minimo. È la forma con cui si registra una quantità che deve essere collocata comunque, e il
55,4% delle righe ha prezzo esattamente zero. Non è un dato mancante: è la dichiarazione di
essere price taker.

### Si comportano in modo perfettamente coerente con l'asta

| | Righe | Incoerenti col prezzo di equilibrio | MW incoerenti per asta |
|---|---|---|---|
| Bilaterali | 12.422 | **1 (0,0%)** | 1 |
| Resto del mercato | 54.208 | 175 (0,3%) | 788 |

Nessuna bilaterale risulta assegnata pur essendo fuori merito, e il 98,9% di esse è
assegnato — esattamente ciò che ci si attende da offerte ai limiti di prezzo. Sono quindi
**già trattate correttamente** dalla ricostruzione, e non contribuiscono al residuo non
spiegato: la loro incoerenza vale 1 MW per asta contro i 788 del resto del mercato.

### La prova sperimentale

| Variante (aste a quarto d'ora, 288 aste) | Errore mediano | Dev. standard | Match ±5 € |
|---|---|---|---|
| bilaterali incluse (attuale) | **3,04** | **9,64** | **64,9%** |
| tolte dalle curve | 14,32 | 17,72 | 12,8% |
| tolte da curve e scambio netto | 3,23 | 9,69 | 63,9% |

| Variante (aste orarie, 72 aste) | Errore mediano | Dev. standard | Match ±5 € |
|---|---|---|---|
| bilaterali incluse (attuale) | 0,33 | **1,18** | **100,0%** |
| tolte dalle curve | 9,74 | 19,54 | 30,6% |
| tolte da curve e scambio netto | 0,23 | 1,42 | 97,2% |

Toglierle dalle sole curve è disastroso, ed è prevedibile: si rimuove il 13% delle quantità
da un lato senza riequilibrare l'altro. Toglierle anche dal calcolo dello scambio netto
riporta il risultato in pari, ma senza alcun guadagno — leggermente peggio su quasi tutti gli
indicatori.

### Decisione
**Le righe bilaterali restano nelle curve con il prezzo che dichiarano.** Escluderle non
migliora la ricostruzione e toglierebbe dal modello il 13% delle quantità realmente scambiate.

### Però l'intuizione dietro la domanda va tenuta
È vero che quelle righe non esprimono una disponibilità a pagare: sono contratti già decisi.
La conseguenza rilevante per la tesi non è sul clearing ma sull'**elasticità**: un ottavo
delle quantità è perfettamente rigido per costruzione, e si somma alla quota di domanda
presentata al prezzo massimo. Le curve sono quindi più ripide di quanto suggerirebbe il
numero di offerte, e questo amplifica l'effetto che una batteria produce sul prezzo. Va
richiamato quando si interpreteranno gli scenari di capacità.

---

## 2026-08-04 — Correzione: l'oscillazione dell'euristica non è sparita

Nella voce di oggi su D-19 avevo scritto che l'oscillazione dell'euristica sui blocchi
spariva, "0 giornate su 7 contro 4 su 7". **È sbagliato**, e la frase è stata rimossa.

L'errore è nell'indicatore, non nella misura. Contavo come oscillanti le giornate che
arrivavano al limite di iterazioni, criterio valido per la versione precedente. La nuova
versione però **esce appena rivede una configurazione già visitata**, quindi si ferma dopo
due o tre iterazioni anche quando oscilla: il conteggio delle iterazioni ha smesso di
misurare ciò che credevo misurasse.

Guardando il flag di convergenza, che è l'unico indicatore valido:

| Campione | Giornate con punto fisso | Senza punto fisso |
|---|---|---|
| Gennaio 2025, 31 giornate orarie | 29 | **2** |
| 12-18 gennaio 2026, 7 giornate a quarto d'ora | 1 | **6** |

L'oscillazione è quindi la norma nel mercato a quarto d'ora, dove i blocchi sono trenta al
giorno. Quello che D-19 ha cambiato non è la convergenza ma **cosa si fa quando non
converge**: prima si restituiva l'ultima configurazione raggiunta, che dipendeva solo da dove
si era interrotta l'iterazione; ora si sceglie fra quelle visitate con un criterio economico.
Il guadagno misurato — deviazione standard da 8,83 a 5,40 — resta valido, perché confronta i
prezzi ricostruiti, non la convergenza.

Le giornate senza punto fisso si ricostruiscono peggio delle altre (errore mediano 2,59
contro 1,67 sul campione a quarto d'ora), il che è coerente: sono quelle in cui la soluzione
d'asta è genuinamente più difficile da riprodurre.

Corretto anche lo script che riportava l'indicatore sbagliato, e aggiunta la colonna di
convergenza al report di validazione, così l'informazione sta nel documento e non solo nel
codice.

---

## 2026-08-04 — Script di validazione allineato alla configurazione adottata

`scripts/03_valida_mese.py` usava ancora il clearing che tratta i blocchi come divisibili,
mentre la configurazione adottata li tratta come indivisibili (D-18, D-19): i numeri di
validazione "ufficiali" non coincidevano con quelli della pipeline in uso. Ora lo script usa
la configurazione adottata e l'opzione `--blocchi-divisibili` riproduce la variante di
confronto. Aggiunte al report per giornata le colonne dei blocchi accettati e della
convergenza.

Validazione rieseguita, e i numeri coincidono ora con quelli dello script diagnostico:
gennaio 2025, 744 aste, errore mediano 0,00 €/MWh, deviazione standard 1,06, prezzo esatto nel
52,3% delle ore, entro 5 €/MWh nel 99,5%, scarto compreso fra -4,37 e +6,61.

---

## 2026-08-04 — L'impianto metodologico: la soglia stocastica price taker → price maker

Consolidata la domanda di ricerca e il disegno dello studio. Questa voce fissa l'impianto e
supera alcune decisioni precedenti.

### La domanda di ricerca
Non "quanto guadagna una batteria", ma **a partire da quale capacità aggregata installata
l'accumulo smette di essere price taker e diventa price maker**. La transizione non è un
punto ma un fenomeno graduale e aleatorio, perché dipende dalla forma delle curve d'asta, che
cambia di giorno in giorno. Va quindi caratterizzata come **soglia stocastica**: non un valore
puntuale ma una distribuzione, con la sua incertezza.

### La metrica: erosione di profitto
Per un giorno storico $d$ e una capacità aggregata $K$ si confrontano due profitti.

* $\pi_{PT}(d,K)$ — **price taker ingenuo**: il piano di carica e scarica è valorizzato ai
  prezzi storici, cioè come se l'accumulo non li muovesse. È quello che si aspetta un
  investitore che ottimizzi su una serie di prezzi passati.
* $\pi_{PM}(d,K)$ — **price maker**: lo stesso identico piano viene inserito nelle curve
  d'asta reali, si ricalcola l'equilibrio di ogni periodo e lo si valorizza ai prezzi nuovi.

L'**erosione** è la quota di profitto che l'accumulo distrugge da sé:

$$E(d,K) = \frac{\pi_{PT}(d,K) - \pi_{PM}(d,K)}{\pi_{PT}(d,K)}$$

Il piano è **lo stesso** nei due casi: la differenza misura solo l'effetto sul prezzo, non un
diverso comportamento. È la definizione che isola il fenomeno da studiare.

### Le quattro scelte fissate

**1. Scenario: tante batterie piccole non coordinate.** Il piano si ottimizza **una volta
sola** sui prezzi storici; non c'è riottimizzazione strategica né ricerca di un punto fisso.
L'equilibrio si ricalcola **una volta sola**, e solo per valorizzare.

La giustificazione è che nessun singolo operatore, essendo piccolo, ha ragione di anticipare
il proprio effetto sul prezzo: ciascuno ottimizza sul segnale di prezzo che osserva. Tutte le
batterie seguono lo stesso segnale, quindi i profili si sommano — è coordinamento **implicito
via prezzo comune**, non collusione. Questo rende legittimo trattare la capacità aggregata $K$
come un unico profilo, che è ciò che permette di simulare.

**2. Incertezza via bootstrap dei giorni storici.** I giorni si ricampionano con reimmissione
per costruire la distribuzione di $E(\cdot,K)$. La stocasticità sta **sulle curve d'asta
reali**, non su un processo di prezzo stimato: le batterie si inseriscono sempre su curve
effettivamente osservate.

**3. Soglia su un quantile prudenziale.** $K^*$ si definisce sul quantile della distribuzione
di $E(\cdot,K)$, non sulla media, perché ciò che conta per un investitore è il caso avverso
ragionevole, non quello tipico. Si usa l'**80° o il 90° percentile, non il 95° o il 99°**: in
coda la stima è instabile e con qualche centinaio di giorni un quantile estremo dipenderebbe
da pochissime osservazioni. Intervalli di confidenza via bootstrap.

**4. Stratificazione per stagione, anno o regime.** La soglia non è stazionaria: dipende dal
mix produttivo e dal livello dei prezzi, che cambiano fra stagioni e fra anni. Stratificare
serve a misurare quanto la soglia si muove, invece di mediare su condizioni disomogenee.

### Il caso dei giorni a basso spread
Quando $\pi_{PT} \approx 0$ l'erosione relativa esplode o è priva di senso. Scartare quei
giorni introdurrebbe però un **bias sistematico**: sono i giorni ad alta produzione
rinnovabile e basso differenziale, cioè proprio quelli che diventeranno più frequenti. La
scelta è quindi di **non scartarli** e di riportare accanto all'erosione relativa (%) anche
quella **in valore assoluto (€)**, che resta interpretabile a qualunque livello di spread.

### Alternative scartate

**Operatore unico con punto fisso fra profilo e prezzi** (era D-21). Descrive un monopolista
dell'accumulo che internalizza il proprio effetto e riottimizza fino alla convergenza. Non è
lo scenario di interesse: la domanda riguarda l'ingresso di molta capacità distribuita fra
operatori in concorrenza. In più il punto fisso spesso **non esiste** — la batteria carica
dove il prezzo è basso ma caricando lo alza — e nella versione implementata la successione
oscillava, obbligando a scegliere fra configurazioni con un criterio aggiuntivo. Lo scenario
non coordinato è insieme più aderente alla domanda e privo di quel problema. La funzione
resta nel codice come variante di confronto, chiaramente etichettata.

**Soglia definita sulla media dell'erosione.** Scartata: la media nasconde la coda, e la
decisione di investimento dipende dal caso avverso. Il quantile prudenziale è la scelta
naturale, con il compromesso sul livello discusso sopra.

**Modellazione stocastica delle curve come dati funzionali (FPCA).** Rappresentare le curve
d'offerta come funzioni aleatorie e simularne le componenti principali sarebbe elegante e
darebbe un modello generativo. Scartata per due ragioni: le curve sono a gradini con
discontinuità che le componenti principali lisciano proprio dove conta, cioè attorno
all'equilibrio; e introdurrebbe un errore di modello aggiuntivo laddove i giorni reali sono
già disponibili in numero sufficiente. Il bootstrap empirico usa le curve così come sono.

**Linearizzazione con elasticità locale.** Approssimare l'effetto sul prezzo con una pendenza
locale $\partial p / \partial q$ stimata attorno all'equilibrio sarebbe enormemente più
rapido. Scartata perché **si rompe proprio dove serve**: per $K$ grandi la batteria si sposta
lungo la curva di molti gradini, e la pendenza locale cessa di essere informativa. Le misure
già raccolte lo confermano: la sensibilità del prezzo è nulla in un quarto delle aste e
superiore ai 20 €/MWh per 100 MW in altre, quindi fortemente non lineare. Poiché la soglia
$K^*$ è per definizione il punto in cui l'effetto smette di essere trascurabile, usare
un'approssimazione valida solo per effetti piccoli sarebbe circolare.

### Limiti dichiarati
* **Reazione di secondo ordine non catturata.** Gli altri operatori non modificano le proprie
  offerte in risposta all'ingresso dell'accumulo. Nella realtà lo farebbero, e questo attenua
  o amplifica l'erosione in modo non prevedibile con questo impianto.
* **Aggiustamento intra-periodo non catturato.** Le batterie non ricontrattano la propria
  posizione dopo il MGP, mentre nella realtà opererebbero anche sui mercati infragiornalieri.
* **Zona NORD isolata.** I vincoli di transito non sono modellati esplicitamente e lo scambio
  con l'esterno è calibrato sull'esito osservato: si assume quindi che i flussi non reagiscano
  al prezzo che l'accumulo muove.
* **Stima in coda del quantile.** Anche all'80° o 90° percentile la stima dipende da un numero
  limitato di giorni; gli intervalli di confidenza bootstrap servono a renderlo esplicito.

---

## 2026-08-04 — Consolidamento su gennaio: tre controlli sui risultati, prima di estendere

Prima di allargare il campione si è verificato che i numeri ottenuti — soglia attorno ai
60 MW ed erosione oltre il 100% per capacità grandi — siano economia e non artefatti. Nessun
dato nuovo: solo controlli su quanto già calcolato.

### Controllo 1 · Le curve nei periodi estremi reggono

Scritto `src/mgp/grafici.py` e `scripts/07_ispezione_curve.py`. Ispezionate l'ora di minimo e
quella di picco di due giornate scelte per differenziale mediano (30/01) e massimo (20/01).

**La pendenza non dipende da poche offerte isolate.** Nella finestra di ingrandimento cadono
39-62 gradini di offerta; entro ±20 €/MWh dall'equilibrio ci sono 42-72 offerte di vendita per
3.500-5.500 MW, e la più grande vale 406-530 MW, cioè circa un decimo del totale locale.

**Le offerte ai prezzi limite non distorcono la regione rilevante.** Sono 13-14 per periodo e
stanno agli estremi della curva: il blocco a −500 €/MWh occupa i primi 2.000-4.500 MW, la
domanda price taker sta a 4.000 €/MWh. L'equilibrio è lontano da entrambi.

**L'equilibrio cade dove deve**: coincide col prezzo ufficiale al centesimo in tre periodi su
quattro; nel quarto lo scarto è 1,50 €/MWh, e il grafico mostra che lì la curva di offerta è
insolitamente piatta attorno all'incrocio, coerentemente con quanto già noto.

**Un fatto emerso dai grafici**: la curva di domanda è quasi verticale all'equilibrio in tutti
e quattro i periodi. L'effetto dell'accumulo passa quindi quasi interamente dalla curva di
offerta, il che spiega perché la pendenza di quest'ultima determini il risultato.

**La pendenza misurata** (variazione di prezzo iniettando potenza):

| Potenza | Scaricando | Caricando |
|---|---|---|
| 100 MW | 0,00 €/MWh | 0,00 / +0,34 |
| 500 MW | −3,6 / −5,8 | +0,4 / +6,0 |
| 1500 MW | −7,9 / −14,0 | +5,7 / +9,0 |

A 100 MW il prezzo spesso non si muove affatto, perché l'equilibrio cade in mezzo a un gradino
largo. È il primo indizio del punto che emerge nel controllo 3.

### Controllo 2 · Il profitto negativo è economia reale

Scritto `scripts/08_debug_erosione.py`, che traccia periodo per periodo prezzo di riferimento,
prezzo ricalcolato, quantità e contributo al profitto.

**Nessuna riottimizzazione nascosta.** Il controllo esplicito passa su tutte le capacità
ispezionate: il piano usato coincide con quello ottimo sui prezzi di riferimento. E a
1500 MW ottimizzare sui prezzi nuovi darebbe un piano **diverso**, il che conferma che la
distinzione fra lo scenario non coordinato e quello con riottimizzazione è sostanziale.

**Il meccanismo del profitto negativo**, 02/01/2025 con 1500 MW aggregati:

| | Prezzi di riferimento | Con la flotta |
|---|---|---|
| Prezzo medio nei periodi di carica | 125,31 | **139,85** |
| Prezzo medio nei periodi di scarica | 161,14 | **140,83** |

La flotta finisce per comprare a 141,56 €/MWh e vendere a 140,88: **ha annientato il
differenziale che stava sfruttando**, e sul residuo perde per il rendimento di ciclo (compra
11.302 MWh, ne rivende 10.200). Profitto price maker −162.921 € contro i +235.447 attesi,
erosione 169%.

È economia reale, e va trattato come risultato sostanziale: una flotta non coordinata che
ignora il proprio effetto non solo erode il margine, ma può distruggerlo del tutto e operare
in perdita. È esattamente la conseguenza dell'assenza di coordinamento, non un difetto del
calcolo.

**Un'ipotesi di artefatto verificata e scartata.** Si sospettava che l'erosione relativa fosse
dominata dal denominatore, cioè che i quantili alti fossero semplicemente le giornate a basso
differenziale. La correlazione fra differenziale giornaliero ed erosione relativa è però solo
−0,20 a 25 MW (−0,48 a 1500 MW), e soprattutto l'erosione **assoluta** varia di sessanta volte
fra le giornate: da 5,79 € a 362,82 € a parità di 25 MW installati. La variabilità è quindi
nelle curve, non nel denominatore, ed è la ragione per cui la soglia è stocastica: in certe
giornate l'equilibrio cade su un gradino stretto e pochi MW bastano ad attraversarlo, in altre
cade in mezzo a un gradino largo e 25 MW non spostano nulla.

### Controllo 3 · La griglia infittita, e un pavimento da correggere

Rifatto il calcolo con griglia da 1 a 6000 MW e passo fine in basso (22 valori). Nessuna delle
soglie cade più sul bordo: la stima principale passa da 61,4 a **59,7 MW**, praticamente
invariata, il che conferma che la griglia grossolana non la distorceva.

**Ma la griglia fine ha rivelato un problema.** Fra 1 e 15 MW l'erosione non cresce: resta
piatta attorno all'1-1,5% in mediana. Un effetto di mercato dovrebbe scalare con la capacità.

L'indagine mostra che a quelle capacità l'erosione non è uno spostamento graduale del prezzo:
a 1 MW il prezzo si muove in media in **1,5 periodi su una decina di periodi attivi**, e quando
si muove salta di 1,8-2,7 €/MWh, cioè di un gradino intero. Su una giornata non si muove
affatto. È l'effetto degli equilibri che cadono **esattamente sul bordo di un gradino**: pochi
megawatt bastano a farli scattare al gradino successivo.

Nel mercato vero questo non accade allo stesso modo, perché l'offerta marginale viene accettata
parzialmente e l'incrocio cade all'interno del gradino. È quindi un **artefatto della
ricostruzione a gradini**, non un fenomeno da misurare.

**Entità del pavimento** (erosione misurata a 1 MW): mediana 1,01%, 80° percentile 2,83%,
90° percentile 3,56%, massimo 5,20%.

**Correzione adottata (D-30).** Si sottrae, giorno per giorno, l'erosione misurata alla
capacità più piccola della griglia, che per costruzione non può essere effetto di mercato.
Effetto sulla soglia:

| Quantile e livello | K* lorda | K* netta |
|---|---|---|
| 90°, 5% | 14,9 MW | 34,1 MW |
| 90°, 10% | 59,7 MW | **73,1 MW** (67-120) |
| 90°, 20% | 206,2 MW | 229,3 MW |
| 80°, 10% | 101,3 MW | 119,8 MW |

Il pavimento sposta la stima principale del 22%, dentro l'intervallo di confidenza ma in modo
sistematico. Sulla soglia al 20% l'effetto è dell'11%, su quella al 5% è del 129%: **la soglia
al 5% non è utilizzabile**, perché il pavimento è comparabile alla soglia stessa. Lo script
ora segnala esplicitamente questa condizione.

La curva dell'erosione netta si comporta come deve: nulla a 1-2 MW e crescente da lì.

### Che cosa cambia nei risultati
La stima adottata per gennaio 2025 diventa **K\* = 73 MW, intervallo 67-120**, al 90° percentile
con soglia del 10%, al netto del pavimento. Resta un valore molto basso rispetto ai 15-25 GW
scambiati per asta, e la spiegazione confermata dal controllo 1 è che l'accumulo opera nelle
ore estreme, dove la curva è ripida, non nell'ora media.

---

## 2026-08-11 — Un lavoro pubblicato sulla stessa domanda: benchmark, non modello

Individuato uno studio che affronta la stessa domanda di ricerca su un altro mercato:

> Alonso-Perez, S. e Arcos-Vargas, A. (2026), *Storage deployment and its impact on
> wholesale electricity prices*, **Energy Reports** 15, 108991.

Studiano l'effetto dell'aggiunta di capacità di accumulo sui prezzi del mercato del giorno
prima **spagnolo** (dati OMIE 2024), confrontano strategie price taker e price maker e usano
le curve di offerta e domanda reali come proxy dell'elasticità. Trovano che il differenziale
si comprime al crescere della capacità fino a saturarsi, con soglie attorno a **15 e 32 GWh**.

*(Nota di servizio: i dati bibliografici sono trascritti come forniti e vanno verificati sulla
pagina dell'editore prima della consegna.)*

### Perché è un benchmark e non un modello da replicare

La differenza è nell'impianto, non nei dettagli.

**Il loro modello è deterministico e produce soglie puntuali**: un numero singolo, 32 GWh, che
descrive il giorno rappresentativo o la media del campione.

**Questa tesi stima una soglia stocastica**: non un numero ma una distribuzione, ottenuta per
bootstrap sui giorni storici (D-26), letta su un quantile prudenziale con intervalli di
confidenza (D-27) e stratificabile per stagione e regime (D-28). È esattamente ciò che quel
lavoro dichiara come proprio limite e come sviluppo futuro.

Il punto non è stilistico. Il controllo 2 del 04/08 ha mostrato che **a parità di 25 MW
installati l'erosione assoluta varia di sessanta volte fra le giornate del campione**, da 5,79
a 362,82 €. Una soglia puntuale su un campione simile descriverebbe una giornata che non
esiste. È la ragione per cui l'incertezza è il contributo, non un'aggiunta: il loro risultato
è il termine di paragone rispetto al quale mostrarlo.

**Conseguenza operativa: l'impianto stocastico resta intatto.** Non si converte nulla al loro
approccio. Di quel lavoro si prendono tecniche e parametri, che sono trasferibili, non il
disegno dello studio, che è ciò da cui questa tesi si differenzia.

### Che cosa è stato preso — parametri tecnici (D-32)

I parametri fisici dell'accumulo erano finora scelti da noi senza fonte: rendimenti 0,95 in
carica e 0,95 in scarica, costo variabile assente. Sono stati sostituiti con quelli dello
studio, che hanno il pregio di essere **citabili**, e centralizzati in `config.PARAMETRI_BESS`
con la fonte nel commento.

| Parametro | Prima | Ora | Effetto sul modello |
|---|---|---|---|
| Rendimento di ciclo | 0,9025 (0,95 · 0,95) | **0,92** (0,9592 per lato) | cambia il piano ottimo |
| Costo variabile | assente | **12 €/MWh**, sola scarica | cambia il piano ottimo, ed è il cambiamento maggiore |
| Durata | 4 ore | 4 ore | nessuno (conferma) |
| Cicli l'anno | — | 350 | nessuno sul LP giornaliero |

Due chiarimenti che hanno evitato altrettanti errori.

**«Potenza del convertitore pari al 25% della capacità» e «durata 4 ore» sono la stessa
affermazione**, perché $P = 0{,}25\,E \iff E/P = 4\text{h}$. Non è un parametro in più da
configurare: è una conferma indipendente di una scelta già fatta per altre ragioni.

**I 350 cicli l'anno non vanno nel programma lineare**, che è giornaliero: sarebbe un vincolo
annuale imposto a un modello che non vede l'anno. Il posto giusto è il calcolo economico del
capitolo 5. Corroborano però il vincolo di ciclo chiuso giornaliero, che ne implica 365: 350
è il 96% di quel valore, quindi l'assunzione di un ciclo al giorno non è eccentrica.

**Il costo si applica alla sola scarica**, così che un ciclo completo costi 12 €/MWh e non 24.
È una convenzione, dichiarata qui perché il raddoppio sarebbe un errore silenzioso.

### Che cosa è stato preso — la curva di impatto marginale

Implementata `curve.curva_impatto()`: la rappresentazione $\Delta\text{Prezzo} = f(\Delta Q)$
con l'origine centrata sul punto di clearing osservato del periodo. È la tecnica che gli autori
usano come proxy dell'elasticità, adottata qui come **strumento diagnostico** accanto — non al
posto — del ricalcolo esatto dell'equilibrio con cui si producono i risultati.

Una nota di implementazione. La curva non è ottenuta rifacendo il clearing a ogni punto della
griglia, ma **invertendo la curva di eccesso** già disponibile: aggiungere $Q$ di offerta price
taker trasla l'eccesso di $Q$ a ogni prezzo, quindi

$$p^*(Q) = \min\{p : S(p) - D(p) \ge -Q\}$$

Basta una costruzione dell'eccesso, già monotono, più una ricerca binaria per punto. Il
risultato è **esatto**, non approssimato, e un test lo verifica confrontandolo con il
ricalcolo esplicito via `aggiungi_import` su nove punti di griglia: senza quel test
l'affermazione resterebbe indimostrata.

Limiti scritti in docstring: è una diagnostica **per periodo** a curve fisse, che non rivaluta
le offerte a blocchi (D-18); e l'asse in energia usa la durata del periodo, quindi su PT15 un
MW vale 0,25 MWh.

### Che cosa NON è trasferibile

* **Le soglie di 15 e 32 GWh sono spagnole e del 2024.** Non vanno usate né come valore atteso
  né per calibrare la griglia di capacità. Per la zona NORD l'ordine di grandezza misurato è di
  decine-centinaia di MW (D-30), cioè **due ordini di grandezza più basso**. Entrano nel testo
  solo come confronto qualitativo.
* **I loro dati sono orari** (24 periodi al giorno), i nostri anche a quarto d'ora (96).
  Nessuna costante del progetto deve assumere 24 periodi; la conversione fra potenza ed energia
  passa sempre da `config.DURATA_ORE`.
* **Mercato e perimetro sono diversi**: OMIE/Spagna contro GME/Italia zona NORD con le
  frontiere confinanti.
* **L'orizzonte di ottimizzazione.** Gli autori misurano che 3 giorni catturano oltre il 99%
  del profitto ottenibile con 5. Il rendimento decrescente è quindi rapido, il che sostiene la
  giornata singola con ciclo chiuso adottata qui (D-22) come troncamento accettabile — ma
  resta un'estrapolazione dal loro mercato al nostro, e va tenuta come limite dichiarato, non
  come validazione.

### La conseguenza metodologica che il costo variabile porta con sé (D-31)

Un costo di 12 €/MWh è di fatto una **soglia sul differenziale**: sotto una certa ampiezza
l'arbitraggio non copre il degrado e il piano ottimo diventa *non fare nulla*, con carica e
scarica identicamente nulle.

Questo tocca D-29, che impone di **non scartare** le giornate a basso differenziale, perché
sono quelle ad alta produzione rinnovabile, cioè quelle destinate a diventare più frequenti.
Con il costo attivo, in quelle giornate $\pi_{PT} = 0$ **esattamente**, e l'erosione relativa
diventa $0/0$: indefinita, non semplicemente instabile.

**Decisione D-31**: quelle giornate restano nel campione con **erosione nulla per
definizione**. La motivazione è sostanziale e non di comodo: la flotta è ferma, quindi non
c'è profitto da erodere *e* non c'è alcun effetto sul mercato. Zero è la risposta corretta,
non un riempimento. Scartarle reintrodurrebbe esattamente il bias che D-29 vuole evitare.

Resta distinto il caso, già previsto da D-29, di un piano **non vuoto** con profitto irrisorio:
lì l'erosione relativa continua a non calcolarsi (NaN) e si riporta quella assoluta. Due test
separati fissano i due comportamenti, perché è la distinzione più facile da perdere in una
modifica futura.

### Il rerun di gennaio: la soglia si alza dell'86%

I parametri nuovi cambiano il piano ottimo, quindi tutti i risultati a valle. Gennaio 2025 è
stato ricalcolato sulla stessa griglia di 22 capacità; i risultati precedenti sono conservati
in `output/tabelle/_pre_D32/` come termine di confronto.

| | Prima (D-30) | Dopo (D-32) |
|---|---|---|
| **K\* al netto del pavimento** | 73,1 MW (67-120) | **136,0 MW (83-179)** |
| K\* lorda | 59,7 MW | 77,8 MW |
| Pavimento, mediana | 1,01% | 0,67% |
| Pavimento, 90° percentile | 3,56% | 2,76% |

**L'erosione cala a ogni capacità**, in modo sistematico e non marginale: da 5,85% a 4,68% in
mediana a 100 MW, da 39,9% a 32,0% a 800 MW, con riduzioni fra il 20 e il 30% su tutta la
griglia. Il pavimento scende in proporzione.

**Il meccanismo, verificato invece che dedotto.** Il costo di degrado rende la flotta più
selettiva: sfrutta solo i differenziali che lo ripagano, quindi cicla di meno e muove meno i
prezzi. Sul 15/01/2025, con 100 MW e quattro ore, il confronto diretto fra i due insiemi di
parametri dà

| | Energia scaricata | Cicli | Ore di scarica |
|---|---|---|---|
| Parametri vecchi (0,95/0,95, costo nullo) | 580 MWh | 1,45 | 6 |
| Parametri nuovi (0,92 rt, 12 €/MWh) | 500 MWh | 1,25 | 5 |

Meno energia immessa nel mercato significa meno effetto sul prezzo, quindi meno erosione,
quindi una soglia più alta. È un risultato con un contenuto economico, non un riassestamento
numerico: **tenere conto del costo di degrado sposta la soglia da 73 a 136 MW**, cioè quasi la
raddoppia. Un modello che ignora il degrado sovrastima l'aggressività dell'accumulo e
sottostima di conseguenza la capacità che il mercato può assorbire prima di risentirne.

**D-31 non si attiva mai in gennaio**: zero piani vuoti su 682 coppie (giorno, capacità). La
ragione è che il differenziale giornaliero minimo del mese è 37,8 €/MWh, ben sopra la soglia
di convenienza implicata da un costo di 12 €/MWh. La decisione è quindi implementata ma
**dormiente su questo campione**: diventerà operante sui mesi estivi e sulle giornate ad alta
produzione rinnovabile, che è esattamente il caso per cui è stata scritta. Va verificata di
nuovo quando il campione sarà esteso all'anno.

**Un'incoerenza minore, che vale la pena registrare.** Il modello produce in media 1,23 cicli
equivalenti al giorno, cioè circa 450 l'anno, contro i 350 del parametro di riferimento. Il
divario è coerente con l'ipotesi di previsione perfetta (D-22), che consente di cogliere ogni
occasione utile: 350 cicli l'anno è verosimilmente ciò che si ottiene operando su previsioni
imperfette. È un ulteriore indizio che il profitto price taker calcolato qui sia un limite
superiore, e va ricordato quando si passerà alle metriche finanziarie.

### Un difetto trovato aggiornando: la tabella di sensibilità era lorda

Nel controllare i numeri è emerso che `scripts/06_soglia_price_maker.py` calcolava la tabella
di sensibilità (quantile × livello) sull'erosione **lorda**, mentre la stima adottata nella
sezione precedente dello stesso report è **netta**. I valori riportati nel capitolo 5 della
tesi erano netti — calcolati a parte nella sessione del 04/08 — e quindi **non erano
riproducibili eseguendo lo script**, contro la regola che ogni numero citato debba esserlo.

Corretto: la tabella si calcola ora sulla colonna netta e affianca quella lorda come
confronto. Il controllo di coerenza è che la cella (90°, 10%) coincida con la stima adottata,
e ora coincide: 136,0 in entrambe.

| Quantile e livello | K\* netta | K\* lorda |
|---|---|---|
| 80°, 5% | 61,0 MW | 39,6 |
| 80°, 10% | 164,1 MW | 130,8 |
| 80°, 20% | 346,5 MW | 328,7 |
| 90°, 5% | 52,2 MW | 24,1 |
| **90°, 10%** | **136,0 MW** | 77,8 |
| 90°, 20% | 327,8 MW | 270,2 |

Il livello del 5% resta il meno affidabile — il pavimento al 90° percentile vale 2,76%, cioè
più della metà della soglia — ma il margine è ora meno stretto di prima (era 3,56% contro 5%).

---

## 2026-08-13 — Validazione del trimestre PT15 reale (ott-dic 2025) e diagnosi degli scarti

Colmata la lacuna dichiarata nel report dell'11/08: i numeri sulla ricostruibilità delle aste a
quarto d'ora venivano da **sette giorni del gennaio 2026**, non dal trimestre che entrerebbe
davvero nel campione. Ora il trimestre è validato per intero: **92 giorni, 8.836 aste**.

### Accuratezza misurata

| | Gen 2025 orario | 7 gg gen 2026 PT15 | **Ott-dic 2025 PT15** | ott | nov | dic |
|---|---|---|---|---|---|---|
| Periodi | 744 | 672 | **8.836** | 2.980 | 2.880 | 2.976 |
| Errore mediano | **0,00** | 2,52 | **2,16** | 2,81 | 2,08 | 1,82 |
| Deviazione standard | **1,06** | 5,40 | **5,42** | 6,52 | 5,06 | 4,41 |
| Prezzo esatto (±0,01) | **52,3%** | 6,1% | **12,5%** | 11,1% | 13,8% | 12,6% |
| Entro ±1 €/MWh | **83,7%** | 28,3% | **33,6%** | 29,6% | 35,1% | 36,2% |
| Entro ±5 €/MWh | **99,5%** | 69,8% | **73,7%** | 66,6% | 75,5% | 79,2% |
| Scarto minimo/massimo | −4,4 / +6,6 | −26,5 / +24,3 | **−30,0 / +35,5** | −29,2 / +35,5 | −30,0 / +31,5 | −25,4 / +26,9 |

**I sette giorni di gennaio 2026 erano una proxy pessimistica ma onesta**: il trimestre reale si
ricostruisce leggermente meglio su tutti gli indicatori di match, con deviazione standard
praticamente identica. La frase del report va quindi completata, non corretta al ribasso.

C'è un **miglioramento mensile monotono** — errore mediano da 2,81 a 1,82, deviazione standard
da 6,52 a 4,41 — compatibile con un mercato che si assesta dopo il passaggio del 1° ottobre, ma
si vedrà più avanti che la spiegazione probabile è un'altra.

**Il divario con l'orario resta di un ordine di grandezza**: il prezzo esatto passa dal 52,3% al
12,5% e lo scarto massimo da 6,6 a 35,5 €/MWh.

### Una lezione metodologica sul campionamento

Per anticipare il quadro mentre girava il calcolo completo (4,5 minuti per giorno, ~7 ore) è
stato costruito un **campione stratificato di 12 giorni**, quattro per mese, distanziati di otto
giorni per variare il giorno della settimana. Dava un errore mediano di 1,83 contro il 2,16
vero, e soprattutto sui giorni di ottobre dava 2,00 contro il 3,75 dei primi sedici giorni reali.

**Il campione aveva pescato giornate migliori della media** e non conteneva nessuna delle
giornate peggiori (07/10, errore mediano 7,04). Con dodici giorni su novantadue, su una grandezza
tanto dispersa, non c'era modo di accorgersene se non confrontando. Da ricordare: su questo dato
i campioni piccoli non sono affidabili nemmeno per l'ordine di grandezza.

### I casi peggiori non sono patologie isolate

L'errore mediano giornaliero si distribuisce con continuità: minimo 0,60, decimo percentile
1,01, mediana 2,23, novantesimo percentile 3,85, massimo 7,04. **Non esiste un gruppo di
giornate anomale separabile dal resto**: la peggiore ricostruibilità del PT15 è diffusa. Non
esiste quindi un filtro sui giorni che recuperi la qualità dell'orario, il che è rilevante per la
decisione sul perimetro temporale.

### Diagnosi: quattro ipotesi messe alla prova, due scartate

**Congestione — effetto reale ma modesto.** I periodi congestionati hanno errore mediano 2,62
contro 2,00, e la correlazione fra spread zonale ed errore è **0,177**. Il trimestre è molto più
congestionato di gennaio 2025 (32,4% dei periodi contro 17,9%), e l'ordine mensile della
congestione (52, 22, 19 periodi su 96) coincide con quello dell'errore. Contribuisce, ma non è
il fattore dominante: fra i giorni meglio ricostruiti ce ne sono con 82 e 88 periodi congestionati
su 96.

**Offerte a blocchi — l'attribuzione in MW si conferma, ma non spiega la variabilità.** Qui
vanno tenute distinte due domande che è facile confondere.

*Quanti MW di incoerenza sono attribuibili ai blocchi?* L'attribuzione formale, rifatta su sei
giornate rappresentative del trimestre, **riproduce quella di gennaio 2026**:

| Causa | Trimestre ott-dic 2025 | 7 gg gen 2026 |
|---|---|---|
| Offerte a blocchi (D-03) | 863,8 MW/asta — **79,2%** | 80,7% |
| Zone di frontiera senza vincoli (D-10) | 66,6 MW — 6,1% | 7,1% |
| Offerte con quota minima di accettazione | 0,0 MW — 0,0% | 0,0% |
| **Non spiegato** | **159,9 MW — 14,7%** | 12,2% |

Il residuo non spiegato sale da 133 a 160 MW per asta, ma le proporzioni tengono: **la
scomposizione è confermata sul trimestre reale.**

*I blocchi spiegano però quali aste sbagliano di più?* No. La correlazione fra numero di blocchi
ed errore è **0,057**, cioè nulla, benché i blocchi passino da 5,2 a 28,8 per asta. E il
confronto con l'esito vero, che il dato contiene (`STATUS_CD` dice se ogni blocco è stato
accettato), non mostra alcuna relazione:

| Giorno | Errore mediano | Quota accettata vera | Quota accettata dall'euristica |
|---|---|---|---|
| 07/10 (peggiore) | 7,04 | 69,3% | 75,0% |
| 31/12 | 5,53 | 45,8% | 45,5% |
| 18/11 (migliore) | 0,60 | 55,1% | 68,0% |
| 23/10 | 0,68 | 54,0% | 43,8% |

Il giorno peggiore accetta **più** blocchi del vero, uno dei migliori ne accetta meno. I blocchi
determinano quindi il **livello** dell'incoerenza, non la sua **variazione** fra aste: la
distinzione conta, perché è quest'ultima che rende inutilizzabile un filtro sui giorni.

Per completezza è stato ricontrollato anche il candidato "vincoli fra quarti d'ora consecutivi":
il 79,2% delle unità ha quantità assegnata identica nei quattro quarti dell'ora, praticamente lo
stesso 80,3% già misurato il 04/08 e già **riconosciuto come artefatto** — un'offerta lontana dal
margine viene accettata in tutti e quattro i quarti comunque. L'esclusione di allora, basata sul
test discriminante delle offerte a cavallo, resta valida e non va riaperta.

**Mancata convergenza dell'euristica** — il 42,4% dei periodi non raggiunge un punto fisso
(a gennaio 2025 convergevano 29 giornate su 31). L'errore è però solo lievemente peggiore dove
non converge (2,39 contro 2,04): è un sintomo di un problema più difficile, non la sua causa.

**Escursione del prezzo dentro l'ora — il fattore dominante sulla dispersione.** È la
correlazione più alta trovata, **0,427**, e l'effetto è forte:

| Quintile di escursione intra-oraria | Escursione media | Errore mediano |
|---|---|---|
| 1 | 1,85 €/MWh | 1,01 |
| 3 | 10,31 | 2,16 |
| 5 | 32,74 | **5,00** |

Nelle 48 ore in cui il prezzo ufficiale è **costante** nei quattro quarti l'errore mediano scende
a 1,00 e il prezzo esatto sale al 30,2%, contro 2,19 e 12,1% nelle altre.

La conferma più netta viene dal **pattern per quarto d'ora**. Sull'insieme dei dati l'errore ha
una forma a U — primo e ultimo quarto peggiori (2,56 e 3,16 contro 1,63 e 1,66) — che
**scompare** nelle ore a prezzo piatto (1,34 · 1,04 · 0,94 · 0,81, monotona). La U è quindi un
artefatto della rampa, non una proprietà della posizione nell'ora.

### Il bias è una cosa diversa dalla dispersione, e ha un'altra causa

L'errore **non è rumore simmetrico**: lo scarto medio è **+1,71 €/MWh** e il 59,2% dei periodi ha
il prezzo ricostruito **sopra** l'ufficiale contro il 28,4% sotto. A gennaio 2025 il bias era
+0,22. Sistematicamente **manca offerta**.

Il punto analitico importante: il bias **non** dipende dall'escursione intra-oraria (per quintile
vale 1,63 · 1,85 · 1,65 · 1,79 · 1,61, cioè piatto). Dispersione e bias hanno quindi cause
**distinte**, e vanno trattate separatamente.

Il bias dipende invece fortemente dal **livello del prezzo**, con correlazione **−0,378** e
andamento monotono:

| Quintile di prezzo ufficiale | Prezzo medio | Bias |
|---|---|---|
| 1 | 88,37 €/MWh | **+4,61** |
| 3 | 112,32 | +1,54 |
| 5 | 148,50 | **−0,89** |

Cioè: **ai prezzi bassi si sovrastima, ai prezzi alti si è quasi in bolla.** Per ora del giorno
il bias culmina a mezzogiorno (+4,85 alle 13, +4,45 alle 14) e si annulla alle 8-9 e alle 17-19.

**Ipotesi solare, formulata e scartata.** Sembrava naturale attribuire il picco di mezzogiorno a
produzione fotovoltaica non rappresentata — per esempio le offerte integrative GSE. Ma lo stesso
picco compare nei sette giorni del **gennaio 2026** (+2,26, +3,38, +3,79 alle 13-15), che sono
invernali e con poco solare, mentre è assente nel **gennaio 2025 orario** (+0,59, +0,46, +0,44).
Il discriminante è quindi la **risoluzione temporale, non la stagione**. Per completezza: nel
nostro archivio i file `MGP_OfferteIntegrativeGrtn` **non sono presenti**, quindi l'ipotesi non è
comunque verificabile senza scaricarli.

**Un confondimento da non trascurare.** Il prezzo medio di gennaio 2025 è 143,32 €/MWh, quello
del trimestre 112-118. Poiché il bias cresce al calare del prezzo, **parte del divario fra orario
e quarto d'ora potrebbe essere un effetto del livello dei prezzi e non della risoluzione.** I due
effetti non sono separabili con i dati attualmente validati.

### Il test del confondimento: è la risoluzione, non il livello dei prezzi

Il dubbio era serio: poiché il bias cresce al calare del prezzo e il trimestre ha prezzi molto
più bassi di gennaio 2025 (115,3 contro 143,3 €/MWh), il divario fra le due risoluzioni poteva
essere in tutto o in parte un effetto del **livello dei prezzi**.

Test eseguito: validare una finestra **oraria a prezzi bassi** — 15-22 aprile 2025, 192 aste,
che include il weekend di Pasqua con domanda bassa e fotovoltaico alto. Il prezzo medio risulta
101,1 €/MWh, cioè **più basso del trimestre a quarto d'ora**. È quindi il controllo giusto.

| | Prezzo medio | Errore mediano | Dev. std | Bias | Prezzo esatto |
|---|---|---|---|---|---|
| Gennaio 2025, orario | 143,3 €/MWh | 0,00 | 1,06 | +0,22 | 52,3% |
| **Aprile 2025, orario** | **101,1** | **0,17** | **1,49** | **+0,63** | **42,2%** |
| Ott-dic 2025, quarto d'ora | 115,3 | 2,16 | 5,42 | +1,71 | 12,5% |

**Il confondimento è escluso.** A prezzi più bassi di quelli del trimestre, il mercato orario si
ricostruisce con errore mediano 0,17 e deviazione standard 1,49, contro 2,16 e 5,42: un ordine
di grandezza di differenza che il livello dei prezzi non spiega.

Esiste un effetto del livello dei prezzi, ma è **piccolo**: fra gennaio e aprile il bias passa da
+0,22 a +0,63 e il prezzo esatto scende dal 52,3% al 42,2%. È circa un terzo del divario
osservato col quarto d'ora, e va nella stessa direzione — quindi qualcosa contribuisce, ma la
causa dominante resta la risoluzione temporale.

Due conferme dentro il campione di aprile. Il bias **non** cresce ai prezzi bassi (per quintile:
+0,36 a 60 €/MWh, +1,09 a 115, +0,30 a 136 — nessun andamento monotono), e le giornate a prezzo
più basso, 82-89 €/MWh, hanno il bias **minore** (+0,20 e +0,21). E il bias di mezzogiorno, che
nel PT15 arriva a +4,85, in aprile resta fra +0,69 e +1,25 nonostante il fotovoltaico sia al
massimo.

**Conseguenza per la scelta del perimetro**: il quarto d'ora è davvero il fattore, e l'ipotesi
che il divario fosse un artefatto stagionale o di livello dei prezzi va abbandonata. L'opzione
dei dodici mesi omogenei in regime orario ne esce rafforzata.

**Conseguenza per la diagnosi**: la relazione fra bias e livello del prezzo osservata dentro il
trimestre **non è un effetto del prezzo in sé** — altrimenti si vedrebbe anche in aprile. È
verosimilmente un indicatore indiretto di qualcos'altro che nel PT15 si concentra nelle ore a
prezzo basso, cioè quelle di massima rampa solare. La causa ultima resta aperta.

### Che cosa resta aperto

Le due ipotesi rimaste per il bias, entrambe da verificare: il **blocco di scambio netto** — che
entra al prezzo minimo e il cui bias cresce con l'import (da +0,84 a +2,73 fra il primo e
l'ultimo quintile) — e una **quota di offerta a basso prezzo non rappresentata**, di cui le
offerte integrative GSE sono il candidato più concreto, non presenti nell'archivio attuale.

---

## 2026-08-13 — Diagnosi del bias PT15: l'ipotesi GSE/CIP6 va abbandonata, è un ritardo

Indagine sull'ipotesi che il bias positivo del trimestre PT15 nasca da offerta a buon mercato
mancante nelle curve — rinnovabile incentivata collocata dal GSE (CIP6 o ritiro dedicato).

### Il dato ufficiale non è scaricabile senza utenza GME

Il `Legend.txt` dell'archivio elenca i nomi veri dei dataset, che non coincidono con quelli
ipotizzati:

* **`MGP_DomandaOfferta`** — curva aggregata di domanda e offerta;
* **`MGP_CurvaOfferte15m`** — la stessa **a 15 minuti**, che è quella pertinente al trimestre;
* **`MGP_OfferteIntegrativeGrtn`** — le offerte integrative GSE.

Nessuno dei tre è presente in locale: l'archivio contiene solo `MGP_OffertePubbliche` (4.083
giorni) e `MB_OffertePubbliche` (1.186).

Le API GME esistono e rispondono (`https://api.mercatoelettrico.org/request`, interfacce
`/api/v1/Auth`, `/api/v1/RequestData`, `/api/v1/GetMyQuotas`) ma **richiedono username e password
assegnati da GME**, con token JWT nell'header. Senza utenza non sono utilizzabili, e il download
dal sito è dietro accettazione delle condizioni con contenuto caricato via JavaScript.

Dal manuale tecnico si ricavano però due informazioni che cambiano le aspettative su quel
percorso. I dataset che servirebbero a confermare l'ipotesi — **`ME_Cip6`** (FlowDate, Hour 1-25,
Zone, Volumes) e **`ME_AdditionalDemand`** (FlowDate, Hour, Zone, Type, Quantity) — sono
**orari** e contengono **solo quantità, senza prezzo**. Anche disponendo delle credenziali non
direbbero *a quale prezzo* quell'energia si colloca sulla curva, che è l'informazione decisiva.
`ME_DemandAndSupply` ha invece un campo `Period` 1-100, quindi copre il quarto d'ora.

### La domanda è stata comunque risolta, per inversione

Non serve la curva ufficiale per misurare quanta offerta manca. Poiché l'eccesso $S(p)-D(p)$ è
monotono, esiste una sola quantità price taker che porta il prezzo ricostruito su quello
ufficiale:

$$Q^* = \min\{Q : p^*(Q) \le p_{\text{ufficiale}}\}$$

Si calcola con `curve.curva_impatto()` (D-32), che inverte l'eccesso ed è esatta. Sui periodi a
forte bias:

| Giorno · periodo | Ora | Ricostruito | Ufficiale | Bias | Deficit | % del volume |
|---|---|---|---|---|---|---|
| 06/10 · 52 | 13 | 87,70 | 56,89 | +30,81 | 2.550 MW | 13,4% |
| 25/10 · 49 | 13 | 60,00 | 34,00 | +26,00 | 580 MW | 3,4% |
| 21/11 · 44 | 11 | 160,00 | 143,03 | +16,97 | 1.230 MW | 4,8% |
| 27/12 · 49 | 13 | 92,90 | 68,62 | +24,28 | 1.240 MW | 8,4% |
| 18/11 · 50 *(controllo)* | 13 | 114,00 | 111,02 | +2,98 | 1.200 MW | 5,5% |

Il controllo è istruttivo: una giornata **ben** ricostruita richiede 1.200 MW quanto le
distorte, perché lì la curva è piatta. **Il deficit in MW non è proporzionale al bias**: dipende
dalla pendenza locale. Figura in `output/figure/09_deficit_offerta_pt15.png`.

### Il profilo giornaliero falsifica l'ipotesi GSE

Il test discriminante è la forma del deficit nella giornata: se fosse fotovoltaico incentivato
dovrebbe essere una campana, nulla di notte e massima a mezzogiorno. Calcolato su tutti i 96
periodi di quattro giornate:

| Fascia | Deficit medio |
|---|---|
| Notte (1-5, 24) | **367 MW** |
| Mezzogiorno (11-15) | **898 MW** |
| Rapporto | 2,45 |

Una componente diurna esiste, ma **il deficit non si annulla di notte**, e il rapporto 2,45 è
molto lontano da quello che produrrebbe il fotovoltaico.

Il fatto decisivo è però un altro: **alle 8-9 e alle 19-20 il bias è negativo** — −7,0, −9,6,
−4,6, −10,2 €/MWh — cioè in quelle ore la ricostruzione ha *troppa* offerta, non troppo poca.
**Nessuna quantità di rinnovabile mancante può produrre un errore di segno opposto.** L'ipotesi
di offerta mancante, in quanto spiegazione principale, è falsificata.

Anche l'ipotesi alternativa dello scambio netto esce indebolita: la correlazione fra deficit e
blocco price taker dell'import è solo **+0,170**.

### Che cos'è davvero: un ritardo rispetto alla rampa

Il segno dell'errore segue la **direzione in cui il prezzo si sta muovendo**. Sull'intero
trimestre la correlazione fra bias e gradiente del prezzo ufficiale è **−0,470**, la più forte
misurata finora, e l'andamento è monotono:

| Direzione del prezzo | Periodi | Bias medio | Quota di bias positivi |
|---|---|---|---|
| Forte discesa | 1.708 | **+5,13** | 81,0% |
| Discesa | 1.861 | +2,41 | 71,0% |
| Piatto | 2.115 | +1,69 | 61,8% |
| Salita | 1.451 | +1,17 | 48,7% |
| Forte salita | 1.609 | **−1,99** | 31,3% |

**Quando il prezzo scende la ricostruzione resta troppo alta; quando sale resta troppo bassa.**
È la firma di un **ritardo**, non di una componente mancante: la curva ricostruita insegue il
mercato con inerzia.

Due controlli qualificano il risultato. Il fenomeno è **assente nel mercato orario**: su gennaio
2025 la pendenza è −0,001 con correlazione −0,016, cioè nulla. E **non è mediato dal numero di
blocchi**: dividendo il trimestre in terzili per blocchi in gara la pendenza resta identica
(−0,321, −0,292, −0,320), quindi non è la quantità di blocchi a governarlo.

### Perché questo riconcilia tutte le osservazioni precedenti

Il ritardo spiega ciò che finora erano indizi slegati: l'escursione **dentro l'ora** come miglior
predittore della dispersione; la forma a U per quarto d'ora che scompare nelle ore piatte; la
correlazione con il livello del prezzo, che è indiretta perché i prezzi bassi cadono a
mezzogiorno, quando il prezzo sta scendendo più rapidamente; e il fatto che i blocchi spieghino
il 79% dei MW incoerenti pur non predicendo quali aste sbaglino.

Il meccanismo candidato è che una parte dell'offerta sia **costante su una finestra di più
periodi** mentre il mercato vero si muove dentro quella finestra: le offerte orarie, che entrano
identiche in tutti e quattro i quarti (D-13, il 6-8% dei MW), e le offerte a blocchi, che sono
indivisibili su tutta la loro estensione e vengono decise sul prezzo medio ponderato (D-18). In
un mercato orario nessuna delle due crea disallineamento, perché il periodo coincide con l'ora.

### L'esperimento sul meccanismo: un'esclusione netta e un test fallito

Rieseguito il clearing su quattro giornate (380 periodi) in tre varianti. È un esperimento
diagnostico, non una modifica della configurazione adottata.

| Variante | Errore mediano | Bias medio | Pendenza | Correlazione |
|---|---|---|---|---|
| A · configurazione adottata | 4,24 | +4,66 | −0,345 | −0,446 |
| B · senza offerte di granularità minoritaria | **38,28** | **+105,97** | +0,719 | +0,048 |
| C · blocchi trattati come divisibili | 5,18 | +1,50 | −0,386 | −0,401 |

*(riferimento: gennaio 2025 orario ha pendenza −0,001 e correlazione −0,016)*

**I blocchi sono esclusi come veicolo.** Trattarli come divisibili lascia il ritardo dov'era —
pendenza −0,386 contro −0,345 — nonostante cambi sensibilmente il bias medio. Qualunque cosa
produca il ritardo, non è l'indivisibilità dei blocchi.

**La variante B non è interpretabile**, ed è un difetto del disegno che va ammesso: togliere le
offerte orarie non rimuove la loro *piattezza*, rimuove il 7-12% dell'offerta reale. Il risultato
è una ricostruzione distrutta, con bias di +106 €/MWh. La correlazione che si annulla non
significa nulla, perché non c'è più una ricostruzione sensata di cui misurare il ritardo.

### Il test osservativo, che invece funziona

L'ipotesi sulle offerte orarie va verificata senza rimuoverle: confrontando giornate con quote
diverse. Se la piattezza infra-oraria delle offerte PT60 genera il ritardo, i giorni con più
offerta oraria devono ritardare di più.

Sui 92 giorni del trimestre, con quota di MW offerti in PT60 fra il 7,1% e il 12,5%:

| Terzile | Quota PT60 | Pendenza | Errore mediano |
|---|---|---|---|
| Poca PT60 | 8,7% | −0,293 | 2,04 |
| Media | 9,8% | −0,309 | 2,61 |
| Molta PT60 | 10,8% | **−0,355** | 2,75 |

Correlazione complessiva **−0,410**: più offerta oraria, più ritardo. E il risultato **non è
confondimento stagionale**, perché la quota di PT60 non varia fra i mesi (9,52%, 10,07%, 9,80%) e
la correlazione tiene dentro ciascun mese: **−0,385** a ottobre, **−0,396** a novembre,
**−0,444** a dicembre.

### Dove siamo con la diagnosi

Il quadro è di **identificazione parziale**, e va riportato come tale.

*Stabilito*: l'errore è un ritardo rispetto alla rampa di prezzo, assente nel mercato orario;
non è offerta mancante (cambia segno); non è l'indivisibilità dei blocchi (esclusa
sperimentalmente); non è lo scambio netto in modo prevalente (correlazione +0,170).

*Indiziato*: le offerte orarie che entrano identiche nei quattro quarti (D-13). L'associazione è
solida e replicata in tre mesi indipendenti, ma la quota in gioco è modesta — attorno al 10% dei
MW — e l'effetto fra terzili è del 20% sulla pendenza. **Contribuiscono, ma difficilmente
spiegano tutto il ritardo.**

*Aperto*: la parte restante. Un candidato non ancora esaminato è il **blocco di scambio netto**,
che è ricalcolato per periodo ma sulle quantità assegnate, cioè su un esito che a sua volta
riflette vincoli infra-orari; la sua correlazione col deficit era però bassa.

Poiché la configurazione adottata resta la migliore fra quelle provate, e poiché il fenomeno è
**assente nel regime orario** su cui poggia l'analisi principale, questo residuo non blocca il
lavoro sulla soglia: va dichiarato come limite noto della ricostruzione a quarto d'ora.

**Conseguenza pratica**: scaricare CIP6 e offerte integrative GSE **non è più prioritario**. Non
spiegherebbero un errore che cambia segno con la rampa, e i due dataset sono comunque orari e
privi di prezzo.

---

## 2026-08-13 — Secondo riferimento in letteratura: Veenstra e Mulder nei capitoli

Integrato nei capitoli LaTeX un secondo lavoro di riferimento, come materiale di scrittura e
posizionamento. **Nessuna modifica al codice**: la pipeline è invariata.

> Veenstra e Mulder (2025), *Profitability of batteries in day-ahead and intraday electricity
> markets: Assessment of operation strategies with endogenous prices*, **Energy Economics**
> 148, 108608.

Valutano la redditività dell'accumulo in arbitraggio sui mercati olandesi del giorno prima e
infragiornalieri, ricostruendo i **prezzi in modo endogeno dalle curve d'asta reali** e
confrontando strategie price taker e price maker su dati 2006-2023. Il modello è deterministico
(complementarità mista risolta sulle condizioni di ottimo, in GAMS).

*(Come per il riferimento spagnolo, dati bibliografici e valori numerici sono trascritti come
forniti e vanno verificati sulla pagina dell'editore. I nomi di battesimo degli autori sono
rimasti da completare invece che inventati.)*

### Perché conta più del primo riferimento

È **metodologicamente il più vicino** a questa tesi: stesso impianto di prezzi endogeni
ricostruiti dalle curve reali, stesso confronto price taker/price maker. E soprattutto
**legittima la domanda di ricerca**: gli autori osservano che l'ipotesi di price taker è
ragionevole finché l'accumulo ha un ruolo marginale, ma cessa di valere man mano che se ne
installa di più — cioè esattamente la transizione che qui si vuole caratterizzare.

Anche il loro modello è però **deterministico**. Entrambi i riferimenti principali condividono
quindi lo stesso limite, e l'elemento di differenziazione — la soglia come distribuzione
stimata per bootstrap, con quantile prudenziale e intervalli di confidenza — resta intatto.

### I quattro inserimenti

**Capitolo 1** (`sec:obiettivi`): il paper accanto al benchmark spagnolo, con il punto sulla
legittimazione della domanda di ricerca e la constatazione che entrambi sono deterministici.

**Capitolo 4** (`sec:setup`): giustificazione teorica della scelta di costruire le curve dalle
**offerte** anziché dal merit order degli impianti. L'argomento è loro: sul breve periodo la
relazione fra merit order tecnico e offerte presentate è debole, perché un'offerta non
corrisponde a uno specifico impianto (portafogli, impianti virtuali, rivendite). Ne segue che il
merit order descrive il sistema fisico ma non la curva su cui il prezzo si forma — e poiché qui
si studia proprio come l'accumulo sposta il prezzo, la rappresentazione pertinente è quella
delle offerte. Finora quella scelta era motivata solo per disponibilità del dato.

**Capitolo 4** (`sec:esecuzione`): confronto di accuratezza con la letteratura.

**Capitolo 6** (`sec:sintesi`): la loro conclusione che l'arbitraggio si satura, e che anche con
volatilità alta e costi ridotti del 60% resterebbe poco spazio per nuova capacità profittevole.
Riportata **come risultato della letteratura**, non come risultato di questo lavoro, con
l'osservazione che l'erosione crescente fino al profitto negativo (D-30, sezione
sull'autodanno) è a sua volta una forma di saturazione. Il confronto quantitativo è marcato
`% DA COMPLETARE` in attesa del campione annuale.

### Una correzione a come il confronto di accuratezza andava presentato

L'intenzione iniziale era riportare i loro numeri "a fronte della mia accuratezza, migliore".
Il confronto però non è a favore su entrambe le metriche:

| | Veenstra e Mulder (giorno prima, 2023) | Gennaio 2025, orario |
|---|---|---|
| Prezzo esatto | 32% | **52,3%** |
| Entro ±1 €/MWh | **88%** | 83,7% |

**Si coglie il prezzo esatto più spesso, ma si è leggermente meno accurati entro un euro.** Nel
capitolo è scritto così, dichiarando entrambe le metriche: presentarlo come superiorità
generica sarebbe stata un'affermazione falsa su un lavoro pubblicato, cioè il tipo di cosa che
un revisore verifica per primo. Il confronto è comunque inquadrato come non omogeneo — mercati,
anni e perimetri diversi — quindi come ordine di grandezza e non come classifica.

---

## 2026-08-13 — Diagnostica dei prezzi negativi: nessuno nei campioni validati

Scritti `curve.prezzi_negativi()` e `scripts/09_prezzi_negativi.py`, riutilizzabili su qualunque
serie di validazione già prodotta. Quattro test su casi giocattolo.

Serve a stabilire se la convenzione di D-32 — perdita di ciclo ripartita **in parti uguali** fra
carica e scarica — tocchi i risultati. A ciclo chiuso e con prezzi positivi conta solo il
prodotto dei rendimenti, quindi la ripartizione è irrilevante; diventa rilevante con prezzi
negativi nelle ore di carica, dove prelevare è remunerato e i due rendimenti entrano
separatamente nell'obiettivo.

| Campione | Periodi | Negativi | Prezzo minimo |
|---|---|---|---|
| Gennaio 2025, orario | 744 | **0** | 85,42 €/MWh |
| 15-22 aprile 2025, orario | 192 | **0** | 13,10 |
| Ott-dic 2025, quarto d'ora | 8.836 | **0** | 11,45 |
| 12-18 gennaio 2026, quarto d'ora | 672 | **0** | 105,58 |

**Nessun prezzo negativo in nessuno dei campioni validati**, per un totale di 10.444 aste. Su
gennaio 2025 il minimo è addirittura 85,42 €/MWh, cioè lontanissimo dallo zero: la questione
**non tocca in alcun modo il risultato attuale**.

I due campioni che si avvicinano di più sono aprile (13,10) e ottobre (11,45), cioè quelli a
maggiore produzione fotovoltaica fra i disponibili — coerente con l'attesa che il fenomeno, se
comparirà, si concentri nelle ore solari dei mesi centrali. Il controllo va quindi **rifatto
sull'anno intero**, dove maggio-luglio non sono ancora stati esaminati.

Finché nessun prezzo negativo compare, la ripartizione 50/50 resta una convenzione senza
conseguenze, ed è documentata come tale nella docstring di `config.rendimenti_da_ciclo`.

---

## 2026-08-13 — D-33 · Il vincolo orario-nei-quarti sul piano della batteria

### L'artefatto trovato

Nel mercato del giorno prima il prodotto è **orario**. Nel regime a quarto d'ora questo si
traduce in un vincolo che il codice rispettava su un lato solo.

**Lato offerte: rispettato.** `curve._riscala_quantita` porta un'offerta oraria nell'asta del
quarto d'ora usandone la quantità **invariata** (D-13): un'offerta da X MW vale X MW in ciascuno
dei quattro quarti. È il vincolo formalizzato anche da **Veenstra e Mulder (2025)**.

**Lato batteria: assente.** Il programma lineare di `profilo_ottimo` aveva come vincoli solo il
bilancio energetico, i limiti di capacità e potenza e il ciclo chiuso. Nulla legava i quattro
quarti della stessa ora. Verificato sul 06/10/2025 con una flotta da 100 MW: **in 10 ore su 24
il piano non era costante dentro l'ora**, quasi sempre con l'escursione massima — l'ora 1 dava
`0 · −100 · −100 · −100` MW, l'ora 18 `0 · 0 · 0 · +100`.

La batteria accendeva e spegneva a metà ora, cosa preclusa per costruzione a tutti gli altri
operatori.

**Quanto valeva.** Confronto fra piano libero e piano vincolato, entrambi valorizzati sui prezzi
veri al quarto d'ora:

| Giorno | Piano libero | Piano vincolato | Vantaggio |
|---|---|---|---|
| 06/10/2025 | 11.440 € | 10.997 € | +4,0% |
| 25/10/2025 | 20.082 € | 19.326 € | +3,9% |
| 18/11/2025 | 6.688 € | 6.587 € | +1,5% |
| 27/12/2025 | 842 € | 702 € | **+19,9%** |

Il vantaggio è strutturalmente positivo — il piano libero ottimizza su un insieme più ampio — e
vale il 2-4% nelle giornate a differenziale ampio, ma arriva a **un quinto del profitto** dove il
margine è sottile e l'arbitraggio infra-orario è quasi tutto ciò che resta.

L'effetto sui risultati sarebbe stato di **gonfiare il profitto price taker**, quindi abbassare
l'erosione e spostare **K\* verso l'alto**: un artefatto della simulazione, non un effetto di
mercato, e per giunta nella direzione che rende l'accumulo più innocuo di quanto sia.

### La correzione (D-33)

Aggiunto il parametro `periodi_per_ora` a `profilo_ottimo`, con default 1 che lascia il
comportamento invariato. `erosione()` lo deriva dalla granularità — `int(round(1/delta))`, cioè
4 su PT15 e 1 su PT60 — quindi non serve alcun ramo condizionale negli script.

L'implementazione **non** aggiunge vincoli di uguaglianza al programma lineare: risolve sulle
**medie orarie** dei prezzi con passo di un'ora e replica il piano nei quattro quarti. Poggia su
due proprietà:

* a potenza costante nell'ora il ricavo dipende solo dalla media dei quattro prezzi, perché
  $\sum_q p_q P \Delta = P \bar{p} \cdot 1\,\text{h}$;
* lo stato di carica è lineare, quindi **monotono**, dentro l'ora: i suoi estremi cadono ai
  bordi, e vincolarlo a fine ora basta a vincolarlo ovunque.

### La verifica di equivalenza

Le due proprietà non sono state assunte ma verificate, implementando anche la formulazione
**esplicita** — LP a 96 periodi più 144 righe di uguaglianza che legano i quarti — e
confrontandola con quella efficiente su tre giornate:

| Giorno | Profitto esplicito | Profitto efficiente | Differenza | max \|Δcarica\| | max \|Δscarica\| |
|---|---|---|---|---|---|
| 06/10/2025 | 10.996,9995 € | 10.996,9995 € | 0,000000 | 0,000000 | 0,000000 |
| 25/10/2025 | 19.325,8667 € | 19.325,8667 € | 0,000000 | 0,000000 | 0,000000 |
| 27/12/2025 | 702,5000 € | 702,5000 € | 0,000000 | 0,000000 | 0,000000 |

Non coincidono solo i profitti: coincide il **piano periodo per periodo**, con scarto
esattamente nullo su tutti i 96 periodi. Un'asserzione verifica inoltre che entrambe rispettino
davvero il vincolo in tutte le 24 ore. Se la monotonia dello stato di carica non avesse retto, le
due versioni sarebbero divergute nelle giornate a piano pieno come il 25/10, dove la batteria
satura la capacità: non è successo.

Adottata quindi la versione efficiente, che usa **48 variabili invece di 192**.

### Gennaio orario è invariato

Su PT60 il vincolo è vacuo, quindi i risultati già prodotti non devono muoversi. Verificato
contro i valori salvati dal rerun dell'11/08, replicando esattamente la configurazione dello
script (perimetro NORD più frontiere, prezzi di riferimento ricalcolati):

| Giorno | $\pi_{PT}$ atteso | $\pi_{PT}$ nuovo | Scarto |
|---|---|---|---|
| 02/01/2025 | 16.514,0764 | 16.514,0764 | 0 |
| 15/01/2025 | 44.762,6711 | 44.762,6711 | 0 |
| 20/01/2025 | 74.082,4278 | 74.082,4278 | 0 |
| 30/01/2025 | 15.879,3816 | 15.879,3816 | 1,8·10⁻¹² |

Scarto massimo **1,8·10⁻¹² €**, cioè zero macchina. **K\* = 136 MW resta valido.**

*(Una nota metodologica: il primo tentativo di verifica sembrava mostrare scarti di centinaia di
euro. Non era la modifica: era il banco di prova, che ricostruiva le curve sulla sola zona NORD
invece che sul perimetro NORD più frontiere usato dallo script. Vale la pena ricordarlo, perché
un controllo di non-regressione mal impostato produce esattamente il tipo di falso allarme che
porta a "correggere" codice sano.)*

Quattro test nuovi fissano il comportamento: vacuità su PT60, costanza dentro l'ora su PT15,
impossibilità che il vincolo aumenti il profitto, ed errore esplicito se i periodi non sono
divisibili in ore intere. Totale 84 test.

---

## 2026-08-17 — L'architettura a due livelli, il parametro K e il conto economico italiano

Preparata la valutazione economica del capitolo 5. Il lavoro ha richiesto prima di sanare
un'incoerenza già presente, poi di aggiungere i nuovi elementi.

### D-34 · π è un margine lordo, e ora è dichiarato

L'ispezione del 17/08 aveva trovato un'asimmetria non documentata: il costo di degrado entra
nel **piano** (il LP ottimizza con i 12 €/MWh sulla scarica) ma **non nella valorizzazione**,
quindi $\pi_{PT}$ e $\pi_{PM}$ erano ricavi lordi senza che questo fosse scritto da nessuna
parte. Sul 15/01/2025 con 100 MW il degrado vale 6.000 € su 44.763 di profitto riportato, cioè
il **13,4%**.

Adottata l'**opzione A**: π resta un margine lordo di mercato, e tutti i costi
dell'investitore si contano a valle. La ragione è che il progetto ha due livelli con nature
diverse:

* **livello 1** (`curve`, `batteria`) — l'effetto dell'accumulo sul prezzo di equilibrio è un
  fenomeno di **mercato**, che dipende dai volumi e dalla forma delle curve, non da come
  l'investitore sia tassato o da quanto costi l'impianto. Dedurvi i costi renderebbe la soglia
  una funzione del regime fiscale, il che sarebbe economicamente sbagliato;
* **livello 2** (`economia`, capitolo 5) — il conto dell'investitore, dove i costi entrano
  tutti, in un punto solo e una volta sola.

**La doppia natura del degrado** è il punto sottile, ed è ora scritto esplicitamente nelle
docstring e nel capitolo 5. Il costo di degrado è l'unico parametro che sta a cavallo dei due
livelli: nel piano è un **segnale operativo** — determina il differenziale minimo sotto il
quale non conviene ciclare, ed è ciò che genera le giornate a piano vuoto (D-31) — mentre nel
conto economico è un **esborso**, sottratto una volta sola. Non è un doppio conteggio: è lo
stesso parametro usato prima per decidere e poi per contare.

### D-35 · Il parametro K, solo nella valorizzazione

Aggiunto `rapporto_prezzo_acquisto` (il **K**) a `profitto_price_taker` e
`profitto_price_maker`, **non** a `profilo_ottimo`. Nello scenario principale il piano resta
guidato dai soli prezzi di mercato e il K colpisce solo il conto economico.

Ha richiesto una modifica di sostanza alla valorizzazione. Prima le due direzioni erano fuse
in un flusso netto, `netto = scarica − carica`, moltiplicato per lo stesso vettore di prezzi:
una scrittura valida **solo** perché K valeva implicitamente 1. Con K ≠ 1 i due lati non sono
più compensabili, perché il prelievo è pagato a un prezzo diverso, e vanno tenuti distinti:

$$\pi = \sum_t p_t \Delta s_t - K \sum_t p_t \Delta c_t$$

**Default K = 1** (net-settled), così i risultati già calcolati restano quelli. Verificato su
tre giornate e tre capacità contro i valori salvati dal rerun dell'11/08: scarto massimo
**2,3·10⁻¹⁰ €**, cioè zero macchina.

I due regimi sono documentati in `config`: K = 1 è il net-settled, economicamente efficiente
ma in Italia **non disponibile per l'arbitraggio puro** (è riservato ai servizi resi al gestore
di rete e agli ausiliari); K ≈ 2,3 è il regime vigente, dove sull'energia prelevata gravano
oneri di rete, oneri generali di sistema e fiscalità.

### D-36 · Il conto economico gira sul price maker

Scritto `src/mgp/economia.py`, che è il livello 2 in forma di codice: prende il margine lordo
e vi applica degrado, oneri via K, CapEx e OpEx, scontando sulla vita utile. Otto test.

La scelta metodologica centrale è che il ricavo si calcola sul **profitto price maker** alla
capacità aggregata di scenario, non sul price taker: quest'ultimo prometterebbe
all'investitore un margine che la sua stessa presenza sul mercato distrugge. La differenza
fra i due è per definizione l'erosione, che alla soglia vale il 10% e cresce rapidamente.

Parametri economici italiani centralizzati in `config.PARAMETRI_ECONOMICI`, con la fonte —
**Lilla et al. (2026), Sustainability** — e gli intervalli, perché la sensitività del capitolo 5
dovrà farli variare: CapEx 110.000 €/MWh (80.000-150.000), OpEx 2.000 €/MWh l'anno
(1.000-10.000), vita utile 15 anni, decadimento dei ricavi 1,5% l'anno, tasso di sconto 3%.

*(Dati bibliografici da verificare sull'editore: nel `.bib` la voce è marcata `DA COMPLETARE`.)*

### Il capitolo 5 e il contesto italiano nel LaTeX

Capitolo 1, nuova sottosezione sul **contesto regolatorio italiano**: la distinzione fra
net-settled e regime vigente, la definizione di K come equazione, e il meccanismo **MACSE** di
Terna — le aste con cui il gestore di rete si approvvigiona di servizi di *time-shifting* — come
contesto istituzionale in cui l'accumulo sta effettivamente entrando nel mercato italiano.

Ne discende una precisazione importante sulla portata del lavoro, ora scritta: la redditività
calcolata riguarda il **solo arbitraggio sul MGP**, ed è quindi un **limite inferiore** di
quella di un impianto reale, che cumula più fonti di ricavo. La domanda di ricerca resta però
ben posta, perché l'effetto sul prezzo si produce indipendentemente da come l'accumulo sia
remunerato.

Nel posizionamento in letteratura, Lilla et al. sono il terzo riferimento e il più vicino sul
piano del **contesto**, ma con impianto complementare: trattano i **prezzi come esogeni** e
ottimizzano l'investimento, mentre qui i prezzi sono endogeni e l'oggetto è l'effetto su di
essi. Sono gli autori stessi a indicare fra gli sviluppi futuri che *un arbitraggio diffuso
potrebbe appiattire i differenziali di prezzo*: è, formulata come questione aperta, la domanda
di ricerca di questa tesi. È il terzo lavoro su tre che converge sullo stesso punto.

Capitolo 5: struttura del conto economico con l'architettura a due livelli resa esplicita, la
doppia natura del degrado, la scelta del price maker, la tabella dei parametri, e la
dichiarazione che i risultati sono presentati a **K = 1**, cioè in un regime che per
l'arbitraggio puro **non esiste oggi in Italia** — quindi come limite superiore, con K ≈ 2,3
in sensitività.

---

## 2026-08-18 — Capitolo 1 sul contesto italiano, e una toolchain LaTeX locale

Voce breve, perché il lavoro è di stesura e di ambiente, non metodologico.

### Il capitolo 1 non era più un segnaposto

Redatte le sezioni **1.1 (transizione energetica)** e **1.2 (BESS)**, finora vuote, sulla base
del **Documento di Descrizione degli Scenari 2024** di Terna e Snam, del **PNIEC 2024** e del
**d.lgs. 210/2021**, le cui voci sono confluite nella bibliografia principale.

I numeri che il capitolo porta in dote e che vale la pena ricordare, perché inquadrano il
lavoro: la quota rinnovabile sul fabbisogno passa dal 37% del 2023 al **63% al 2030**, il
fotovoltaico da 31 a **105 TWh**, e il fabbisogno di accumulo al 2030 è di **122 GWh
complessivi**, di cui **71,5 di nuova capacità**. Il DDS stima inoltre un profilo operativo di
**3.300 ore equivalenti l'anno** per un accumulo da 8 ore — un termine di raffronto diretto per
i cicli che il nostro modello produce.

Due punti di attrito con il resto della tesi, risolti conservando entrambi i contenuti. Il file
fornito conteneva un `\chapter` completo con le sole due sezioni: sostituirlo avrebbe cancellato
le sezioni 1.3-1.5, il posizionamento rispetto ai tre riferimenti in letteratura e la
sottosezione sul parametro K, che il capitolo 5 cita. Si è quindi **fuso** invece di sostituire.
Dalla sottosezione su K è stato tolto il paragrafo sul MACSE, che il testo nuovo tratta più
estesamente e con la fonte.

### Il documento ora si compila in locale

Installata **MiKTeX 25.12** (in `AppData\Local\Programs`, non in `Program Files`) e aggiunto
`siunitx` con separatore decimale a virgola: il capitolo 1 usa `\SI` e `\num` in ogni paragrafo
e senza il pacchetto il documento **non compilava affatto**.

Prima compilazione completa della tesi, con la sequenza `pdflatex` → `biber` → `pdflatex` ×2:
**49 pagine, nessun errore, nessuna citazione o riferimento non definito**, sei voci
bibliografiche tutte risolte. Restano sette over/underfull box, sei nel capitolo 4 (righe lunghe
delle tabelle di validazione) e uno nel capitolo 6: sono tipografici e nessuno tocca il
capitolo 1.

È un cambiamento di metodo di lavoro: finora il LaTeX si verificava solo con un controllo
statico fatto in casa e si compilava su Overleaf. Ora il ciclo si chiude in locale, e i
segnaposto `DA COMPLETARE` sono 23.

Compilato anche il frontespizio con i dati veri. Restano da completare il correlatore e
l'eventuale sottotitolo, segnalati in commento nel sorgente.

---

## 2026-08-19 — Lo spread infragiornaliero al Sud contro il Nord: misura esplorativa

Misura preparatoria alla scelta della zona da studiare, da discutere col relatore. I documenti
Terna concentrano il fabbisogno di accumulo su SUD e CSUD e suggeriscono che l'arbitraggio vi
sia più redditizio; qui la cosa è verificata sui prezzi ricostruiti invece che sulle previsioni.

**È esplorativa, non una validazione**: misura lo spread del prezzo di equilibrio ricostruito,
non l'accuratezza della ricostruzione sulle zone meridionali, dove l'assunzione di zona isolata
regge peggio che al Nord perché le zone sono più accoppiate fra loro.

### Disegno

Giorni **10-16 di ogni mese da gennaio a settembre 2025**: 63 giornate, tutte in **regime
orario**, perché il passaggio al quarto d'ora è del 01/10/2025 e restare in un solo regime rende
le stagioni confrontabili. Conseguenza dichiarata: **l'autunno è rappresentato dal solo
settembre** (7 giornate), ed è quindi la stagione meno solida.

Sul perimetro è stata fatta una verifica prima di scegliere. La configurazione validata per NORD
include le frontiere estere (D-10), che per le zone meridionali non hanno un analogo diretto.
Misurato il 15/01/2025: **NORD con e senza frontiere dà lo stesso identico spread**, 151,30
€/MWh. Il blocco di scambio netto (D-16), essendo calibrato sulle quantità assegnate osservate,
assorbe già l'effetto delle zone di frontiera. Si è quindi usato il trattamento uniforme
"zona sola più scambio netto" per tutte e tre, che è confrontabile fra zone e non rompe la
coerenza con la configurazione adottata.

**Controllo di qualità**: su 63 giornate × 3 zone, **nessuna asta senza equilibrio**. Non
emergono problemi evidenti nella ricostruzione zonale meridionale, il che è un'informazione
utile per un'eventuale estensione futura.

### Il risultato: il vantaggio del Sud esiste, ma è più modesto dell'atteso

| Zona | Spread medio | Mediano | Dev. std | 90° perc. |
|---|---|---|---|---|
| **SUD** | **79,79** | **72,03** | 33,75 | 131,10 |
| CSUD | 66,75 | 55,00 | 31,67 | 113,21 |
| NORD | 63,83 | 53,49 | 29,69 | 113,17 |

Rapporto rispetto a NORD, calcolato **appaiato** sugli stessi giorni — molto più robusto di un
confronto fra medie, perché elimina la variabilità di sistema comune alle zone:

| Stagione | SUD / NORD | CSUD / NORD |
|---|---|---|
| **Autunno** (settembre) | **1,80** | 1,27 |
| **Estate** | **1,36** | 1,13 |
| Primavera | 1,03 | 0,91 |
| Inverno | 1,06 | 0,92 |
| **Complessivo** | **1,23** | **1,00** |

Tre fatti che ridimensionano l'aspettativa di partenza.

**Il vantaggio del SUD è 1,23×, non 2×.** È però sistematico: lo spread supera quello del NORD
in **47 giornate su 63**, quindi non è l'effetto di poche giornate estreme.

**CSUD non è una zona ad arbitraggio più ricco del NORD**: rapporto mediano **1,00**, e in 32
giornate su 63 lo spread è inferiore. È la sorpresa maggiore, perché Terna concentra il
fabbisogno su SUD *e* CSUD, ma sui prezzi effettivamente formatisi solo SUD si distingue.

**Il vantaggio è stagionale e sparisce per metà anno**: forte in autunno ed estate, nullo in
inverno e primavera.

### Da dove viene il vantaggio: non dal ventre solare

La scomposizione dello spread in minimo e massimo è il risultato più utile della misura, perché
smentisce il meccanismo che si dava per scontato (differenze medie in €/MWh, SUD meno NORD):

| Stagione | Δ minimo | Δ massimo | Origine del vantaggio |
|---|---|---|---|
| Inverno | +0,1 | +2,9 | nessuna |
| **Primavera** | **−15,8** | +1,4 | ventre solare |
| **Estate** | −3,5 | **+17,0** | **picco serale** |
| **Autunno** | −7,8 | **+17,2** | **picco serale** |

Nelle due stagioni in cui il SUD ha davvero un vantaggio, questo **non nasce dall'eccesso di
produzione fotovoltaica di mezzogiorno** ma dal fatto che il prezzo serale vi sale molto più che
al Nord: +17 €/MWh sul massimo contro −4/−8 sul minimo. Il picco serale vale 1,24-1,27 volte la
media giornaliera al SUD contro 1,17-1,19 al NORD. È un fenomeno di **scarsità serale**, non di
overgeneration diurna.

Il ventre di mezzogiorno esiste ed è più profondo al Sud (prezzo medio delle ore 11-16 sulla
media giornaliera: 0,609 contro 0,728 in primavera), ma la primavera — dove il fenomeno è più
netto — è proprio la stagione in cui il vantaggio relativo è **nullo**, perché anche il Nord ha
un ventre profondo.

**In inverno il ventre non esiste in nessuna zona**: il minimo giornaliero cade alle ore 4-5.
L'arbitraggio invernale è notte→sera, strutturalmente diverso da quello estivo mezzogiorno→sera.

Figura in `output/figure/10_profilo_orario_zone.png`: profilo orario medio delle tre zone nelle
quattro stagioni.

### Implicazione per la scelta della zona

L'evidenza **sostiene la terza via**: tenere NORD come zona di analisi principale, dove il
motore è validato e la ricostruzione è accurata (errore mediano 0,00 €/MWh), e usare SUD come
**confronto** documentato.

Le ragioni sono tre. Il vantaggio del SUD è reale ma modesto, 1,23×, e non giustifica di
rifare da capo validazione e messa a punto su una zona dove l'assunzione di zona isolata regge
peggio. CSUD, che secondo il quadro Terna dovrebbe essere fra le zone privilegiate, non si
distingue dal NORD. E soprattutto il vantaggio del SUD viene in larga parte da un meccanismo —
il picco serale — che non è quello che la narrazione sull'accumulo assume.

Quest'ultimo punto è di per sé un contributo: il campione suggerisce che collocare accumulo al
Sud renda di più **non** perché vi si sprechi energia solare a mezzogiorno, ma perché vi si paga
di più l'energia la sera. Se il relatore volesse una seconda zona, SUD è la scelta giusta e
questa è la misura da cui partire; ma andrebbe messa in conto una validazione dedicata.


---

## 2026-08-24 — Le due giornate a spread massimo: le figure che illustrano l'arbitraggio

**Cosa serviva.** Una figura che mostri l'opportunità di arbitraggio nella sua forma più
diretta, prima di qualunque modello: il profilo orario del prezzo di equilibrio in una
giornata in cui minimo e massimo sono molto distanti. È materiale illustrativo per la tesi,
non un risultato nuovo, ma la selezione delle giornate va comunque fatta con un criterio
riproducibile e non a occhio.

### Il bacino, e perché la classifica va letta insieme alla sua composizione

Sono state misurate **93 giornate del 2025 in regime orario**, quelle già in cache Parquet:
gennaio per intero (31 giorni) e la settimana 10-16 di febbraio-settembre, più la finestra
10-22 di aprile. La ricostruzione usa la **configurazione adottata**, la stessa dello script
03: perimetro NORD più le frontiere presenti (D-10), offerte in gara (D-06), tutte le
granularità (D-13), quantità rettificata (D-20), scambio netto simmetrico (D-16), clearing
iterativo consapevole dei blocchi (D-18, D-19). Non è una scorciatoia sul prezzo ufficiale:
è il motore validato. Tutte e 93 le giornate chiudono su 24 periodi, nessuna asta senza
equilibrio.

Il regime a quarto d'ora è escluso di proposito e per due ragioni: 96 periodi rendono
illeggibili marcatori ed etichette, e quel regime si ricostruisce con deviazione standard
5,42 contro 1,06 dell'orario.

**Il bacino non è un campione casuale, e questo pesa sul risultato.** Gennaio ha avuto 31
occasioni di produrre un estremo, gli altri mesi sette. Lo si vede confrontando la mediana
mensile con il massimo mensile:

| Mese | Giorni | Spread mediano | Massimo |
|---|---|---|---|
| gennaio | 31 | 56,50 | **161,31** |
| febbraio | 7 | 64,87 | 74,68 |
| marzo | 7 | 67,10 | 130,35 |
| aprile | 13 | 94,14 | 124,76 |
| **maggio** | 7 | **120,35** | 136,41 |
| giugno | 7 | 47,52 | 114,66 |
| luglio | 7 | 51,10 | 81,32 |
| agosto | 7 | 55,31 | 88,78 |
| settembre | 7 | 44,22 | 118,42 |

**Maggio è il mese a spread tipico più alto** — mediana 120,35 contro i 56,50 di gennaio — e
con sette sole giornate ha già prodotto il terzo, quarto e quinto posto in classifica
(136,41, 135,51, 131,35). Con maggio campionato per intero è verosimile che il massimo
assoluto dell'anno non cada più il 20 gennaio. Le giornate scelte sono quindi le più ampie
**del bacino esaminato**, e vanno presentate così: non come il massimo dell'anno.

Spread mediano complessivo sulle 93 giornate: **60,23 €/MWh**; medio 69,37.

### Le due giornate scelte, e perché non le prime due

Le prime due della classifica sono **20 gennaio (161,31)** e **15 gennaio (151,30)**, ma
raccontano la stessa identica storia: minimo notturno attorno a 125 €/MWh, picco alle 9.
Come coppia di figure sarebbero ridondanti. Si è preferita una coppia mista:

| Giornata | Spread | Minimo | Massimo | Scarto dall'ufficiale (mediano / massimo) |
|---|---|---|---|---|
| **20 gennaio 2025** | **161,31** | 127,69 (ore 2) | 289,00 (ore 9-10, 19-20) | 0,23 / 6,61 |
| **16 maggio 2025** | **136,41** | 15,41 (ore 14) | 151,82 (ore 21) | 0,31 / 4,22 |

Lo spread ufficiale è 161,37 e 132,38: la ricostruzione lo coglie a 0,06 €/MWh nella prima
giornata e a 4,03 nella seconda.

La ragione della scelta non è estetica ma di contenuto: la voce del 19/08 aveva già
osservato che **i due regimi di arbitraggio sono strutturalmente diversi**. Il 20 gennaio è
notte → mattina, con il minimo alle 2 e il picco alle 9, e il ventre di mezzogiorno non
esiste. Il 16 maggio è mezzogiorno → sera, con il minimo alle 14 a 15,41 €/MWh e il picco
alle 21 a 151,82: un rapporto di quasi dieci volte, ed è il meccanismo su cui poggia la
domanda di ricerca. Due giornate invernali gemelle mostrerebbero soltanto che a gennaio 2025
il gas costava molto.

Il 20 gennaio è inoltre **la stessa giornata già usata nel capitolo 4** per le curve d'asta
(`07_curve_20250120`) e per la curva di impatto marginale: il lettore vede il profilo dei
prezzi e, poche pagine dopo, le curve che lo generano nell'ora di minimo e in quella di
picco.

### Che cosa misura lo spread, e che cosa non misura

Va scritto nella didascalia, perché è il punto su cui la figura può ingannare. Lo spread è
il **ricavo lordo per MWh ciclato di un accumulo perfettamente informato e di potenza
trascurabile**: un limite superiore dell'arbitraggio price taker. Non è il profitto. Il
profitto sconta il rendimento di ciclo, il costo variabile e soprattutto il **vincolo di
potenza**, perché l'energia non si sposta tutta in una sola ora — e per capacità non
trascurabili sconta anche la retroazione sul prezzo, che è l'oggetto della tesi. La
docstring di `profilo_prezzi` lo dice, così il chiarimento non si perde.

### Due scelte di disegno che valgono come metodo

**Il prezzo si disegna a gradini, non con una spezzata.** Il prezzo di un'asta oraria è
costante dentro l'ora; interpolare i vertici suggerirebbe una transizione graduale che non
esiste. I marcatori di minimo e massimo cadono al centro dell'ora, dove il gradino è in
vigore.

**Nel confronto appaiato i due pannelli condividono l'asse verticale.** Con assi
indipendenti due spread di ampiezza diversa occuperebbero la stessa altezza sulla pagina e
il confronto visivo sarebbe ingannevole. Condividendo l'asse si leggono insieme l'ampiezza
dell'oscillazione e il livello attorno a cui avviene: il 16 maggio ha uno spread poco più
piccolo, ma tutto il suo profilo sta sotto al minimo del 20 gennaio.

Due dettagli emersi solo guardando i PNG salvati, non prevedibili scrivendo il codice.
Il primo: il 20 gennaio il massimo di 289,00 €/MWh è toccato da **quattro ore** (9-10 e
19-20), non da una; il marcatore ne segna una sola e senza l'annotazione degli intervalli
sembra un errore. Il secondo: con il minimo del 16 maggio a 15,41 €/MWh, tagliare l'asse
verticale a zero non lascia spazio all'etichetta, che finisce ribaltata dentro la spezzata.
Si è preferito lasciare che l'asse scenda di qualche euro sotto lo zero — dove non c'è alcun
dato e la linea dello zero resta visibile — piuttosto che spostare l'etichetta in un punto
in cui collide con la curva.

### Prodotti

Logica in `src/mgp/grafici.py` (`profilo_prezzi`, `figura_profilo_prezzi`,
`figura_profili_confronto`, con `_annota_estremi` che sceglie il lato dell'etichetta in base
allo spazio libero); esecuzione in `scripts/10_profilo_spread.py`, che in modalità `--cerca`
riproduce la classifica del bacino e senza argomenti disegna le due giornate. Undici test
nuovi in `tests/test_grafici.py` sulle due regole che, se sbagliate, darebbero una figura
plausibile ma falsa — la compressione delle ore in intervalli e la misura degli estremi:
**103 test verdi**.

Figure in `output/figure/` (PNG a 160 dpi e PDF vettoriale), copiate in `latex/figure/` per
la compilazione: `10_profilo_20250120`, `10_profilo_20250516` e il confronto appaiato
`10_profilo_confronto_20250120_20250516`. Tabella riproducibile in
`output/tabelle/10_spread_giornaliero_NORD.csv`.

Nessuna modifica al motore né alle scelte esistenti: è materiale illustrativo.


---

## 2026-08-27 — Tre riferimenti nei capitoli 3 e 4: la radice storica, la controparte teorica, il sostegno ai parametri

Integrati tre lavori nella bibliografia e nei capitoli 3 e 4. Non sono materiale
implementativo: nessuna riga di codice cambia, cambia l'argomentazione. Ciascuno risponde a
un'obiezione diversa che la tesi si attirerebbe se ne fosse priva.

### Sioshansi, Denholm, Jenkin e Weiss (2009) — la cannibalizzazione non è un'ipotesi

*Energy Economics* 31(2), 269-277. Fra i primi a formalizzare, su dati reali del mercato PJM
fra il 2002 e il 2007, che l'accumulo su larga scala **appiattisce il profilo dei prezzi** —
abbassa i picchi, solleva i minimi — e che il valore unitario dell'arbitraggio decresce al
crescere della capacità installata.

Collocato nel **capitolo 3**, subito dopo l'osservazione che la retroazione agisce contro
l'operatore in entrambe le direzioni. È il punto in cui il meccanismo viene enunciato per la
prima volta, e senza un riferimento resterebbe una congettura di questo lavoro.

L'inquadramento conta quanto la citazione: il fenomeno è **noto e consolidato da oltre
quindici anni**, quindi la domanda di ricerca non è se esista ma *dove* si collochi la soglia
in un mercato specifico e con quanta incertezza. Detto così, il contributo originale si
definisce per differenza — curve d'asta effettivamente presentate al mercato, e soglia
restituita come distribuzione anziché come valore puntuale — invece di essere rivendicato.

### Dumitrescu, Silvente e Tankov (2024) — la stessa conclusione da strumenti opposti

Preprint arXiv (CREST/ENSAE, Institut Polytechnique de Paris). Costruiscono il prezzo di
equilibrio come soluzione di un sistema di **equazioni differenziali stocastiche
forward-backward**, in un mercato con rinnovabili, produttori convenzionali e accumulo price
taker, calibrato sugli scenari RTE per la Francia.

Il risultato che interessa: al crescere della capacità di accumulo aumentano **sia i ricavi
medi sia l'ampiezza degli intervalli interquantile**. Più profitto atteso, ma anche più
dispersione — cioè la media da sola descrive male l'investimento.

Collocato nel **capitolo 3**, all'apertura della sezione sulla gestione dell'incertezza, dove
si dichiara che la soglia è essa stessa una variabile aleatoria.

Il valore argomentativo sta nella **convergenza fra metodi opposti**. Quel lavoro è *model
driven*: postula una dinamica in tempo continuo e ne deriva le proprietà. Questo è *data
driven*: non postula alcuna dinamica di prezzo, ricampiona le curve osservate e lascia che
l'incertezza emerga dalla loro variabilità. Che due strade così diverse indichino entrambe la
distribuzione come oggetto rilevante è un sostegno più forte di quanto sarebbe una
concordanza fra lavori metodologicamente affini. Nel testo è dichiarato **preprint non
sottoposto a revisione paritaria**: citarlo senza dirlo sarebbe scorretto, e la citazione
regge lo stesso perché serve come conferma convergente, non come autorità.

### McConnell, Forcey e Sandiford (2015) — sostegno puntuale a due scelte

*Applied Energy* 159, 422-432. Due risultati, collocati in due punti diversi del **capitolo
4** perché sostengono due cose diverse.

**La durata di quattro ore** (§ sugli scenari): trovano valore marginale modesto oltre le
**sei ore** di durata, perché oltre quel punto l'energia aggiuntiva finisce impiegata in
periodi troppo poco remunerativi. Quattro ore stanno quindi nella regione in cui il
rendimento della durata è ancora crescente. Fin qui il caso base poggiava solo sulla
diffusione commerciale del taglio e su Alonso-Perez (D-32): ora ha anche una ragione
economica.

**Il rendimento di ciclo** (§ sui parametri tecnici): in un mercato in cui il valore
dell'accumulo si concentra nei prezzi estremi, il round-trip efficiency incide poco, perché
con un differenziale ampio qualche punto percentuale di perdita non cambia la convenienza
dell'operazione. Ne discende una **previsione verificabile** scritta nel testo: la
sensitività su η (85, 90, 92%) dovrebbe spostare K\* meno di quanto la sposti la durata.
Vale la pena averla messa per iscritto *prima* di calcolarla: se il rerun la smentisse,
sarebbe un risultato, non un imbarazzo.

**Il limite del trasferimento è dichiarato nel testo.** Il loro è un mercato *energy only*,
mentre in Italia esistono un mercato della capacità e il MACSE. L'osservazione vale per la
sola componente di arbitraggio, che è l'unica considerata qui: scriverlo evita che la
citazione provi più di quanto possa.

### Bibliografia: cosa resta da completare

Le tre voci sono in coda a `latex/bibliografia.bib`. Restano tre buchi, marcati
`DA COMPLETARE` e non riempiti a invenzione:

* il **DOI** di Sioshansi e quello di McConnell (entrambi Elsevier);
* per Dumitrescu, l'**identificativo arXiv** e i **nomi di battesimo** degli autori. I
  cognomi da soli bastano a far rendere correttamente `\textcite`, ma la voce è incompleta.

I DOI non sono stati inseriti a memoria di proposito: un DOI sbagliato in una tesi è peggio
di un DOI assente, perché non si vede finché qualcuno non lo clicca.

### Segnalato e non fatto

**Sioshansi starebbe bene anche nel capitolo 1**, nella rassegna che oggi posiziona la tesi
rispetto ad Alonso-Perez, Veenstra e Lilla: quei tre sono tutti recenti e manca la radice
storica. Il capitolo 1 è però **fuori perimetro** — dal 27/08 valgono le regole registrate in
`CLAUDE.md`, per cui da qui si scrive solo nei capitoli 3, 4 e 5, si può aggiungere in
`acronimi.tex` e in `bibliografia.bib`, e tutto il resto è gestito dallo studente su
Overleaf. La segnalazione è stata fatta a parole.

Nessun acronimo nuovo è stato necessario: MACSE e MGP erano già definiti.

Il testo per il capitolo 1 è stato **redatto e consegnato allo studente**, non inserito: va
fra «La domanda non è inedita.» e la frase su Alonso-Perez, nel paragrafo «Il contributo
rispetto alla letteratura».

### La compilazione ha fatto emergere due difetti preesistenti

Compilazione locale con MiKTeX: **63 pagine, nessun errore**, le tre citazioni nuove si
risolvono e biber non segnala nulla su di esse. Ha però portato a galla due difetti che non
c'entrano con questa integrazione e che nessuno aveva notato, perché finora si compilava su
Overleaf senza leggere il log.

**Chiave di citazione rotta in `05_valutazione_economica.tex`**: il capitolo citava
`lilla2026storage`, ma nel `.bib` la voce ha oggi la chiave MDPI `su18031404` — il capitolo 1
la cita già così. A pagina 44 i parametri economici italiani risultavano quindi **senza
attribuzione**. Corretto: il capitolo 5 è dentro il perimetro.

**`\label{sec:mgp}` commentato** in `02_mercato_elettrico.tex`, mentre `04_simulazione.tex`
lo referenzia due volte: nel PDF si leggevano due «Sezione **??**», a pagina 26 e 39. Il
capitolo 2 è fuori perimetro, quindi segnalato e non toccato.

La lezione è di metodo e vale oltre questo caso: **un riferimento rotto non fa fallire la
compilazione**, produce un `??` o una citazione muta e passa inosservato in un PDF di
sessanta pagine. Il log va letto, non solo guardato l'esito.


---

## 2026-08-28 — Il 2024 come anno base: griglia delle capacità e calcolo parallelo

Il relatore ha approvato il **perimetro temporale**: anno base **2024**, interamente in regime
orario. È la decisione che bloccava tutto il resto (voce «Prossimi passi» dal 18/08). Questa
voce copre la preparazione dell'infrastruttura, non il run: griglia delle capacità e
parallelizzazione, entrambe validate ma non ancora usate per produrre risultati.

### Il 2024 si ricostruisce senza adattamenti, ed è più semplice del 2025

Verificate tre giornate distribuite sull'anno (15 gennaio, 15 giugno, 15 dicembre), non una:
una deriva di schema può avvenire *dentro* l'anno, come è successo col passaggio al quarto
d'ora dell'ottobre 2025.

**366 giorni su 366 disponibili**, nessuna lacuna. L'archivio contiene 732 file per il 2024
perché ogni giorno ha sia `MGPOffertePubbliche` sia `MBOffertePubbliche` (Mercato di
Bilanciamento, che non ci riguarda). Anche **2020 (366) e 2022 (365) sono completi**, quindi
il confronto di volatilità previsto non ha buchi.

Tre proprietà rendono il 2024 più semplice del 2025, non solo più veloce:

* **granularità pura**: 100% PT60, zero righe PT15 o PT30. La questione aperta D-13 sul
  trattamento della quota a granularità minoritaria **non si pone** su questo anno;
* **perimetro di frontiera ridotto a SVIZ**: FRAN non compare. Il perimetro si costruisce per
  intersezione con le zone presenti, quindi si adatta da solo, ma va saputo — il blocco di
  scambio netto (D-16) lavora su un perimetro leggermente diverso da quello di gennaio 2025;
* **ricostruzione accurata senza messa a punto**: scarto dall'ufficiale mediano 0,05 €/MWh il
  15 gennaio e 0,00 il 15 giugno, massimo 2,72. In linea con gennaio 2025.

Il vincolo orario D-33 resta **vacuo** per costruzione: un periodo coincide con un'ora.

### Il costo reale: molto più basso di quanto si temeva

La stima di ~27 ore per l'anno veniva dai 4,5 minuti per giorno del PT15. Quel numero è di un
altro problema: 96 periodi invece di 24, e la validazione completa invece del solo calcolo
dell'erosione. Misurato sull'orario, il rapporto è di circa **1 a 60**.

| | lettura | curve + prezzi rif. | erosione (9 capacità) | totale |
|---|---|---|---|---|
| A freddo (parsing dallo zip) | 15,60 s | 5,48 s | 1,50 s | **22,58 s** |
| A caldo (da cache Parquet) | 0,41 s | 2,92 s | 1,33 s | **4,66 s** |

Con la griglia vecchia a 9 punti l'anno costava **28 minuti** in sequenza, non 27 ore. Questo
ha aperto la possibilità di infittire la griglia, che è il passo successivo.

### La griglia delle capacità: 132 punti, quattro regimi

Prima una **correzione a un ricordo sbagliato**. Sulla curva di gennaio 2025, al 90°
percentile e sull'erosione **lorda**, le soglie cadono a: 5% → 24 MW, 10% → 78 MW, 20% → 270
MW, 50% → 740 MW, 100% → 1.568 MW (sulla mediana, 2.447 MW). Il K\* = 136 MW noto è al
**netto del pavimento** (D-30): sottraendolo la curva si abbassa e il 10% viene attraversato
più tardi. Lordo 78, netto 136 — quasi un fattore due, tutto pavimento di discretezza. Per
dimensionare la griglia contano entrambi, perché il calcolo passa dal lordo.

| Regime | Intervallo | Passo | Punti | A che serve |
|---|---|---|---|---|
| Fondo | 1–20 MW | **1 MW** | 20 | il pavimento D-30 e la sua verifica |
| Soglia | 30–400 MW | **10 MW** | 38 | le convenzioni al 5, 10 e 20%, lorde e nette |
| Transizione | 425–1.000 MW | 25 MW | 24 | la salita verso la saturazione |
| Saturazione | 1.100–6.000 MW | 100 MW | 50 | il tratto oltre il 100% di erosione |

Definita in `batteria.griglia_capacita`, che ne documenta ogni regime.

**Il minimo resta 1 MW e non va abbassato.** `sottrai_pavimento` usa la capacità più piccola
della griglia come riferimento di «effetto nullo»: cambiarla ridefinirebbe il pavimento e
renderebbe i risultati non confrontabili con quelli già prodotti.

**Il passo di 1 MW sotto i 20 non serve alla risoluzione ma a una verifica.** Se il pavimento
è davvero discretezza della ricostruzione e non effetto di mercato, la curva lì dev'essere
piatta — su gennaio 2025 lo è (1 e 2 MW danno lo stesso q90, 2,76%). Con venti punti a passo
unitario quella piattezza si osserva sul 2024 invece di essere assunta.

**Il passo nella regione della soglia è 10 MW e non 5**, ed è una scelta deliberata dello
studente. Dieci megawatt sono già circa **cinque volte più fini dell'intervallo di confidenza**
di K\*, ampio ~96 MW su gennaio (83–179). La griglia è quindi calibrata sulla risoluzione
informativa reale: raffinare sotto l'ampiezza dell'incertezza campionaria darebbe una
**precisione fittizia**, che il rumore statistico non giustifica e che costerebbe il doppio del
tempo. Il passo a 5 MW era stato proposto e scartato per questa ragione (170 punti contro 132).

Costo misurato: **143 ms per capacità**, identico al costo per capacità della griglia vecchia
(147 ms), quindi lineare e senza sorprese. La giornata passa da 4,7 a **21,5 s** e l'anno da
28 minuti a **2,2 ore** in sequenza. La frase «infittire è quasi gratis» valeva a trenta punti,
non a centotrenta: il tempo si sposta tutto sull'erosione, che diventa l'86% del totale.

### Un rischio da sorvegliare quando si lancerà il bootstrap

`_attraversamento` prende il **primo** superamento della soglia, il che presuppone che la
curva erosione-capacità sia monotona. Con griglia fitta, un sobbalzo locale del quantile
dentro un ricampionamento bootstrap potrebbe far scattare l'attraversamento in anticipo e
spostare K\* **verso il basso**. Su gennaio la curva q90 è monotona su tutti i 22 punti della
griglia fine, quindi il rischio è per ora teorico — ma va verificato prima di fidarsi del
numero finale, non dopo.

Piano concordato, da eseguire **al momento del bootstrap** e non ora:

1. misurare la **frequenza** di non-monotonia, cioè quanti ricampionamenti hanno almeno un
   doppio attraversamento;
2. misurare anche l'**ampiezza** dei sobbalzi, distinguendo il rumore di campionamento del
   quantile (frazioni di punto percentuale) dai doppi attraversamenti economicamente
   significativi. La correzione giusta dipende da *com'è fatta* la non-monotonia, non solo da
   quanto è frequente;
3. **decidere la correzione solo se emerge**, fra: (a) prendere l'ultimo attraversamento
   invece del primo — robusto ma grezzo, adatto ai veri doppi attraversamenti; (b) lisciare
   la curva quantile prima di cercare l'attraversamento (regressione isotonica, che impone
   monotonia, o media mobile sulle capacità) — più elegante e statisticamente motivata, adatta
   se i sobbalzi sono rumore locale;
4. qualunque correzione sposta la soglia, quindi va registrata come **D-37** datata al momento
   della scelta, non adesso.

### La parallelizzazione: 4,4× e nessun cambiamento nei risultati

Il calcolo è imbarazzantemente parallelo — ogni giorno ha le proprie curve e non dipende dagli
altri. Nuovo modulo `src/mgp/parallelo.py`, che **avvolge** il calcolo validato senza
modificarlo: `erosioni_giorno` è la stessa funzione che stava in `scripts/06`, spostata nel
package perché la logica riutilizzabile vi appartiene e perché il runner deve importarla.
Lo script 06 ha ora l'opzione `--processi`.

**La macchina non è quella che si credeva**: AMD Zen/Zen+, **4 core fisici e 8 thread**, non
6/12. Il tetto realistico è quindi attorno a 4×, non 6×.

| Processi | Secondi (16 gg) | s/giorno | Speedup | Efficienza | Anno 2024 |
|---|---|---|---|---|---|
| 1 | 343,6 | 21,48 | 1,00 | 1,00 | 2,18 h |
| 2 | 186,4 | 11,65 | 1,84 | 0,92 | 1,18 h |
| 4 | 114,9 | 7,18 | 2,99 | 0,75 | 0,73 h |
| 6 | 94,8 | 5,93 | 3,62 | 0,60 | 0,60 h |
| 8 | 78,3 | 4,89 | **4,39** | 0,55 | **0,50 h** |

**L'anno 2024 passa da 2,2 ore a 30 minuti** su otto processi. Il guadagno oltre i quattro
processi viene dal solo SMT, e infatti l'efficienza crolla da 0,75 a 0,55.

#### Uno speedup falso, e come si è riconosciuto

La prima misura dava **8,18× con efficienza 1,71 su due processi**. È un risultato impossibile:
uno speedup superlineare su lavoro CPU-bound non esiste, e l'efficienza maggiore di uno è il
sintomo che la baseline è stata penalizzata.

La causa: i sedici giorni di marzo non erano in cache. La prova sequenziale, girando per prima,
ha pagato ~15 s per giorno di parsing dagli zip; le quattro prove parallele successive hanno
trovato la cache Parquet già scritta. Il confronto attribuiva alla parallelizzazione un
guadagno che era soltanto I/O già fatto — la baseline risultava 40,18 s/giorno contro i 21,48
reali.

Corretto aggiungendo al benchmark una passata di **riscaldamento della cache** prima di
cronometrare, documentata nello script con questo ragionamento perché è un errore che si rifà
volentieri. Vale come regola generale: **quando una misura di prestazione dà un risultato
migliore del possibile, l'errore è nella misura.**

### Non regressione: identici bit a bit, non «al centesimo»

Sei giornate calcolate in sequenza e su quattro processi: tutte e dieci le colonne numeriche
**coincidono esattamente**, righe nello stesso ordine, colonne testuali identiche.

Il confronto è esatto di proposito. Accontentarsi di due decimali nasconderebbe una differenza
sistematica piccola, che è il sintomo peggiore perché non si nota e si propaga a tutto l'anno.
`erosioni_giorno` è pura rispetto alla data, quindi i float *devono* coincidere: se non lo
facessero, ci sarebbe un problema da capire, non una tolleranza da allargare.

### Il seme del bootstrap in parallelo: il problema non si pone

Domanda legittima, risposta strutturale: **il parallelismo sta interamente a monte del
generatore casuale**. I lavoratori calcolano una tabella deterministica giorno × capacità e non
estraggono alcun numero; `bootstrap_soglia` gira **dopo**, in un solo processo, con il suo
parametro `seme`. Non esiste stato di generatore da dividere fra processi né corsa critica sul
seme.

Restano due condizioni, entrambe verificate:

1. **stessi valori** — garantito dalla purezza di `erosioni_giorno` e dal test di non
   regressione;
2. **stesso ordine** — `executor.map` restituisce i risultati nell'ordine degli argomenti, non
   in quello di completamento.

La seconda condizione è **più forte del necessario**, e questo è il punto interessante:
`bootstrap_soglia` costruisce una `pivot_table` indicizzata per `data` e ordinata per capacità,
quindi l'ordine delle righe in ingresso non raggiunge il generatore in alcun modo. Verificato
mescolando le righe: K\* e intervallo identici. L'ordinamento deterministico serve dunque alla
riproducibilità *bit a bit dei CSV*, non alla correttezza del bootstrap. Che la replicabilità
poggi su **due garanzie indipendenti** invece che su una è voluto.

Controprova necessaria: con seme diverso l'intervallo cambia. Se non cambiasse, i test di
riproducibilità non proverebbero nulla.

### Prodotti

`src/mgp/parallelo.py` (nuovo), `batteria.griglia_capacita` e `GRIGLIA_CAPACITA_MW`,
`scripts/11_verifica_parallelo.py` (non regressione, seme, speedup; da rieseguire ogni volta
che si tocca `parallelo`, `batteria` o la griglia), `scripts/06` collegato al runner con
`--processi`. Quattordici test nuovi in `tests/test_parallelo.py`: **117 test verdi**.

La parallelizzazione è **riutilizzabile senza modifiche per il 2020 e il 2022**: prende una
lista di giorni qualsiasi. Il primo run completo resterà però al solo 2024, con gli altri due
anni da aggiungere a 2024 consolidato.

Nulla è stato lanciato: il run completo e il bootstrap sono il passo successivo.


---

## 2026-08-28 — Cambio di impianto: la previsione a D-1 diventa il cuore statistico

Il relatore ha approvato un **impianto a due fasi**, e questo cambia il baricentro della tesi.
Fino a oggi la batteria pianificava sui prezzi reali (previsione perfetta, D-22) e
l'incertezza veniva dal ricampionamento dei giorni (D-26). Da ora:

* **fase 1**: si prevede il prezzo orario del giorno D usando solo l'informazione disponibile
  a D-1, e la batteria pianifica su quei prezzi **previsti**;
* **fase 2** (già costruita e validata): il piano si inserisce nelle curve d'asta reali, si
  ricalcola l'equilibrio, si misurano profitto effettivo ed erosione.

Il **bootstrap dei giorni esce dall'impianto**: l'incertezza non viene più dal ricampionamento
ma dall'errore di previsione. Registrato come D-37, che supera D-22 e D-26. La previsione
perfetta **non si butta**: resta il limite superiore contro cui misurare tutto.

Il punto che vale la pena fissare: l'obiettivo **non è prevedere bene**. È caratterizzare
l'errore e la sua propagazione. La previsione è il motore che rende la batteria non
onnisciente; l'oggetto statistico è l'errore.

### La fase 2 non accettava un piano da previsione, e il motivo era sottile

Verificato prima di toccare qualsiasi cosa. In `erosione` il parametro `prezzi_riferimento`
faceva **due lavori insieme**: costruiva il piano *e* valorizzava il profitto price taker.
Passandogli le previsioni, il piano sarebbe stato giusto ma π_PT sarebbe risultato valorizzato
ai prezzi **previsti** — cioè avremmo misurato il profitto che la batteria *credeva* di fare,
non quello che avrebbe fatto. L'erosione non sarebbe più stata confrontabile con quella del
perfect foresight.

Risolto con `prezzi_piano` (D-38), additivo: con il default `None` il comportamento è identico
a prima. Verifica su tre giornate reali e sei capacità, **162 confronti esatti** — non al
centesimo, bit a bit. Il degrado continua a modellare il piano e a farlo sui prezzi del piano;
il parametro K (D-35) resta fuori dal piano, verificato ai due regimi.

Aggiunto il campo `profitto_atteso`: lo stesso piano valorizzato ai prezzi su cui è stato
costruito. Servono **tre** grandezze, non due — atteso, price taker realizzato, price maker
realizzato — perché le due perdite sono concettualmente diverse: quella da **incertezza
informativa** (perfect foresight meno previsione, entrambi ai prezzi veri) e quella da
**cannibalizzazione** (price taker meno price maker, a parità di piano).

**La proprietà di cancellazione dell'erosione sopravvive.** π_PT e π_PM restano entrambi
valorizzati sui prezzi ricostruiti, con e senza accumulo: l'errore di ricostruzione entra
identico nei due termini e si semplifica. La previsione cambia *quale* piano si costruisce,
non *come* lo si valorizza.

### Due cose emerse dai controlli, entrambe sostanziali

**La soglia di convenienza dell'arbitraggio è oltre il doppio di quella analitica.** La
formula `cv · η_s + p · (1 − η)` dà ~8 €/MWh; misurata su un profilo sinusoidale a 24 ore, la
soglia vera è **~18 €/MWh senza degrado e ~42 con degrado a 12 €/MWh**. Il motivo è il
**vincolo di durata**: con quattro ore la batteria non transa nell'ora estrema ma su finestre
di quattro ore, e su un profilo liscio cattura molto meno dello spread nominale. La formula
chiusa va quindi usata come ordine di grandezza, mai come soglia operativa.

**Un errore di previsione non può invertire l'ordine fisico delle operazioni.** Il primo test
scritto — previsione esattamente rovesciata — è fallito, e correttamente: la batteria dovrebbe
scaricare prima di aver caricato, mentre parte da stato zero con ciclo chiuso. Il piano è
*infeasible*, non subottimo. L'errore previsivo può spostare **quando** si opera, non l'ordine
carica→scarica. È un vincolo che limita strutturalmente quanto danno l'errore può fare, ed è
esso stesso un risultato.

Il test riprogettato è calcolabile a mano: prezzi veri (100, 200, 300, 150), previsione
(200, 100, 150, 300) → la batteria **crede** di fare +20.000 € e ne fa **−5.000**, con il price
maker ancora peggiore. Su una previsione sbagliata la retroazione **aggrava la perdita** invece
di erodere un margine: è un meccanismo diverso dalla cannibalizzazione, e va tenuto distinto.

### La serie storica: 2023-2024, prezzi ufficiali

Estratti 731 giorni, **17.544 ore**, nessun buco. Si prevedono i prezzi **ufficiali GME** e non
i ricostruiti: è quello che osserva un operatore reale, e prevedere la propria ricostruzione
significherebbe prevedere anche il proprio errore di ricostruzione, che non è un fenomeno di
mercato.

Media 117,58 €/MWh, dev. std 33,89, minimo **0,10**, massimo 295,00. **Nessun prezzo ≤ 0**: il
logaritmo resta comunque escluso, perché con un minimo di 0,10 sarebbe fragile per costruzione
e sul MGP i prezzi negativi sono ammessi fino a −500.

**Un difetto trovato e corretto**: la prima versione costruiva l'istante come `data + ora`, che
sui giorni di cambio ora produce un **istante duplicato e un buco**. In 183 giorni il totale
quadrava lo stesso, perché +1 e −1 si compensano, quindi il conteggio non lo rivelava.
Trattamento (a), D-40: 24 slot in ora locale, media delle due occorrenze dell'ora ripetuta e
interpolazione di quella mancante. Quattro slot ricostruiti in due anni, tutti alle 02:00. Che
le due occorrenze siano davvero la stessa ora si legge nei dati: 110,00 e 113,00 il 29/10/2023,
95,35 e 97,64 il 27/10/2024. Vale per la **sola serie di previsione**; la fase 2 continua a
usare i periodi d'asta reali.

### La specifica SARIMAX, letta dal correlogramma

Le due stagionalità, misurate su ottobre 2023 – marzo 2024:

* **giornaliera, forte**: profilo da 88 €/MWh alle 3-4 a 135 alle 19, ampiezza **47,8 €/MWh,
  il 44% della media**, con doppio picco (mattutino a 129, serale a 135) e ventre a 95;
* **settimanale, modesta**: feriali 110-113, sabato 101, domenica 97, ampiezza 15,8 €/MWh. Ma
  tolto il profilo orario il giorno della settimana spiega solo il **5,2%** della varianza
  residua.

La differenziazione **non la decidono i test** (con d=1 la dev. std è già 11,49 contro 9,91
della doppia) ma l'ACF:

| | ACF a 24, 48, 72, 96, 120 |
|---|---|
| d=1 | +0,62 +0,57 +0,53 +0,53 +0,52 |
| d=1 e D=1 | −0,43 −0,01 −0,05 +0,00 −0,06 |

Con la sola differenza prima la stagionalità **non decade affatto**. Con anche quella
stagionale collassa e resta **una sola punta negativa a lag 24 che taglia netto** (PACF
−0,429): la firma di una media mobile stagionale di ordine 1. Da qui **D=1, P=0, Q=1, s=24**,
che non è una scelta ma una lettura.

A lag 168 resta +0,129: struttura settimanale residua, che i **regressori di Fourier** devono
assorbire. Non una seconda stagionalità — SARIMA ne ammette una sola e differenziare a 168
costerebbe una settimana di burn-in — ma due coppie di armoniche più dummy sabato, domenica e
festivi italiani (Lunedì dell'Angelo incluso). Sette regressori, tutti leggibili.

### La selezione dell'ordine, e un tranello evitato

| Ordine | AIC | BIC | par | σ² | convergenza |
|---|---|---|---|---|---|
| **(2,1,1)** | **63.572,10** | 63.657,01 | 12 | 84,20 | **No a maxiter=50** |
| (1,1,2) | 63.575,47 | 63.660,38 | 12 | 84,24 | Sì |
| (1,1,1) | 63.833,29 | 63.911,12 | 11 | 86,79 | Sì |
| (0,1,1) | 64.319,99 | 64.390,75 | 10 | 91,81 | Sì |

Il vincitore per AIC **non era convergente**: l'ottimizzatore si era fermato per esaurimento
di iterazioni, non perché avesse trovato il massimo. **Un AIC non convergente non è
confrontabile con uno convergente**, e adottarlo avrebbe significato scegliere il modello su
un numero che non misura ciò che dovrebbe.

Rilanciato con `maxiter=200`: **converge in 55 iterazioni**, cinque più del limite, con AIC
identico al millesimo (63572,101 contro 63572,104). La stima era già all'ottimo, mancava solo
la conferma formale. Il confronto è quindi valido e **(2,1,1) vince legittimamente** — anche
se per soli 3,37 punti su 63.572 e a parità di parametri, quindi la scelta non è delicata.

Conseguenza operativa registrata nel codice: `maxiter` predefinito portato a **200**. Una
stima non convergente non è un errore visibile — restituisce numeri plausibili — e nelle
ristime mensili nessuno guarderebbe il diagnostico.

Quello che il confronto dice senza ambiguità è che **la parte autoregressiva serve**: da
(0,1,1) a (1,1,1) l'AIC scende di 487 punti, e il secondo termine ne vale altri 258. Lì il
margine non è ambiguo.

**Ljung-Box p < 0,0001 su tutti i candidati.** Su 8.760 osservazioni il test rifiuta per
scostamenti minimi: non è una bocciatura, è un numero da dichiarare. L'autocorrelazione
residua è materia del passo successivo, dove la struttura dell'errore è l'oggetto e non il
disturbo.

**σ² ≈ 84 corrisponde a una dev. std dei residui di ≈ 9,2 €/MWh, ma a un passo.** Le previsioni
sono a 24 passi: l'errore vero sarà sensibilmente maggiore, e ci si attende che cresca con
l'orizzonte, perché le ore serali del giorno D distano 30-44 ore dall'ultima osservazione.

### Prodotti e prossimo passo

`src/mgp/previsione.py` (nuovo), `prezzi_piano` e `profitto_atteso` in `batteria.erosione`,
`parallelo.serie_prezzi`/`prezzi_giorno`, `scripts/12_serie_prezzi.py`,
`scripts/13_seleziona_ordine.py`. `statsmodels 0.15.0` aggiunto a `requirements.txt`.
Cinque test nuovi sul piano da previsione: **122 test verdi**.

Il passo successivo è la **previsione a origine mobile su tutto il 2024** — 12 ristime mensili
e 366 previsioni a 24 passi — da cui esce la caratterizzazione dell'errore: per ora del giorno,
autocorrelazione, code, eteroschedasticità.


---

## 2026-08-29 — La firma dell'errore di previsione: sei dimensioni e una sintesi

Previsione a origine mobile completata su tutto il 2024: **8.784 ore, 366 giorni, 11 ristime
mensili, 7 ore e 14 minuti** di calcolo. Da qui la caratterizzazione dell'errore
$e(g,h) = p_{\text{reale}} - p_{\text{previsto}}$, che è il pezzo statistico centrale della
fase 1. Non interessa quanto il modello sbagli — quello lo dice l'RMSE, 14,75 €/MWh — ma
**come** sbaglia, perché è quella struttura che si propagherà al piano della batteria.

Prodotti in `scripts/15_errore_previsione.py`, quattro figure in `output/figure/15_*`.

### 1. L'errore segue l'ora del giorno, non l'orizzonte

Varia di **2,4 volte** fra l'ora migliore e la peggiore: RMSE 8,22 €/MWh allo slot 0, **19,97
allo slot 14**. Le ore notturne piatte si prevedono bene (8-12), il pomeriggio male.

* correlazione fra RMSE orario e **variabilità** del prezzo in quell'ora: **+0,931**
* correlazione con il **livello** medio del prezzo: **+0,185**

L'aspettativa di partenza — errore massimo nei picchi delle 8 e delle 19 — è **per metà
smentita**. L'ora 8 è effettivamente fra le peggiori (17,80), ma il picco serale delle 19, che
è l'ora di prezzo più alto dell'anno (138 €/MWh), si prevede **meglio** (16,61) del ventre
pomeridiano. Il picco serale è alto ma regolare; il pomeriggio è mediamente basso ma erratico,
perché dipende dal fotovoltaico.

**Avvertenza di identificazione, dichiarata**: l'origine è sempre la fine di D-1, quindi
l'orizzonte *h* coincide sempre con l'ora *h−1*. Le due variabili **non sono separabili** su
questi dati. Si può però escludere che sia un puro effetto di orizzonte, perché lo schema non
è monotono: scende da 12,31 alle 3 a 10,04 alle 6, risale a 19,97 alle 14, ridiscende a 10,65
alle 23.

**Il fatto emerso e non cercato**: l'errore standard **dichiarato** dal SARIMA cresce monotono
da 8,60 a 17,62 €/MWh, come impone la teoria — l'incertezza è funzione dell'orizzonte. Quello
**realizzato** segue l'ora. Le due curve si incrociano tre volte e il rapporto
realizzato/dichiarato va da **0,60** alle ore 5-6 e 22-23 a **1,15** alle 14. Il modello ha
una teoria dell'errore che dipende solo dalla distanza temporale, mentre l'errore vero dipende
da quale ora si prevede: prende il livello quasi giusto e **sbaglia la forma lungo la
giornata**. Figura `15_errore_orario`.

### 2. Non distorto, molto disperso

Media **0,0148** €/MWh, mediana 0,0352, test t su media nulla **p = 0,925**. Il bias massimo
per ora del giorno vale **0,29 €/MWh** contro una dispersione di **14,75**.

Il modello è praticamente non distorto: **tutto l'errore è dispersione**. Non c'è una
correzione sistematica da applicare — nessun aggiustamento del tipo «alza i picchi del tot» —
si può solo convivere con la varianza, ed è quella che si propagherà al piano.

Quantili: p1 −42,87, p25 −7,83, p50 +0,04, p75 +7,54, p99 +39,92.

### 3. Code spesse, e concentrate dove si guadagna

Asimmetria **−0,0002** (perfettamente simmetrica), **curtosi in eccesso +3,97**.

| Oltre k·σ | Osservato | Gaussiana | Rapporto |
|---|---|---|---|
| 1σ | 23,14% | 31,73% | **0,7×** |
| 2σ | 5,19% | 4,55% | 1,1× |
| 3σ | 1,67% | 0,27% | **6,2×** |
| 4σ | 0,638% | 0,006% | **101×** |
| 5σ | 0,148% | ~0% | **2.581×** |

Più massa al centro *e* nelle code, meno nelle spalle. **L'1% peggiore delle ore porta il 19,0%
della somma dei quadrati; il 5% peggiore il 45,4%.** Figura `15_errore_forma`: l'istogramma da
solo ingannerebbe, perché le code sono invisibili proprio dove contano; il diagramma
quantile-quantile mostra la classica S dello scostamento agli estremi.

**Il legame che collega la fase 1 alla redditività.** Il RMSE giornaliero correla:

* con lo **spread reale** del giorno: **+0,600** (p = 3·10⁻³⁷)
* con la **volatilità** del giorno: **+0,638** (p = 3·10⁻⁴³)
* con il **livello medio** del giorno: +0,045, **non significativo** (p = 0,39)

| Quintile di spread | Spread (€/MWh) | RMSE medio | Errore sullo spread |
|---|---|---|---|
| 1 | 20–47 | 9,89 | **−10,01** |
| 2 | 47–56 | 9,90 | −1,12 |
| 3 | 57–66 | 11,65 | +5,04 |
| 4 | 66–79 | 13,19 | +8,96 |
| 5 | **79–158** | **20,56** | **+37,58** |

L'errore **raddoppia** nelle giornate a spread ampio, cioè proprio quelle in cui l'arbitraggio
vale di più. E l'ultima colonna dice qualcosa di peggio: nelle giornate migliori il modello
**sottostima lo spread di 37,58 €/MWh in media**.

Figura `15_errore_spread`, pannello destro: lo spread **previsto** vive in una fascia stretta,
40–80 €/MWh, mentre quello **reale** spazia da 20 a 158. Il modello **contrae lo spread verso
la sua media** — comportamento atteso di un modello a ritorno in media su orizzonte lungo, ma
qui la conseguenza è specifica e grave: la batteria vede quasi la stessa opportunità ogni
giorno. Lo spread è sottostimato nel **65%** delle giornate.

### 4. Memoria dentro la giornata, nessuna fra giornate

ACF dei residui: **+0,849** a lag 1, +0,670 a lag 2, +0,518 a lag 3. La PACF vale +0,849 a lag
1, **−0,184 a lag 2** e poi si annulla: struttura di tipo autoregressivo del primo ordine.

Ljung-Box rifiuta massicciamente a 24, 48 e 168 (p = 0 in tutti i casi). **I residui non sono
bianchi.** Va dichiarato senza attenuazioni: resta segnale non sfruttato, e il modello si
potrebbe migliorare. Con 8.784 osservazioni il test rifiuterebbe comunque per scostamenti
minimi, ma un'ACF di 0,849 a lag 1 non è uno scostamento minimo.

Il punto però è **dove** vive quella memoria. L'ACF dell'errore **medio giornaliero** vale
+0,034 a lag 1, dentro la banda: **le giornate difficili non si presentano a grappoli**. Una
giornata sbagliata non ne annuncia un'altra.

È il verso peggiore per il piano della batteria. Un errore coerente per l'intera giornata
sbaglia l'**ordinamento** delle ore — che è esattamente ciò che determina quando caricare e
quando scaricare — mentre errori indipendenti si compenserebbero.

*(Nota di metodo: l'interpretazione «le giornate difficili vengono a grappoli» era stata
scritta nel report **prima** di vedere i dati, che la smentiscono. È stata sostituita con un
commento condizionato al risultato. Scrivere l'interpretazione prima del numero è un errore da
non ripetere.)*

### 5. Eteroschedasticità: a U sul livello, monotona sulla volatilità

Sul **livello del prezzo previsto** — e i decili si costruiscono sul previsto, non sul
realizzato, perché raggruppare per il realizzato è contaminato per costruzione, e infatti dava
un bias apparente da −14,88 a +10,92 che è quasi tutto artefatto:

| Decile previsto | RMSE |
|---|---|
| più basso (28–77 €/MWh) | **22,01** |
| centrali | **10,96** |
| più alto (141–215) | **20,63** |

**Andamento a U: l'errore raddoppia a entrambi gli estremi.** La correlazione di rango vale
+0,001 (p = 0,92) e da sola direbbe «nessuna eteroschedasticità»: cerca monotonia, e qui la
relazione non è monotona. La tabella dice più del coefficiente.

Sulla **volatilità della giornata** la relazione è invece monotona e forte:

| Quintile di volatilità | Volatilità (€/MWh) | RMSE medio |
|---|---|---|
| 1 | 4,6–13,3 | 9,93 |
| 3 | 16,2–18,8 | 10,97 |
| 5 | **23,7–50,8** | **20,45** |

L'errore **raddoppia** dai giorni tranquilli a quelli agitati. È l'anello che lega l'errore di
previsione al **regime di mercato**, e va nella direzione sfavorevole: i regimi volatili sono
quelli in cui l'accumulo guadagna.

### 6. Intervalli larghi al centro, stretti nelle code

| Livello nominale | Copertura osservata | Scarto | Ampiezza mediana |
|---|---|---|---|
| 50% | 64,7% | **+14,7 pp** | 22,99 |
| 80% | 88,2% | +8,2 pp | 43,68 |
| 90% | 93,6% | +3,6 pp | 56,06 |
| 95% | 96,0% | +1,0 pp | 66,81 |
| 99% | 98,1% | **−0,9 pp** | 87,80 |

**Lo scarto decresce in modo monotono e cambia segno.** È la firma esatta di intervalli
gaussiani costruiti su un errore leptocurtico: troppo larghi al centro, troppo stretti nelle
code. Non è un difetto di *ampiezza* ma di *forma*, ed è la stessa cosa vista alla dimensione
3, letta dal lato dell'incertezza dichiarata.

Rapporto realizzato/dichiarato complessivo **0,895**: il modello è mediamente prudente. La
miscalibrazione è però **strutturata per ora** e rispecchia la dimensione 1: copertura al 90%
pari a **97-99% nelle ore notturne** (troppo largo) e **86,9-88,8% alle ore 13-15** (troppo
stretto). Proprio nelle ore che contano per l'arbitraggio il modello è più sicuro di quanto
dovrebbe. Figura `15_calibrazione`.

### La sintesi: la firma di questo errore

Cinque tratti, che si tengono:

1. **non distorto ma molto disperso** — niente da correggere, solo varianza da subire;
2. **strutturato per ora del giorno**, con il massimo nel ventre pomeridiano e il minimo di
   notte, e con il modello che crede invece di sbagliare in funzione dell'orizzonte;
3. **leptocurtico e simmetrico** — quasi sempre piccolo, rarissimamente enorme, con il 5%
   peggiore delle ore che porta quasi metà dell'errore quadratico;
4. **coerente dentro la giornata, indipendente fra giornate** — non si compensa, sbaglia
   l'ordinamento;
5. **crescente con volatilità e spread** — grande dove si guadagna.

### Che cosa conterà quando l'errore si propagherà al piano (punto 3)

Quattro caratteristiche puntano tutte nella stessa direzione, e la previsione è che **la
perdita da previsione imperfetta sarà più che proporzionale all'errore medio**.

**La contrazione dello spread è il meccanismo principale.** Prevedendo 40-80 €/MWh quando il
vero spread va da 20 a 158, la batteria vede quasi la stessa opportunità ogni giorno e
**pianificherà quasi allo stesso modo ogni giorno**. Perderà soprattutto le giornate
eccezionali, che sono quelle che fanno il margine annuo. È un effetto sul *livello* del
profitto, non sul suo rumore.

**La coerenza intragiornaliera impedisce la compensazione.** Con ACF a 0,849, se il modello
sbaglia al mattino sbaglia nello stesso verso nelle ore seguenti: l'errore non si media via
lungo le 24 ore, sposta l'intero profilo.

**L'errore è massimo nell'ora di carica.** Il minimo giornaliero cade spesso nel ventre delle
13-15, che è l'ora peggio prevista dell'intera giornata (19,97 €/MWh).

**L'errore è massimo nelle giornate migliori.** Correlazione +0,600 con lo spread: il danno si
concentra dove c'è da guadagnare.

Un vincolo che invece **limita** il danno, ed è emerso dai test del 28/08: un errore di
previsione può spostare **quando** la batteria opera, non l'**ordine** carica→scarica, perché
lo stato di carica parte da zero e il ciclo dev'essere chiuso. Il piano peggiore possibile non
è quello rovesciato, che sarebbe *infeasible*, ma quello che opera nelle ore sbagliate.


---

## 2026-08-29 — La propagazione: la mia previsione teorica è smentita dai dati

Punto 3 dell'impianto a due fasi: l'errore di previsione si propaga al piano della batteria e
al risultato. 366 giorni, 13 capacità, due origini del piano — previsione perfetta e
previsione SARIMAX — a confronto sulle stesse curve d'asta.
`scripts/16_propagazione.py`, ~15 minuti su otto processi.

Le due ipotesi erano state formulate **prima** di guardare i dati, come previsioni opposte:

* la **contrazione dello spread** avrebbe dovuto peggiorare le cose, perché il modello
  prevede spread in 40-80 €/MWh contro un reale di 20-158 e li sottostima nel 65% delle
  giornate;
* il **vincolo di ammissibilità e l'ordinamento** avrebbero dovuto proteggere, perché il
  piano dipende dall'ordine delle ore e non dal livello dei prezzi.

Il disegno le rendeva distinguibili: la prima lega l'efficienza allo spread, la seconda alla
correlazione di rango. **La prima è smentita, la seconda è confermata con forza.**

### A. I due piani si somigliano più di quanto l'errore facesse temere

**Nessuna giornata su 366 in cui la previsione faccia rinunciare a operare**, e nessuna in cui
faccia operare quando non conveniva. Il piano è non vuoto in tutte e 366 le giornate con
entrambe le origini.

* ore di **carica** azzeccate: **78,4%**
* ore di **scarica** azzeccate: **86,2%**
* ora del **minimo** indovinata esattamente: **24,6%**
* ora del **massimo** indovinata esattamente: **49,2%**

Il contrasto fra le ultime due coppie di numeri è il punto. Il modello sbaglia l'ora esatta
del minimo in tre giornate su quattro, eppure sceglie correttamente quasi quattro ore di
carica su cinque. La ragione è la **durata**: con quattro ore la batteria non opera nell'ora
estrema ma su una finestra, e le ore vicine hanno prezzi vicini. Sbagliare di un'ora costa
poco.

### B. Il costo dell'incertezza: 10,4% del profitto

A 25 MW, dove l'effetto sul prezzo è trascurabile e la differenza fra i due piani è **pura**
perdita informativa:

| | € sull'anno |
|---|---|
| profitto che la batteria **si aspettava** | 1.696.701 |
| profitto **realizzato** | **1.684.613** |
| profitto con **previsione perfetta** | 1.879.240 |

**Perdita da incertezza informativa: 194.627 €, il 10,4%** del limite superiore. Efficienza
informativa **89,6%**.

**Attenzione all'illusione, che sull'aggregato inganna.** Atteso meno realizzato vale in totale
soli 12.088 € (+0,6%), il che farebbe pensare che la batteria sappia prevedere il proprio
guadagno. È **compensazione, non accuratezza**: giorno per giorno l'illusione ha media
assoluta di **1.552 €** e **media assoluta relativa del 48,1%**, con il 53,3% di giornate in
cui il modello si aspetta più di quanto realizza. Sul singolo giorno la batteria si sbaglia
di quasi la metà; sull'anno gli errori si annullano. Riportare solo il totale sarebbe
fuorviante.

### C. Ipotesi 1 SMENTITA: la contrazione dello spread non peggiora le cose

| Quintile di spread | Spread (€/MWh) | Efficienza media | Perdita media (€) |
|---|---|---|---|
| 1 | 20–47 | **0,838** | 334 |
| 2 | 47–57 | 0,899 | 396 |
| 3 | 57–66 | 0,894 | 490 |
| 4 | 66–79 | **0,911** | 551 |
| 5 | **79–158** | 0,899 | 891 |

Correlazione spread ~ efficienza: **+0,120** (p = 0,02). **Positiva, non negativa.**

La previsione era che l'efficienza crollasse nelle giornate a spread ampio. Accade il
contrario: l'efficienza è **più bassa nel quintile a spread stretto** (0,838) e resta attorno
a 0,90 in tutti gli altri. La correlazione con la perdita **in euro** è invece +0,250, ma
quella è quasi meccanica — cresce anche il profitto potenziale — e non decide nulla.
L'avvertenza era stata scritta nel report prima di vedere il risultato, ed è servita.

Perché l'ipotesi era sbagliata: la contrazione riguarda il **livello** dello spread, mentre il
piano dipende dall'**ordinamento**. Nelle giornate a spread ampio il segnale è grande rispetto
all'errore, quindi l'ordinamento sopravvive anche a una previsione mediocre. Nelle giornate
piatte l'errore è comparabile allo spread stesso e scompiglia l'ordine delle ore — ed è lì che
l'efficienza cede.

### D. Ipotesi 2 CONFERMATA: conta l'ordinamento, non il livello

| Efficienza correlata con | r | p |
|---|---|---|
| **correlazione di rango** previsione/realtà | **+0,735** | 2·10⁻⁶³ |
| correlazione lineare | +0,705 | 3·10⁻⁵⁶ |
| **errore sul livello dello spread** | **−0,046** | 0,38 (**non significativo**) |

| Quintile di rango | Rango | Efficienza media |
|---|---|---|
| 1 | 0,08–0,78 | **0,695** |
| 3 | 0,86–0,92 | 0,921 |
| 5 | 0,95–0,99 | **0,971** |

L'errore in livello è **irrilevante** per il risultato: il coefficiente è praticamente nullo e
non significativo. Conta solo se il modello mette le ore nell'ordine giusto.

Correlazione di rango mediana sull'anno: **0,884**; il 45,6% delle giornate sta sopra 0,9. È
questo che spiega perché un errore da 14,75 €/MWh di RMSE costi solo il 10,4% del profitto:
**il SARIMAX sbaglia i prezzi ma azzecca la classifica delle ore.**

### E. L'erosione peggiora, e la soglia si abbassa

L'erosione resta misurata a parità di piano dentro ciascuna origine, quindi continua a isolare
il solo effetto sul prezzo; il confronto fra origini va letto come «quanta della propria fonte
di reddito distrugge una flotta che pianifica come pianifica davvero».

| Capacità | Erosione mediana perfetta | da previsione | q90 perfetta | da previsione |
|---|---|---|---|---|
| 100 MW | 0,0714 | 0,0786 | 0,1518 | 0,1958 |
| 400 MW | 0,2395 | 0,2657 | 0,4177 | 0,5721 |
| 1500 MW | 0,7855 | 0,8873 | 1,1357 | 1,9170 |

**Soglia K\* (erosione lorda, 90° percentile, griglia grossolana):**

| Livello | Previsione perfetta | Da previsione |
|---|---|---|
| 10% | 60,6 MW | **33,7 MW** |
| 20% | 147,5 MW | **103,6 MW** |

Una flotta che pianifica su previsioni realistiche **diventa price maker a una capacità
inferiore del 44%** al livello del 10%. Il risultato va preso con due riserve: è erosione
**lorda**, senza la sottrazione del pavimento di discretezza (D-30), e la griglia qui è a 13
punti, non a 132.

Il meccanismo non è solo il denominatore più piccolo. L'erosione **assoluta** è anch'essa
maggiore: 7,68 M€ contro 7,46 a 400 MW, 93,8 contro 88,5 a 1500. Un piano meno mirato guadagna
meno **e** fa più danno al prezzo — presumibilmente perché opera in ore scelte da un segnale
rumoroso, dove la curva può essere più ripida.

### La sintesi

**L'errore di previsione costa il 10,4% del profitto, molto meno di quanto la sua dimensione
facesse temere, e per una ragione precisa: l'arbitraggio non ha bisogno di prezzi giusti, ha
bisogno dell'ordine giusto delle ore.** Un RMSE di 14,75 €/MWh su prezzi che ne valgono in
media 118 lascia intatta una correlazione di rango mediana di 0,884, e su quella si costruisce
un piano che cattura il 90% del valore ottimo.

Le due caratteristiche dell'errore che sembravano più minacciose alla fase 1 — la contrazione
dello spread e la concentrazione dell'errore nelle giornate redditizie — **non mordono**,
perché agiscono sul livello e non sull'ordinamento. Quella che morde è la sola che scompiglia
l'ordine: l'errore relativamente grande nelle giornate **piatte**, dove è comparabile al
segnale.

Il danno vero non è dove lo si cercava. Non è sulle giornate eccezionali, che restano
riconoscibili; è sulle giornate ordinarie, dove il margine è sottile e basta poco a invertire
la classifica delle ore.

**Conseguenza per il capitolo 5**: il conto economico va rifatto sul profitto price maker con
piano da previsione, non da previsione perfetta. La differenza è il 10,4% sul margine e un
K\* inferiore del 44%: entrambi spostano il VAN nella direzione sfavorevole.


---

## 2026-08-30 — K* definitiva sulla griglia a 132 punti, nelle due varianti di piano

Rifatta la stima della soglia con l'infrastruttura completa: griglia a **132 punti**, erosione
**netta** del pavimento di discretezza (D-30), due varianti del piano a confronto — previsione
perfetta e previsione SARIMAX. 366 giorni, 96.624 righe, circa un'ora su otto processi.
`scripts/16_propagazione.py --completa` per il calcolo, `scripts/17_soglia_definitiva.py` per
la soglia.

### Il ruolo del bootstrap, che va precisato

D-37 aveva tolto il bootstrap dei giorni dall'impianto: l'incertezza del modello non viene più
dal ricampionamento ma dall'errore di previsione. Il bootstrap resta però come **strumento
inferenziale** per l'intervallo di confidenza di K\*, che è una stima campionaria come
un'altra. Sono due ruoli distinti — sorgente dell'incertezza contro strumento di inferenza — e
non sono in contraddizione, ma vanno tenuti separati per non far sembrare che D-26 sia stata
reintrodotta di soppiatto.

### La verifica di non-monotonia: negativa, e senza margini di dubbio

Era la condizione posta prima di fidarsi del numero. La regola del primo attraversamento
presuppone che la curva erosione-capacità sia crescente; con 132 punti un sobbalzo locale del
quantile poteva farla scattare in anticipo.

Su 1.000 ricampionamenti, per tutte e quattro le combinazioni di origine e soglia:

* ricampionamenti con **più di un attraversamento: 0,0%** (massimo osservato: 1);
* ricampionamenti **senza** attraversamento: 0,0%;
* calo massimo della curva: **mediana −0,01 punti percentuali**, 90° percentile 0,00;
* **scarto fra ultimo e primo attraversamento: 0,00 MW, sia in media sia al massimo.**

Sulla curva osservata il calo massimo vale −0,05 punti percentuali con previsione perfetta e
−0,06 con previsione SARIMAX: rumore di arrotondamento, non un avvallamento.

**Nessuna correzione serve, e nessuna decisione nuova va registrata.** La D-41 che era stata
prenotata per l'eventualità non nasce. Vale la pena aver misurato: la frequenza da sola non
avrebbe deciso nulla, è lo scarto fra primo e ultimo attraversamento — esattamente zero — a
chiudere la questione.

### K* definitiva

Erosione netta, quantile prudenziale 90°, intervallo di confidenza al 90% da 1.000
ricampionamenti.

| Origine del piano | Soglia | **K\*** | IC 90% |
|---|---|---|---|
| previsione perfetta | 10% | **75,9 MW** | 70,5 – 81,7 |
| previsione perfetta | 20% | **173,1 MW** | 157,5 – 189,0 |
| **previsione SARIMAX** | 10% | **50,1 MW** | 43,3 – 57,5 |
| **previsione SARIMAX** | 20% | **129,3 MW** | 108,0 – 142,9 |

**Il confronto è il risultato**: la soglia scende del **34,0%** al livello del 10% e del
**25,3%** al 20%. Gli intervalli di confidenza delle due varianti **non si sovrappongono** a
nessuna delle due soglie, quindi la differenza non è un artefatto campionario.

Una flotta che pianifica su previsioni realistiche diventa price maker **prima**. Lo stesso
errore che le costa il 10,4% di profitto la fa anche operare in modo meno mirato, quindi con
più effetto sul prezzo a parità di capacità installata — e l'erosione assoluta lo conferma,
non solo il rapporto.

Figura `17_curva_erosione`: le due curve sovrapposte su asse logaritmico, mediana e 90°
percentile per ciascuna, con le soglie e i quattro K\* segnati. La curva SARIMAX sta sopra
quella perfetta a ogni capacità.

Il confronto con il preliminare del 29/08 (33,7 MW) mostra quanto pesasse l'approssimazione:
quella stima era su erosione **lorda** e tredici capacità. Il pavimento sottratto alza la
soglia da 33,7 a 50,1 MW, cioè di metà. Non è un dettaglio di raffinamento: senza D-30 la
soglia sarebbe sottostimata di un terzo.

### Il pavimento, misurato separatamente per le due varianti

Va misurato per ciascuna origine, perché il piano da previsione ha un pavimento suo:

| Origine | Mediana | 80° perc. | 90° perc. | Massimo |
|---|---|---|---|---|
| perfetta | 0,69% | 1,74% | 2,66% | 12,50% |
| previsione | 0,90% | 2,30% | 3,40% | **94,94%** |

Quel 94,94% è un artefatto e va spiegato, non nascosto: cade il **1° maggio 2024**, giornata in
cui il profitto price taker a 1 MW vale **4,80 €**. Con un denominatore così piccolo il
rapporto è puro rumore — è esattamente la situazione che D-29 descrive. La soglia
`PROFITTO_MINIMO_PER_RAPPORTO` vale 1 €, quindi 4,80 € la supera e il rapporto viene calcolato
benché non significhi nulla.

Sono 2 giornate su 366 sopra il 25% e 6 sopra il 10%, quindi l'effetto sul 90° percentile
calcolato su 366 giorni è contenuto. È stato però verificato invece che assunto:

| Campione | K\* perfetta | K\* previsione | Divario |
|---|---|---|---|
| tutti i 366 giorni | 75,9 | 50,1 | −34,0% |
| senza pavimento >10% (n = 360/365) | 77,0 | 55,6 | −27,8% |
| senza pavimento >5% (n = 348/358) | 78,7 | 57,0 | −27,6% |

**Il risultato qualitativo è robusto** — la soglia scende fra il 26 e il 34% — ma il valore
esatto dipende da come si trattano le giornate a profitto quasi nullo. Si adotta la stima sul
campione **completo**, coerentemente con D-29, che vieta di scartare le giornate a basso
differenziale perché sono quelle destinate a diventare più frequenti; e si dichiara la
sensibilità.

### Un difetto trovato dal run

L'analisi dello script 16 sulla griglia completa è fallita con un errore incomprensibile
(`Bin edges must be unique: Index([nan, nan, ...])`) perché leggeva le grandezze a una
capacità **fissata a 25 MW**, che sta nella griglia ridotta ma **non** in quella definitiva:
la griglia a 132 punti passa da 20 a 30 MW. Il filtro produceva una tabella vuota e l'errore
emergeva molto più avanti, dove la causa era irriconoscibile.

Corretto cercando la capacità **più vicina fra quelle disponibili**, con una nota esplicita nel
report quando non coincide. Le grandezze della sezione B si leggono ora a 20 MW e sono
invariate nelle quote — perdita informativa 10,4%, efficienza 89,6% — perché sono rapporti.

La lezione, che vale oltre questo caso: una costante che indicizza una griglia va **cercata**
nella griglia, non data per presente. Il fallimento silenzioso è il modo peggiore in cui un
parametro sbagliato si manifesta.


---

## 2026-08-30 — I risultati veri nei capitoli 3 e 4

Sostituiti i segnaposto con i numeri del 2024. Compilazione locale: **76 pagine, zero
errori**; restano solo i due `sec:mgp` preesistenti del capitolo 2, fuori perimetro e già
segnalati.

### Un segnaposto che chiedeva un controllo, e il controllo smentisce il testo

A `03_strategia_ottima.tex` c'era scritto di «quantificare l'affermazione precedente
ripetendo il calcolo dell'erosione con piani subottimi e verificando di quanto si sposta
K\*». L'affermazione da quantificare era:

> «La previsione perfetta distorce quindi il *livello* dei profitti più di quanto distorca la
> *soglia*.»

**È falsa.** Il livello scende del 10,4%, la soglia del 34,0%: la soglia è distorta più di
**tre volte** il livello, non meno. Il passaggio è stato riscritto come congettura smentita,
con la ragione: un piano meno mirato guadagna meno **e** incide di più sul prezzo, perché
opera in ore scelte da un segnale rumoroso invece che dove la curva d'offerta è più piatta.
Il numeratore dell'erosione cala meno del denominatore.

L'assunzione di previsione perfetta non era quindi conservativa, come si era supposto, ma
**ottimistica proprio sulla grandezza che la tesi vuole stimare**. È il tipo di errore che un
segnaposto serve a intercettare, e in questo caso l'ha fatto.

### Che cosa è entrato

**Capitolo 3** — riscritta la coda della sezione sull'incertezza:

* `sec:due-fasi`, che sostituisce la vecchia «Bootstrap dei giorni storici». L'incertezza non
  viene più dal ricampionamento ma dall'errore di previsione; il bootstrap resta come
  strumento inferenziale per l'intervallo di confidenza, ed è scritto che sono due ruoli
  distinti. Le due alternative scartate (dati funzionali, linearizzazione) restano, spostate.
* `sec:due-varianti`, che sostituisce «La previsione perfetta»: il perfect foresight passa da
  assunzione operativa a limite superiore, e contiene la congettura smentita.
* `sec:ordinale`, nuova: **l'arbitraggio è un problema ordinale, non cardinale**. È il
  risultato portante, con il meccanismo (la durata di quattro ore fa operare su una finestra,
  e le ore contigue hanno prezzi simili), la localizzazione del danno (giornate ordinarie e
  piatte, non eccezionali) e le tre delimitazioni dichiarate come portata e non come
  debolezza: durata quattro ore, ciclo giornaliero singolo con SoC nullo e ciclo chiuso,
  valorizzazione ai prezzi veri.

**Capitolo 4** — due sezioni nuove:

* `sec:previsione`: orizzonte e sua giustificazione, specifica SARIMAX con la lettura del
  correlogramma che fissa la parte stagionale, protocollo a origine mobile, e la
  caratterizzazione dell'errore nelle **sei dimensioni** con quattro figure;
* `sec:limiti-previsione`: i due limiti dichiarati;
* `sec:soglia-definitiva`: la verifica di monotonia, la tabella dei quattro K\*, la figura
  della curva erosione-capacità, il peso del pavimento e la sensibilità;
* `sec:propagazione`: la perdita informativa e l'illusione che sull'aggregato inganna.

**I limiti li dichiara la tesi per prima.** I residui non sono bianchi (ACF 0,849, Ljung-Box
p < 10⁻⁴): il modello è migliorabile in senso statistico. Ma il testo prosegue mostrando
perché questo **non intacca il risultato economico** — l'autocorrelazione residua riguarda il
livello, il valore dell'arbitraggio dipende dall'ordinamento — e ne trae un'indicazione
operativa: raffinare il modello sull'AIC o sulla bianchezza dei residui è la strada meno
promettente, converrebbe valutarlo sulla correlazione di rango giornaliera. Stessa cosa per
la collinearità fra ora e orizzonte: dichiarata come limite del disegno, con l'esclusione del
puro effetto di orizzonte perché lo schema non è monotono.

### Aggiunte fuori dai capitoli, entrambe additive

`acronimi.tex`: SARIMAX, ACF, PACF, RMSE, MAE, AIC. Nessuno supera `DDS 2024` in lunghezza,
quindi il parametro di larghezza dell'ambiente **non è stato toccato**.

`bibliografia.bib`: Box, Jenkins, Reinsel e Ljung (2015) per la metodologia SARIMA, e Weron
(2014) per la previsione dei prezzi elettrici. Il DOI di Weron resta `DA COMPLETARE`: un DOI
inventato è peggio di un DOI assente.

### Tre difetti trovati compilando

**`\text{\euro}` non funziona dentro l'argomento unità di siunitx.** Dodici errori di
«Undefined control sequence». Il progetto ha già la macro `\euromwh`, che è l'idioma usato
negli altri capitoli: adottata quella.

**Una collisione di acronimi introdotta il 27/08.** Nel paragrafo su Dumitrescu avevo scritto
«RTE per la Francia» intendendo il gestore di rete francese, ma `acronimi.tex` definisce già
`RTE` come *Round-Trip Efficiency*. Non si rompeva nulla perché l'avevo scritto a mano, ma
sarebbe stata una trappola per chiunque avesse usato `\ac{RTE}`. Risolto scrivendo per esteso
il nome dell'operatore.

**Biber non aggiorna le citazioni nuove in una sola passata di `latexmk`.** Le due voci
risultavano irrisolte pur essendo nel `.bcf`, e biber non emetteva alcun avviso. Risolto
eseguendo `biber main` esplicitamente e poi ricompilando. Da ricordare: quando si aggiungono
voci al `.bib`, una sola esecuzione di `latexmk` può non bastare, e il sintomo è una
citazione irrisolta **senza** messaggio di biber.


---

## 2026-08-31 — Il confronto fra regimi: la soglia segue la ripidità, non la volatilità

Completati 2022 e 2023 con la pipeline del 2024 e una sola modifica — finestra di stima
**mobile** di 365 giorni invece che crescente — e prodotto il confronto trasversale.
`scripts/18_anno_completo.py` per i due anni, `scripts/19_confronto_regimi.py` per la
lettura. Costo: 4,72 ore il 2022, 4,34 il 2023, contro le 7h14 della sola fase 1 del 2024.

I tre anni sono **tre casi, non un campione**: con tre punti non si stima una relazione, si
osserva un ordinamento e si verifica se i meccanismi trovati su un anno reggano sugli altri.
La stocasticità della tesi resta la propagazione dell'errore *dentro* ciascun anno.

### Il quadro

| | 2022 | 2023 | 2024 |
|---|---|---|---|
| Spread infragiornaliero medio | **161,71** | 78,42 | 65,51 |
| Pavimento a 1 MW (mediana) | **2,45%** | 1,07% | 0,69% |
| RMSE della previsione | **50,07** | 20,81 | 14,75 |
| Correlazione di rango mediana | 0,865 | 0,868 | 0,884 |
| Copertura al 90% nominale | **78,0%** | **98,2%** | 93,6% |
| **K\* perfetta, 10%** | **35,7** | 40,9 | **75,9** |
| **K\* previsione, 10%** | **23,2** | 30,5 | **50,1** |
| K\* perfetta, 20% | 106,7 | 112,7 | 173,1 |
| K\* previsione, 20% | 70,2 | 83,4 | 129,3 |
| Calo di K\* al 10% | −35,1% | −25,5% | −34,0% |
| Efficienza pesata per profitto | 82,6% | 88,6% | 89,6% |
| Efficienza equipesata | 81,8% | 87,3% | 88,8% |

Verifica di non-monotonia: **0,0% di ricampionamenti con attraversamenti multipli** in tutte
e dodici le combinazioni dei tre anni, scarto ultimo-primo 0,00 MW. Nessuna correzione.

### 1. La soglia è governata dalla ripidità della curva, non dalla volatilità del prezzo

L'attesa era che più volatilità significasse spread più ampi e quindi soglia più alta. **È il
contrario**, e in modo netto: il 2022 ha spread 2,5 volte il 2024 e soglia **meno della
metà**.

* per spread: 2022 (161,7) > 2023 (78,4) > 2024 (65,5)
* per pavimento a 1 MW: 2022 (2,45%) > 2023 (1,07%) > 2024 (0,69%)
* per K\*: 2022 (35,7) < 2023 (40,9) < 2024 (75,9)

Il pavimento è un **termometro della ripidità**: misura di quanto si muove il prezzo quando si
aggiunge una capacità troppo piccola per contare economicamente. Nel 2022 un solo megawatt si
sentiva quasi quattro volte più che nel 2024, perché la crisi del gas spingeva l'equilibrio
in una regione molto più ripida della curva d'offerta.

Lo si vede anche a capacità fissata: l'erosione netta mediana a 400 MW vale 0,305 nel 2022,
0,287 nel 2023 e 0,230 nel 2024. Non è un effetto della soglia scelta, è la curva intera che
si sposta.

**Un limite di identificazione da dichiarare.** Fra questi tre anni spread e ripidità sono
perfettamente co-ordinati, quindi la correlazione non separa le due spiegazioni — e con tre
punti non separerebbe nulla comunque. È il **meccanismo** a farlo: il pavimento misura
direttamente ciò che K\* misura, cioè quanto la capacità sposta il prezzo, mentre lo spread
misura quanto vale l'arbitraggio, che è un'altra cosa. Le due grandezze coincidono nel
segno per caso, non per costruzione.

### 2. Il risultato ordinale regge, ed è la verifica più forte che si potesse avere

| | Variazione fra i tre anni |
|---|---|
| RMSE della previsione | **×3,4** (14,75 → 50,07) |
| Correlazione di rango mediana | **2,3%** (0,884 → 0,865) |

L'errore in livello cambia di un fattore tre fra i regimi; l'ordinamento delle ore **quasi
per nulla**. Il risultato trovato sul 2024 — l'arbitraggio è un problema ordinale, non
cardinale — non era una proprietà di quell'anno.

**Ma l'efficienza non è funzione della sola mediana del rango**, e questo raffina il
risultato:

| | Rango mediano | Rango 10° perc. | Efficienza equipesata |
|---|---|---|---|
| 2022 | 0,865 | **0,514** | 81,8% |
| 2023 | 0,868 | 0,650 | 87,3% |
| 2024 | 0,884 | 0,696 | 88,8% |

Il 2022 e il 2023 hanno **mediana quasi identica** (0,865 e 0,868) ed efficienza molto diversa
(81,8% e 87,3%). Ciò che le distingue è la **coda bassa**: nel 2022 il decimo percentile del
rango scende a 0,514 contro 0,650. Non conta solo quanto il modello azzecchi l'ordinamento di
norma, ma **quante giornate lo sbaglia in modo grave**. È la stessa struttura leptocurtica
vista nell'errore, letta sul rango.

### 3. Il calo di K\* NON è una costante strutturale

Con due anni sembrava esserlo: −35,1% nel 2022 e −34,0% nel 2024 alla soglia del 10%. Il
terzo punto lo smentisce.

| | Soglia 10% | Soglia 20% |
|---|---|---|
| 2022 | −35,1% | −34,2% |
| 2023 | −25,5% | −26,0% |
| 2024 | −34,0% | −25,3% |

Sei valori fra −25,3% e −35,1%, mediana −30,0%. L'escursione **dentro** un anno arriva a 8,7
punti (il 2024 fra le due soglie) e **fra** anni a 9,7 punti: sono dello stesso ordine. Va
riportato come **intervallo fra un quarto e un terzo**, non come costante — e la coincidenza
fra 2022 e 2024 alla soglia del 10% era appunto una coincidenza.

### Un effetto del disegno, non del mercato: la finestra mobile ritarda sul regime

La copertura degli intervalli al 90% nominale non è né stabile né monotona nella volatilità:
**78,0% nel 2022, 98,2% nel 2023, 93,6% nel 2024**. Nel regime estremo gli intervalli sono
troppo **stretti**, in quello successivo troppo **larghi**.

L'ipotesi, formulata prima di guardare il dettaglio mensile: la finestra di stima è di 365
giorni, quindi ogni modello dichiara l'incertezza dell'**anno precedente**. Il 2022 è stimato
su un 2021 tranquillo e risulta troppo sicuro; il 2023 su un 2022 estremo e risulta troppo
prudente; il 2024 su un 2023 moderato e risulta calibrato.

I dati mensili la sostengono. Nel 2022 la copertura passa da **76% nel primo trimestre a 89%
nell'ultimo**, man mano che la finestra si riempie di dati dello stesso regime. Nel 2023 resta
invece attorno al 98% per tutto l'anno — e anche questo è coerente, perché con finestra di
365 giorni la stima contiene ancora una parte del 2022 fino a dicembre, e dicembre 2022 è
stato il mese più estremo dell'anno più estremo.

**È un effetto del disegno e va dichiarato come tale**: gli intervalli di previsione sono
affidabili solo a regime stabile, e nell'anno successivo a una transizione di regime sono
sistematicamente sbagliati, in un verso o nell'altro. Non intacca i risultati sulla soglia,
che non usano gli intervalli, ma intacca qualunque uso degli intervalli per dimensionare un
margine di rischio.

### Note di metodo

**`start_params` tolto dalle ristime**, dopo verifica. Ripartire dai coefficienti del mese
precedente porta alla **stessa** verosimiglianza (scarto relativo 8·10⁻⁸, quindi non due
ottimi locali) ma a coefficienti **esogeni** diversi fino al 2,5%, mentre quelli ARMA restano
identici alla quinta cifra. È una cresta piatta: i termini di Fourier a 168 ore e le
indicatrici di sabato e domenica descrivono lo stesso ciclo settimanale e si compensano,
quindi il blocco esogeno è **debolmente identificato**. Il 10% di tempo risparmiato non vale
coefficienti che dipendono dall'ordine delle ristime. La docstring, che dichiarava un
comportamento che il codice non aveva, ora racconta la verifica.

**La collinearità del blocco esogeno** è un difetto di parsimonia della specifica, emerso da
questa verifica. Non si tocca — ordine ed esogene sono congelati (D-39) e cambiarli
invaliderebbe i tre anni — ma va dichiarato fra i limiti, accanto ai residui non bianchi.

**Un difetto misurativo ripetuto.** La prima misura dei costi di ristima dava 24 mesi più
veloce di 12 a parità di iterazioni, il che è impossibile: era girata mentre l'estrazione dei
prezzi occupava otto processi. È la seconda volta in tre giorni, dopo lo speedup superlineare
del 28/08. Regola: **i benchmark non si lanciano in parallelo ad altro lavoro**, nemmeno
quando l'altro sembra I/O-bound — il parsing degli XML non lo è affatto.

**Coerenza fra i due percorsi.** Il 2024 è stato rigenerato con `scripts/18` a partire dagli
stessi dati già prodotti da `scripts/16` e `17`: i quattro K\* coincidono esattamente
(75,95 / 173,05 / 50,11 / 129,29).


---

## 2026-08-31 — I capitoli 3 e 4 completati con i risultati veri

Scrittura in quattro blocchi, ciascuno compilato e committato separatamente. La tesi passa
da 76 a **84 pagine**, zero errori; restano i due `sec:mgp` del capitolo 2, fuori perimetro e
già segnalati.

### Blocco 1 — i due segnaposto sostanziali del capitolo 3

`§3.2.x I valori dei parametri` e `§3.3 Modellazione del degrado`, quest'ultima prima
**interamente vuota**. Quattro precisazioni evitano altrettanti fraintendimenti: il rendimento
è un valore di ciclo e la ripartizione a parti uguali non ha conseguenze con ciclo chiuso e
prezzi positivi; il costo variabile grava sulla sola scarica; la durata di quattro ore non è
un parametro indipendente ma la stessa affermazione della condizione sul convertitore;
l'orizzonte di un giorno è un troncamento che agisce sul livello e non sull'ordinamento.

Il punto non ovvio: **la soglia analitica di convenienza sottostima quella vera di oltre il
doppio** — circa 20 €/MWh dalla formula chiusa contro ~18 senza degrado e ~42 con il costo
variabile, misurati. La ragione è il vincolo di durata, che fa operare su finestre e non
nell'ora estrema.

### Blocco 2 — che cosa determina la soglia

Nuova `§3.1.3`, collocata nel capitolo **teorico** e non fra i risultati, perché l'argomento è
algebrico e si legge nella definizione di erosione senza guardare un dato: il differenziale
compare a numeratore e denominatore del rapporto e si semplifica; ciò che resta è lo
spostamento del prezzo, che dipende dalla **pendenza** della curva.

La collocazione è una scelta di sostanza. Una previsione fatta prima e verificata dopo vale
più di una regolarità osservata a posteriori, e il capitolo 4 la verifica.

### Blocco 3 — il confronto fra regimi

Nuova `§4.7` con i risultati B e C, la tabella a tre anni e la figura `19_confronto_regimi`.
La previsione del blocco 2 è confermata e quella intuitiva smentita: ordinamento per
differenziale 2022 > 2023 > 2024, ordinamento per K\* **inverso e perfetto**.

Il limite di identificazione è dichiarato: ampiezza e ripidità sono co-ordinate per una causa
comune, la correlazione non le separa, e districarle richiederebbe un controfattuale — un anno
a differenziali ampi su curva piatta — che i dati osservativi non offrono.

### Blocco 4 — i limiti e la nota di metodo

`§4.5.4` passa da «due limiti dichiarati» a **quattro**: si aggiungono la collinearità del
blocco esogeno e la calibrazione degli intervalli, quest'ultima scomposta nelle **due ragioni
distinte** — per *forma* (gaussiani su errore leptocurtico) e per *regime* (la finestra mobile
eredita l'incertezza dell'anno precedente) — perché hanno cause e rimedi diversi. Aggiunte
anche le tre condizioni di validità del risultato ordinale, presentate come portata e non come
debolezza.

Tutti e quattro i limiti convergono sullo stesso scudo, che non è un espediente retorico ma la
conseguenza del risultato ordinale: riguardano il **livello** dei prezzi, mentre il valore
dell'arbitraggio dipende dall'**ordinamento** delle ore.

Nuova `§4.8 Una nota di metodo: gli aggregati che ingannano`, con i tre casi incontrati nel
lavoro: la compensazione che si spaccia per accuratezza (illusione totale sotto l'1% contro
una media assoluta giornaliera del 48,1%), il coefficiente che cerca la forma sbagliata
(correlazione di rango +0,001 su una relazione a U), la regolarità costruita su due punti (il
calo di K\* che sembrava costante). Il quarto caso incontrato — la misura di tempo contaminata
dalla contesa di CPU — resta **fuori dalla tesi** e vive solo in questo diario: è un errore
dell'ambiente di calcolo, non un tema metodologico della ricerca.

### Cosa resta

Un solo `DA COMPLETARE` nel capitolo 3: l'effetto numerico del vincolo orario sul regime a
quarto d'ora, che richiede un rerun mai eseguito. Nel capitolo 4 ne restano quattro, tutti
legati a numeri non ancora prodotti. Il **capitolo 5** poggia ancora sul price maker con
previsione perfetta e va rifatto sul piano da previsione.

Nota sulla sincronizzazione: la copia locale dei capitoli coincideva esattamente con l'ultimo
commit, quindi nessuna modifica fatta su Overleaf è stata sovrascritta — ma questo si può
verificare solo confrontando con il locale, e se lo studente avesse modificato senza scaricare
la divergenza andrebbe riconciliata a mano.

---

## Prossimi passi

*Sezione viva, riscritta man mano: a differenza delle voci datate qui sopra, non è
append-only. Ultimo allineamento 2026-08-28.*

**Il blocco è caduto**: il relatore ha approvato il perimetro temporale, **anno base 2024 in
regime orario**. Griglia delle capacità (132 punti) e calcolo parallelo (4,4×, anno in mezz'ora)
sono pronti e validati, ma non ancora usati per produrre risultati.

1. **Lanciare il run completo sul 2024**: 366 giorni, 132 capacità, con il bootstrap e la
   stratificazione. È il passo immediatamente successivo. Costo atteso ~30 minuti su otto
   processi a cache calda, più ~1,5 ore di parsing la prima volta.
2. **Verificare la non-monotonia della curva quantile** dentro i ricampionamenti bootstrap —
   frequenza *e* ampiezza dei sobbalzi — prima di fidarsi di K\*. Se emerge, scegliere fra
   ultimo attraversamento e lisciamento isotonico e registrare la scelta come **D-37**
   (piano dettagliato nella voce del 28/08).
3. **Aggiungere 2020 e 2022** per il confronto di volatilità, a 2024 consolidato: la
   parallelizzazione li accetta senza modifiche, e i due anni sono completi in archivio.
4. **Rerun su PT15 con il vincolo orario** (D-33), quando serva: è attivo ma non ha ancora
   prodotto numeri, e darà una K\* più bassa di prima — il valore corretto.
5. **Stratificare** per stagione e regime, e misurare quanto la soglia si sposta: la non
   stazionarietà è essa stessa un risultato.
6. **Sensitività**: durata della flotta (1, 2, 4, 8 ore), rendimento di ciclo (85/90/92%),
   costo di degrado, perimetro zonale, e i due regimi di **K** (1 contro 2,3). A parità di
   potenza una durata maggiore dovrebbe alzare la soglia: previsione da verificare.
7. **Numeri del capitolo 5**: VAN, TIR, tempo di ritorno e LCOS ai due regimi di K. L'impianto
   c'è (`economia.py`, D-36); manca solo il campione annuale, perché su un mese invernale
   l'annualizzazione sarebbe grossolana.
8. **Dimensionamento ottimale** (potenza, capacità, durata) tenendo conto della retroazione:
   è l'obiettivo dichiarato della tesi e presuppone i punti 6 e 7.

**Questioni aperte minori**: il residuo non identificato del ritardo PT15 (dichiarato come
limite noto); la riverifica dei prezzi negativi sui mesi centrali dell'anno; il DOI di Lilla et
al. e il correlatore nel frontespizio.

**Da portare al relatore insieme al perimetro temporale**: la **scelta della zona**. La misura
del 19/08 sostiene NORD come zona principale con SUD come confronto documentato — il vantaggio
di spread al Sud è 1,23× e stagionale, CSUD non si distingue dal Nord, e il vantaggio viene dal
picco serale più che dal ventre solare. Le due decisioni interagiscono: se si scegliesse di
aggiungere SUD, servirebbe una validazione dedicata su quella zona, che ha un costo.


---

## 2026-09-01 — Report per il ricevimento del 4 settembre, e un difetto nel convertitore

Il ricevimento di venerdì è il primo a cui partecipa anche la **correlatrice**, e l'ultimo
report è dell'11 agosto: da allora sono entrati l'impianto a due fasi, la firma dell'errore, la
propagazione, K\* definitiva e il confronto fra regimi, cioè il lavoro più sostanzioso della
tesi. Scritto `docs/report/2026-09-04_report.md`, che copre tre settimane invece di una.

Due scelte di impostazione, dovute al fatto che c'è un lettore nuovo:

* **la Sezione 1 richiama domanda di ricerca e impianto a due fasi** in una pagina, così che il
  documento si legga senza i report precedenti. Chi ha già il quadro salta alla Sezione 2;
* **le notazioni della tesi non compaiono**. L'erosione è descritta a parole invece che con la
  formula: in un documento che si legge una volta sola prima di una chiamata, una formula
  introdotta senza il contesto del capitolo costa più di quanto renda.

### Le cinque domande

Ordinate per urgenza, non per interesse. Le prime due bloccano il capitolo 5, che è il prossimo
lavoro.

**D1, il regime regolatorio ($K = 1$ contro $K = 2{,}3$), era già stata posta l'11 agosto e non
si era fatto in tempo a discuterla.** Allora era una questione di impostazione, ora è
bloccante: determina tutti i numeri del capitolo economico. Riproposta per prima e marcata come
tale.

**D3 è la domanda nuova, ed è la più propriamente statistica**: i residui non sono bianchi (ACF
+0,849 a lag 1) e il blocco esogeno è debolmente identificato. La si porta con l'evidenza che la
rende interessante invece che retorica — fra i tre anni l'RMSE varia di ×3,4 e il rango mediano
del 2,3%, quindi **migliorare la previsione potrebbe non spostare il risultato**. È il punto su
cui il parere della correlatrice vale di più, perché un lettore statistico potrebbe leggere come
rinuncia ciò che qui è una scelta di perimetro.

Registrate come chiuse le tre questioni risolte dall'ultimo ricevimento: perimetro temporale,
livello di erosione (10% principale, 20% in sensitività), offerte integrative GSE.

### Il difetto trovato: `K\*` arrivava in Word con la barra rovesciata

Il documento generato mostrava `4.3 La soglia K\*, definitiva sul 2024`. Nei report la soglia si
scrive `K\*` per impedire che l'asterisco apra un corsivo, ma `mgp.report` **non scioglieva gli
escape Markdown**: 34 occorrenze su tre report, tutte a vista nel `.docx` che va al relatore.

La prima correzione era sbagliata, e **il test l'ha presa**. Sostituivo la barra con un
segnaposto lasciando l'asterisco al suo posto: ma l'asterisco resta un delimitatore, e due
occorrenze sulla stessa riga venivano lette come un corsivo — `K\* scende mentre K\* sale`
diventava «K *scende mentre K* sale». Il carattere protetto va **nascosto per intero** finché la
formattazione inline non è stata riconosciuta, e la trasformazione dev'essere invertibile: si
sposta in `0xE000 + ord(c)`, dentro l'area a uso privato di Unicode, e si riporta indietro dopo.

Dentro il codice inline la barra si ripristina, perché in Markdown gli escape non agiscono in un
blocco di codice: chi scrive `` `\*` `` vuole vedere quei due caratteri.

Nuovo `tests/test_report.py`, otto casi, tutti calcolabili a mano. L'ultimo è un controllo di
regressione sui report **veri**: converte quelli presenti in `docs/report/` e fallisce se resta
una barra rovesciata fuori dal codice. Un difetto di formattazione si vede solo aprendo il file,
quindi senza quel test tornerebbe. **130 test verdi.**

Nota sul perché valesse la pena correggere il modulo invece del testo: gli escape sono sintassi
Markdown standard, e la stessa svista sarebbe tornata al report successivo.

### Stato

Rigenerati tutti e quattro i `.docx`. Resta il **capitolo 5** come unico pezzo incoerente col
resto: poggia ancora sul price maker con previsione perfetta e su gennaio 2025, mentre i
capitoli 3 e 4 hanno stabilito che il piano realistico rende il 10,4% in meno e abbassa K\* di
un quarto-un terzo. Il vincolo dichiarato nel LaTeX — «richiede il campione annuale, su un solo
mese invernale l'annualizzazione sarebbe grossolana» — **non esiste più**: con 366 giorni
l'annualizzazione è esatta. `economia.py` è testato ma non è mai stato chiamato da uno script di
pipeline, solo dal debug 08.


---

## 2026-09-01 — Le figure dentro il report, e una didascalia che il test ha salvato

Il `.docx` per il relatore citava le figure per nome ma non le conteneva: andavano mostrate a
schermo durante la chiamata. Aggiunto il supporto immagini a `mgp.report`, con la sintassi
Markdown standard `![didascalia](file.png)` su riga propria.

Quattro scelte di comportamento, tutte con una ragione:

* **il nome nudo basta**: si scrive `![...](15_errore_orario.png)` e il file si cerca prima
  accanto al report, poi dalla radice del progetto, infine in `output/figure/`. Senza l'ultimo
  passaggio servirebbe `../../output/figure/...`, che renderebbe illeggibile il sorgente
  Markdown — che è versionato e si rilegge;
* **un riferimento a `.pdf` ricade sul `.png` di pari nome**. Word non incorpora PDF e gli
  script del progetto salvano sempre entrambi i formati: senza la ricaduta, scrivere `.pdf` per
  distrazione darebbe una figura mancante senza motivo apparente;
* **l'immagine si riduce alla colonna ma non si ingrandisce mai**. Scalare in su una figura
  piccola la sfoca, e nessuna figura di questo progetto ha bisogno di essere ingrandita.
  L'altezza si scala a mano insieme alla larghezza: fissare la sola larghezza deformerebbe;
* **una figura mancante lascia un segnaposto rosso nel documento** e stampa un avviso, invece
  di interrompere la conversione o di essere ignorata. Il documento va al relatore: l'assenza
  deve vedersi sia quando si genera sia quando si legge. Interrompere sarebbe peggio, perché
  lascerebbe senza report a poche ore dal ricevimento.

### Il test di regressione ha ripreso un difetto introdotto adesso

`test_nessuna_barra_rovesciata_residua_nei_report_veri`, scritto stamattina per il difetto
degli escape, è fallito **su codice nuovo**: nella didascalia della curva di erosione avevo
scritto `K\*` e arrivava in Word con la barra, perché `_immagine` scriveva la didascalia con un
`add_run` diretto invece di passarla dal riconoscimento inline.

Correzione giusta e non aggiramento: la didascalia ora passa da `_aggiungi_testo` come ogni
altro testo, e la formattazione (corsivo, 9 punti, grigio) si applica ai run risultanti. Così
una didascalia può contenere anche grassetto o un nome di file fra apici inversi.

Vale la pena registrarlo perché è il caso in cui un test di regressione **paga entro la stessa
giornata**: era stato scritto per un difetto e ne ha preso un altro, in una funzione che allora
non esisteva.

### Verifiche

Otto casi nuovi su immagini, tutti su PNG generati al volo di dimensioni note: riduzione alla
colonna con rapporto conservato (2:1 in partenza, 2:1 all'arrivo), nessun ingrandimento,
didascalia, escape nella didascalia, ricaduta PDF→PNG, segnaposto per la figura mancante,
ricerca in `output/figure/`, e l'immagine che interrompe il paragrafo precedente anche senza
riga vuota davanti. **138 test verdi.**

`pillow` aggiunto a `requirements.txt`: arriva già come dipendenza di `python-docx`, ma i test
la importano direttamente e affidarsi alla transitività è fragile.

Report rigenerato: cinque figure incorporate, tutte a 6,00 pollici di larghezza — errore per
ora del giorno, forma della distribuzione, errore contro spread, curva di erosione nelle due
varianti, confronto fra regimi. 817 KB.


---

## 2026-09-03 — L'orizzonte giornaliero: una citazione che diceva il contrario, e la decisione mancante

Lo studente ha caricato in `scientific literature/` i PDF della letteratura, fra cui
Alonso-Perez e Arcos-Vargas — la fonte dei parametri tecnici (D-32). Prima verifica diretta
sulla fonte invece che sulla memoria, e ha prodotto due correzioni.

### La citazione sull'orizzonte usava la riga sbagliata della tabella

Il capitolo 3 scriveva: «il costo di questa scelta è quantificato dalla fonte: un orizzonte di
tre giorni cattura oltre il 99% del profitto ottenibile con cinque». **Il numero esiste** — la
fonte dice 99,5% — ma «questa scelta» è l'orizzonte di **un giorno**, e la stessa Tabella 2
quantifica anche quello:

| Orizzonte | 2.000 MWh | 8.000 | 14.000 | 20.000 |
|---|---|---|---|---|
| **1 giorno** | **82,8%** | **92,4%** | **92,1%** | **92,3%** |
| 3 giorni | 99,3% | 99,8% | 99,9% | 99,5% |
| 5 giorni | 100% | 100% | 100% | 100% |

Il troncamento costa fra il **7,6% e il 17,2%** del reddito netto, non meno dell'1%. E gli
autori scrivono testualmente che «daily optimization performs poorly», richiamando
Dufo-López e Bernal-Agustín (2015) per cui i modelli a ciclo giornaliero **sottostimano
sistematicamente** i ricavi.

La citazione sosteneva quindi l'opposto di ciò che la fonte misura. Il diario dell'11 agosto
era più prudente («resta un'estrapolazione»): l'irrigidimento è avvenuto nel passaggio al
LaTeX, dove «sostiene» è diventato «è quantificato».

**Lezione di metodo, la seconda in due settimane sullo stesso tema**: un numero letto una
volta e trascritto senza l'artefatto a fianco non è verificabile. Finché il PDF non era nel
progetto, né io né lo studente potevamo ricontrollarlo — ed è esattamente lo stato in cui una
citazione sbagliata sopravvive fino alla discussione.

### Il paragrafo riscritto

Riporta i numeri veri e sposta la difesa dove regge davvero, cioè su tre ragioni che il
confronto sui ricavi non cattura: l'orizzonte giornaliero è l'**unità di decisione effettiva**
del MGP (le offerte del giorno D si presentano tutte entro mezzogiorno di D−1); il ciclo chiuso
rende i profitti **omogenei e sommabili**, quindi ricampionabili per l'inferenza su K\*;
l'orizzonte coincide con quello della **previsione a D−1** (D-37), e allungarlo a tre giorni
richiederebbe una previsione a 72 passi, cambiando l'oggetto statistico del lavoro e non solo
il suo costo di calcolo.

Aggiunta la distinzione su **dove** il limite agisce: sul livello del profitto per intero, e
quindi sul capitolo 5 in senso **prudenziale** (il progetto rende più di quanto il modello
dichiari); sull'erosione di secondo ordine, per la stessa ragione algebrica della
Sezione 3.1.3 — il piano fisico è identico a numeratore e denominatore, quindi un troncamento
che cambia *quale* piano si costruisce lo cambia in entrambi i termini.

### D-41 · la decisione che non era mai stata registrata

Cercando l'ID da citare si è scoperto che **non esisteva**. D-22 riguarda la previsione
perfetta ed è superata da D-37; fra le quaranta decisioni nessuna copriva l'orizzonte. Era
l'assunzione più strutturale del modello — orizzonte, stato iniziale nullo e ciclo chiuso,
tre vincoli che stanno insieme — e viveva solo nel codice e in un paragrafo del capitolo 3.

Registrata come **D-41**, con il costo misurato dentro la voce. Aggiornato anche il commento
di `config.PARAMETRI_BESS["orizzonte_giorni"]`, che ripeteva la citazione sbagliata.

### Altro emerso dalla stessa verifica, non ancora sistemato

* **Il rendimento del 92% non è qualificato AC o DC nella fonte.** Il modello richiede per
  costruzione l'AC-AC, perché $c_t$ e $s_t$ sono le quantità valorizzate al prezzo di mercato
  e inserite nelle curve d'asta. La fonte dice solo «round-trip». Da dichiarare come limite.
  La sua sensitività quantifica la posta: da 90% a 80% il reddito netto cala del **17,7%**.
* **Il costo variabile della fonte è 12,3 €/MWh**, non 12,0 come in `config`.
* **La voce bibliografica è del preprint** (SSRN 2025); il PDF è la versione pubblicata,
  *Energy Reports* 15 (2026) 108991. Fuori perimetro: segnalato allo studente.
* La fonte àncora le proprie equazioni a **Sioshansi et al. (2022)**, «minimum set of
  desirable storage model characteristics»: è il riferimento giusto per la formulazione
  di §3.2, oggi priva di citazione.

### Manutenzione

`scientific literature/` aggiunta al `.gitignore`: 101 MB di PDF sotto copyright, e il
repository è pubblico. Prima della riorganizzazione fatta dallo studente, **13 PDF su 36
avevano percorsi oltre i 260 caratteri** di `MAX_PATH` ed erano illeggibili da Python (la
cartella e il file ripetevano lo stesso titolo lungo). Dopo l'appiattimento: 22 PDF, **0
problematici**.
