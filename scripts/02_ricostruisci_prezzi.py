"""
Passo 2 della pipeline: ricostruzione del prezzo di equilibrio e confronto con l'ufficiale.

Che cosa fa
-----------
Esegue il clearing su tutti i periodi di un giorno e confronta il prezzo ricostruito con
quello ufficiale letto da `AWARDED_PRICE_NO` (D-07). Lo fa per piu' **varianti** della
pipeline, che corrispondono alle decisioni ancora da validare:

* **perimetro zonale** (D-01 vs D-10): NORD isolata, NORD piu' le frontiere confinanti,
  NORD piu' tutte le zone virtuali presenti;
* **stati ammessi** (D-06): quali `STATUS_CD` compongono la curva d'asta;
* **granularita'** (D-13): solo la granularita' nativa del giorno, oppure anche le offerte
  presentate all'altra granularita', riscalate.

Per ciascuna variante riporta la frequenza di match a diverse tolleranze, l'errore assoluto
mediano e il bias con segno: e' il criterio di bontà stabilito in D-09.

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\02_ricostruisci_prezzi.py
    .\\.venv\\Scripts\\python.exe scripts\\02_ricostruisci_prezzi.py --data 20250115

La granularita' delle aste viene dedotta dalla data (D-12): oraria fino al 30/09/2025,
a quarto d'ora dal 01/10/2025.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from mgp import config, curve, io_gme  # noqa: E402

#: Insiemi di stati da confrontare. Il primo e' quello adottato (D-06).
VARIANTI_STATI: dict[str, list[str]] = {
    "ACC+REJ+PREJ (adottato)": ["ACC", "REJ", "PREJ"],
    "ACC+REJ": ["ACC", "REJ"],
    "solo ACC": ["ACC"],
    "ACC+REJ+PREJ+REP": ["ACC", "REJ", "PREJ", "REP"],
    "tutti gli stati": ["ACC", "REJ", "PREJ", "REP", "REV", "INC"],
}

#: Zone virtuali presenti nei dati che NON confinano con NORD e che quindi non vanno
#: incluse nel perimetro: Corsica (verso CNOR/SARD) e Malta (verso SICI).
ZONE_VIRTUALI_ALTRE = ["CORS", "COAC", "MALT", "MONT"]


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=config.DATA_PILOTA)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    config.assicura_cartelle()
    pd.set_option("display.width", 130)

    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo)
        buffer.write(testo + "\n")

    granularita = config.granularita_prevalente(args.data)

    out(_sezione(f"RICOSTRUZIONE DEI PREZZI — {args.data}, granularita' {granularita}"))
    out("Caricamento di tutte le zone (serve per i perimetri allargati)...")
    df = io_gme.carica_giorno(data=args.data, zona=None, usa_cache=not args.no_cache)
    out(f"Righe caricate: {len(df):,}".replace(",", "."))

    ufficiale = io_gme.prezzi_ufficiali(
        df[df["ZONE_CD"] == config.ZONA_DEFAULT], granularita=granularita
    )
    out(f"Prezzi ufficiali NORD: {len(ufficiale)} periodi, "
        f"da {ufficiale['prezzo_ufficiale'].min():.2f} a {ufficiale['prezzo_ufficiale'].max():.2f} €/MWh")

    zone_presenti = set(df["ZONE_CD"].dropna().unique())
    perimetri: dict[str, list[str]] = {
        "NORD isolata (D-01)": ["NORD"],
        "NORD + frontiere confinanti (D-10)": ["NORD"] + [
            z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti
        ],
        "NORD + tutte le zone virtuali": ["NORD"] + [
            z for z in config.ZONE_FRONTIERA_NORD + ZONE_VIRTUALI_ALTRE if z in zone_presenti
        ],
    }

    # ----------------------------------------------------------------------------------
    # A. Perimetro zonale, a parita' di stati adottati
    # ----------------------------------------------------------------------------------
    out(_sezione("A. EFFETTO DEL PERIMETRO ZONALE (stati: ACC+REJ+PREJ)"))
    risultati = []
    serie: dict[str, pd.DataFrame] = {}
    for nome, zone in perimetri.items():
        ric = curve.clearing_giorno(df, granularita=granularita, zone=zone)
        serie[nome] = ric
        esito = curve.confronta_con_ufficiale(ric, ufficiale)
        esito["variante"] = nome
        esito["zone"] = " ".join(zone)
        risultati.append(esito)
    tab_perimetro = pd.DataFrame(risultati).set_index("variante")
    out(tab_perimetro[["n_ricostruiti", "errore_mediano", "bias_mediano",
                       "match_0.01", "match_1.0", "match_5.0"]].to_string())

    # ----------------------------------------------------------------------------------
    # B. Stati ammessi, a parita' di perimetro adottato
    # ----------------------------------------------------------------------------------
    perimetro_adottato = perimetri["NORD + frontiere confinanti (D-10)"]
    out(_sezione(f"B. EFFETTO DEGLI STATI AMMESSI (perimetro: {' '.join(perimetro_adottato)})"))
    risultati = []
    for nome, stati in VARIANTI_STATI.items():
        ric = curve.clearing_giorno(df, granularita=granularita,
                                    zone=perimetro_adottato, stati=stati)
        esito = curve.confronta_con_ufficiale(ric, ufficiale)
        esito["variante"] = nome
        risultati.append(esito)
    tab_stati = pd.DataFrame(risultati).set_index("variante")
    out(tab_stati[["n_ricostruiti", "errore_mediano", "bias_mediano",
                   "match_0.01", "match_1.0", "match_5.0"]].to_string())

    # ----------------------------------------------------------------------------------
    # C. Granularita' minoritaria (D-13)
    # ----------------------------------------------------------------------------------
    out(_sezione("C. EFFETTO DELLE OFFERTE ALL'ALTRA GRANULARITA' (D-13)"))
    out("Le quantita' NON vengono riscalate: `QUANTITY_NO` e' una potenza (MW), quindi")
    out("un'offerta oraria di X MW vale X MW in ciascuno dei quarti d'ora dell'ora.")
    risultati = []
    for nome, includi in [("solo granularita' nativa", False),
                          ("nativa + altra granularita'", True)]:
        ric = curve.clearing_giorno(df, granularita=granularita, zone=perimetro_adottato,
                                    includi_altra_granularita=includi)
        esito = curve.confronta_con_ufficiale(ric, ufficiale)
        esito["variante"] = nome
        risultati.append(esito)
    tab_gran = pd.DataFrame(risultati).set_index("variante")
    out(tab_gran[["n_ricostruiti", "errore_mediano", "bias_mediano",
                  "match_0.01", "match_1.0", "match_5.0"]].to_string())

    # ----------------------------------------------------------------------------------
    # D. Import netto esogeno: il pezzo mancante della curva di offerta
    # ----------------------------------------------------------------------------------
    out(_sezione("D. EFFETTO DEL BLOCCO DI IMPORT NETTO"))
    out("Le offerte di una zona non contengono l'energia che vi arriva dalle altre zone o")
    out("dall'estero. Il blocco di import netto la reintroduce come offerta price taker,")
    out("calibrata sulle quantita' assegnate osservate (limite: e' una grandezza calibrata).")
    risultati = []
    for nome, zone in perimetri.items():
        ric = curve.clearing_giorno(df, granularita=granularita, zone=zone,
                                    includi_altra_granularita=True, con_import=True)
        serie[f"{nome} + import"] = ric
        esito = curve.confronta_con_ufficiale(ric, ufficiale)
        esito["variante"] = f"{nome} + import"
        esito["import_medio_MW"] = round(float(ric["import_netto"].mean()), 0)
        risultati.append(esito)
    tab_import = pd.DataFrame(risultati).set_index("variante")
    out(tab_import[["import_medio_MW", "errore_mediano", "bias_mediano",
                    "match_0.01", "match_1.0", "match_5.0"]].to_string())

    # ----------------------------------------------------------------------------------
    # E. Dettaglio della variante migliore
    # ----------------------------------------------------------------------------------
    tutte = pd.concat([tab_perimetro, tab_import])
    migliore = tutte["errore_mediano"].idxmin()
    out(_sezione(f"E. DETTAGLIO DELLA VARIANTE MIGLIORE: {migliore}"))
    ric = serie[migliore].merge(ufficiale[["PERIOD", "prezzo_ufficiale"]], on="PERIOD")
    ric["scarto"] = ric["prezzo"] - ric["prezzo_ufficiale"]
    out("\nPeriodi senza intersezione delle curve, per motivo:")
    out(ric["motivo"].value_counts().to_string())
    out("\nDistribuzione dello scarto (ricostruito - ufficiale, €/MWh):")
    out(ric["scarto"].describe().to_string())
    out("\nPrimi e ultimi periodi:")
    colonne = ["PERIOD", "prezzo", "prezzo_ufficiale", "scarto", "quantita", "n_offerte"]
    out(pd.concat([ric[colonne].head(5), ric[colonne].tail(5)]).to_string(index=False))

    # ----------------------------------------------------------------------------------
    # Salvataggi
    # ----------------------------------------------------------------------------------
    f_serie = config.PROCESSED_DIR / f"prezzi_ricostruiti_{args.data}_{granularita}.csv"
    f_tab = config.TABLE_DIR / f"02_varianti_{args.data}.csv"
    f_report = config.TABLE_DIR / f"02_riepilogo_{args.data}.txt"
    ric.to_csv(f_serie, index=False)
    pd.concat([tab_perimetro.assign(blocco="perimetro"),
               tab_stati.assign(blocco="stati"),
               tab_gran.assign(blocco="granularita"),
               tab_import.assign(blocco="import")]).to_csv(f_tab)

    out(_sezione("FILE PRODOTTI"))
    for f in (f_serie, f_tab, f_report):
        out(f"  {f}")
    f_report.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
