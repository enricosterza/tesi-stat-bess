# Primo tentativo di lettura, conservato come traccia del punto di partenza.
#
# SUPERATO da `mgp.io_gme` (vedi docs/DIARIO.md, D-08): `pandas.read_xml` costruisce in
# memoria l'intero albero XML, e su un file da 574 MB servono diversi GB di RAM e un
# riparsing completo a ogni esecuzione. Il modulo `mgp.io_gme` legge lo stesso file in
# streaming con `lxml.etree.iterparse`, filtra la zona durante il parsing e mette in cache
# il risultato in Parquet.
#
# Uso corrente:
#     from mgp import io_gme
#     df = io_gme.carica_giorno(data="20260331", zona="NORD")

import pandas as pd

# --- 1. Caricamento del file XML di un singolo giorno ---
file_path = "20260331MGPOffertePubbliche.xml"

df = pd.read_xml(file_path)

print(df.shape)
print(df.columns.tolist())

#%%
