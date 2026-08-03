# Tesi — Impatto delle batterie di accumulo sul MGP (zona NORD)

Pipeline di analisi in Python per la tesi magistrale in Statistica (mercati finanziari).
Si ricostruiscono le curve di domanda e offerta del Mercato del Giorno Prima italiano a
partire dalle offerte pubbliche di GME e si simula l'effetto dell'inserimento di capacità
di accumulo che fa arbitraggio fra ore a prezzo basso e ore di picco.

## Avvio rapido

```powershell
# 1. dipendenze (venv Python 3.10 già presente in .venv/)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. caricamento e validazione del giorno pilota (31/03/2026, zona NORD)
.\.venv\Scripts\python.exe scripts\01_carica_ed_esplora.py

# 3. documento Word del report settimanale per il relatore
.\.venv\Scripts\python.exe scripts\90_genera_report.py
```

La prima esecuzione riparsa 574 MB di XML (qualche minuto) e crea una cache Parquet in
`data/interim/`; le successive partono dalla cache.

## Documentazione

| File | Contenuto |
|---|---|
| [docs/DIARIO.md](docs/DIARIO.md) | diario metodologico datato: cosa, perché, assunzioni, validazioni |
| [docs/decisioni.md](docs/decisioni.md) | registro sintetico delle decisioni metodologiche (D-01…D-09) |
| [docs/glossario_dati.md](docs/glossario_dati.md) | dizionario dei campi e dei codici dei file GME |
| [docs/report/](docs/report/) | sorgenti dei report settimanali per il relatore (il `.docx` si genera in `output/report/`) |

## Struttura

```
src/mgp/      moduli riutilizzabili (config, lettura dati, curve, batteria)
scripts/      elaborazioni eseguibili, numerate nell'ordine della pipeline
notebooks/    esplorazioni
data/         cache e dataset derivati (non versionati)
output/       figure e tabelle (non versionate)
docs/         documentazione metodologica
tests/        test delle funzioni di calcolo
```

I dati grezzi GME (~6 GB) non sono versionati e restano fuori dal progetto: i percorsi sono
in [src/mgp/config.py](src/mgp/config.py).
