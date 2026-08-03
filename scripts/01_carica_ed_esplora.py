"""
Passo 1 della pipeline: caricamento e validazione del file di offerte MGP del giorno pilota.

Obiettivo
---------
Prima di ricostruire curve e prezzi bisogna essere certi di aver letto il dato per intero
e di averlo interpretato correttamente. Questo script esegue e documenta i controlli:

1. carica il file del 31/03/2026 filtrando la zona NORD (primo livello di filtro);
2. stampa i valori unici dei campi categoriali con i relativi conteggi;
3. verifica la conversione numerica (dtype, NaN, range dei prezzi e delle quantita');
4. riepiloga la composizione del dato: periodi, righe per periodo, MW per lato del mercato,
   quanto pesano le granularita' diverse da PT15 che verranno escluse;
5. estrae il prezzo zonale ufficiale per periodo (benchmark per validare, al passo
   successivo, il prezzo di equilibrio ricostruito).

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\01_carica_ed_esplora.py

La prima esecuzione riparsa i 574 MB di XML (alcuni minuti) e scrive una cache Parquet in
`data/interim/`; le successive rileggono la cache in pochi secondi. Per forzare il
riparsing: `--no-cache`.

Output su file
--------------
* `output/tabelle/01_riepilogo_<data>_<zona>.txt`      : il report completo;
* `output/tabelle/01_per_periodo_<data>_<zona>.csv`    : righe e MW per periodo;
* `data/processed/prezzi_ufficiali_<zona>_<data>.csv`  : prezzo zonale ufficiale per periodo.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# Il pacchetto `mgp` vive in <progetto>/src: lo rendiamo importabile senza installazione.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from mgp import config, io_gme  # noqa: E402


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=config.DATA_PILOTA, help="data YYYYMMDD (default: giorno pilota)")
    parser.add_argument("--zona", default=config.ZONA_DEFAULT, help="zona di mercato (default: NORD)")
    parser.add_argument("--no-cache", action="store_true", help="forza il riparsing dell'XML")
    args = parser.parse_args()

    config.assicura_cartelle()
    pd.set_option("display.width", 120)
    pd.set_option("display.max_rows", 120)

    # Il report viene scritto a video e su file: le tabelle finiscono nel diario e in tesi.
    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo)
        buffer.write(testo + "\n")

    # ----------------------------------------------------------------------------------
    # 1. Caricamento (filtro di primo livello: la zona)
    # ----------------------------------------------------------------------------------
    percorso = config.path_giorno(args.data)
    out(_sezione("1. CARICAMENTO"))
    out(f"File sorgente     : {percorso}")
    out(f"Dimensione        : {percorso.stat().st_size / 1e6:.1f} MB")
    out(f"Zona richiesta    : {args.zona}")
    out("Lettura in corso (streaming lxml; la prima volta richiede qualche minuto)...")

    df = io_gme.carica_giorno(data=args.data, zona=args.zona, usa_cache=not args.no_cache)
    out(f"Righe caricate    : {len(df):,}".replace(",", "."))
    out(f"Colonne           : {list(df.columns)}")

    # ----------------------------------------------------------------------------------
    # 2. Campi categoriali: valori unici e conteggi
    # ----------------------------------------------------------------------------------
    out(_sezione("2. VALORI UNICI DEI CAMPI CATEGORIALI"))
    for col in ["PURPOSE_CD", "STATUS_CD", "GRANULARITY", "OFFER_TYPE", "TYPE_CD",
                "ZONE_CD", "PARTIAL_QTY_ACCEPTED_IN", "BILATERAL_IN", "MARKET_CD"]:
        if col not in df.columns:
            continue
        conteggi = df[col].fillna("(vuoto)").replace("", "(vuoto)").value_counts()
        out(f"\n{col} ({conteggi.size} valori distinti):")
        out(conteggi.to_string())

    out("\nLettura dei codici:")
    out(f"  {config.PURPOSE_ACQUISTO} = offerta di acquisto -> curva di DOMANDA")
    out(f"  {config.PURPOSE_VENDITA} = offerta di vendita  -> curva di OFFERTA")
    out("  STATUS_CD: ACC accettata, REJ respinta, REP sostituita da un'offerta successiva,")
    out("             REV revocata, INC incongruente, PREJ pre-respinta.")
    out("             Quali status entrino nelle curve e' una decisione aperta (docs/decisioni.md, D-06).")

    # ----------------------------------------------------------------------------------
    # 3. Conversione numerica
    # ----------------------------------------------------------------------------------
    out(_sezione("3. CONVERSIONE DEI CAMPI NUMERICI"))
    out("Nell'XML il separatore decimale e' il PUNTO (la virgola compare solo negli export")
    out("Excel/CSV di GME); la conversione e' comunque difensiva su entrambi i separatori.")
    riep = io_gme.riepilogo(df)
    out("\n" + riep["numeriche"][["dtype", "count", "n_NaN", "min", "mean", "max"]].to_string())

    # ----------------------------------------------------------------------------------
    # 4. Composizione del dato
    # ----------------------------------------------------------------------------------
    out(_sezione("4. COMPOSIZIONE DEL DATO"))
    out("\nRighe per granularita' e finalita' (BID = acquisto, OFF = vendita):")
    out(riep["per_granularita"].to_string())
    out("\nAttenzione: PERIOD va sempre letto insieme a GRANULARITY.")
    for g, n in config.GRANULARITA_PERIODI.items():
        presenti = df.loc[df["GRANULARITY"] == g, "PERIOD"]
        if len(presenti):
            out(f"  {g}: PERIOD da {presenti.min()} a {presenti.max()} "
                f"({presenti.nunique()} periodi distinti, attesi {n})")

    out("\nRighe per status e finalita':")
    out(riep["per_status"].to_string())

    out("\nIndicatori di qualita' e di impatto delle semplificazioni:")
    out(riep["qualita"].to_string())

    per_periodo = riep["per_periodo"]
    out(f"\nPeriodi PT15 con almeno un'offerta: {len(per_periodo)} (attesi 96)")
    out("\nPrime e ultime righe della tabella per periodo (PT15):")
    out(pd.concat([per_periodo.head(3), per_periodo.tail(3)]).to_string())
    out("\nStatistiche sulle righe per periodo:")
    out(per_periodo[["righe", "righe_BID", "righe_OFF", "MW_domanda", "MW_offerta"]]
        .describe().T.to_string())

    # ----------------------------------------------------------------------------------
    # 5. Prezzo zonale ufficiale (benchmark di validazione)
    # ----------------------------------------------------------------------------------
    out(_sezione("5. PREZZO ZONALE UFFICIALE (benchmark per il clearing)"))
    prezzi = io_gme.prezzi_ufficiali(df)
    n_ambigui = int((prezzi["n_valori_distinti"] != 1).sum())
    out("Su asta a prezzo uniforme, AWARDED_PRICE_NO deve essere costante entro (zona, periodo).")
    out(f"Periodi con piu' di un valore distinto: {n_ambigui} (atteso 0)")
    out(f"Prezzo min/medio/max sui {len(prezzi)} periodi: "
        f"{prezzi['prezzo_ufficiale'].min():.2f} / "
        f"{prezzi['prezzo_ufficiale'].mean():.2f} / "
        f"{prezzi['prezzo_ufficiale'].max():.2f} €/MWh")
    out("\nControllo puntuale (valori verificati indipendentemente sul file grezzo):")
    for periodo, atteso in [(40, 177.87), (76, 180.20)]:
        riga = prezzi.loc[prezzi["PERIOD"] == periodo, "prezzo_ufficiale"]
        ottenuto = float(riga.iloc[0]) if len(riga) else float("nan")
        esito = "OK" if abs(ottenuto - atteso) < 0.005 else "DIVERGENZA"
        out(f"  periodo {periodo}: atteso {atteso:.2f} - ottenuto {ottenuto:.2f} -> {esito}")

    # ----------------------------------------------------------------------------------
    # Salvataggi
    # ----------------------------------------------------------------------------------
    f_prezzi = config.PROCESSED_DIR / f"prezzi_ufficiali_{args.zona}_{args.data}.csv"
    f_periodi = config.TABLE_DIR / f"01_per_periodo_{args.data}_{args.zona}.csv"
    f_report = config.TABLE_DIR / f"01_riepilogo_{args.data}_{args.zona}.txt"
    prezzi.to_csv(f_prezzi, index=False)
    per_periodo.to_csv(f_periodi)

    out(_sezione("FILE PRODOTTI"))
    out(f"  {f_prezzi}")
    out(f"  {f_periodi}")
    out(f"  {f_report}")
    f_report.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
