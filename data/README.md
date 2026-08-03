# Cartella dati

I **dati grezzi non sono qui** e non sono versionati: pesano circa 6 GB e risiedono già
nella cartella del progetto sincronizzata su OneDrive. Copiarli o spostarli avrebbe solo
duplicato peso e tempi di sincronizzazione, quindi restano dove sono e vengono raggiunti
tramite i percorsi definiti in [../src/mgp/config.py](../src/mgp/config.py).

| Cosa | Dove |
|---|---|
| Giorno pilota (31/03/2026), 574 MB, 568.185 offerte | `20260331MGPOffertePubbliche.xml` nella radice del progetto |
| Archivio storico 2015-2026, 5.251 file `.zip` (uno al giorno) | `MGP_OffertePubbliche/MGP_OffertePubbliche/` |
| Legenda dei dataset GME | `MGP_OffertePubbliche/MGP_OffertePubbliche/Legend.txt` |

Se i dati vengono spostati, l'unico file da modificare è `src/mgp/config.py`.

## Sottocartelle

* `interim/` — cache Parquet delle letture (`offerte_<data>_<zona>_<granularità>.parquet`).
  Rigenerabile: cancellarla è sicuro, la prima esecuzione successiva la ricostruisce.
* `processed/` — dataset derivati pronti per l'analisi, per esempio
  `prezzi_ufficiali_NORD_20260331.csv` (prezzo zonale ufficiale per periodo, estratto da
  `AWARDED_PRICE_NO`: vedi decisione D-07).

Entrambe sono escluse dal versionamento perché interamente ricostruibili dagli script.
