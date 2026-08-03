"""
Pacchetto `mgp` — pipeline di analisi del Mercato del Giorno Prima (MGP) italiano
per la tesi sull'impatto delle batterie di accumulo in zona NORD.

Moduli
------
config   : path dei dati e costanti di progetto (unico punto da modificare se i dati si spostano)
io_gme   : lettura in streaming dei file XML "OffertePubbliche" di GME e normalizzazione
curve    : (passo successivo) curve aggregate di domanda/offerta e prezzo di equilibrio
batteria : (passo successivo) simulazione dell'accumulo come domanda/offerta addizionale
grafici  : (passo successivo) grafici delle curve e dei risultati
"""

__version__ = "0.1.0"
