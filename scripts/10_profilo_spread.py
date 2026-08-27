"""
Profilo orario del prezzo di equilibrio nelle giornate a spread infragiornaliero ampio.

A che serve
-----------
Illustrare l'opportunita' di arbitraggio nella sua forma piu' diretta: la distanza fra il
prezzo minimo e quello massimo della stessa giornata e' il ricavo lordo per MWh ciclato di
un accumulo perfettamente informato e di potenza trascurabile. E' il limite superiore
dell'arbitraggio price taker, non il profitto: quest'ultimo sconta rendimento di ciclo,
costo variabile e vincolo di potenza, e si ottiene da `batteria.profilo_ottimo`.

Due modi d'uso
--------------
`--cerca` percorre le giornate gia' in cache nel regime orario, ricostruisce il prezzo con
la configurazione adottata e ne classifica lo spread: e' il passaggio che *motiva* la scelta
delle giornate da disegnare, e va rifatto se il bacino cambia.

Senza `--cerca` disegna le giornate indicate da `--giorni`.

Perimetro
---------
Configurazione adottata, identica a quella dello script 03 di validazione: perimetro NORD
piu' le zone virtuali di frontiera presenti (D-10), offerte in gara (D-06), tutte le
granularita' (D-13), quantita' rettificata (D-20), blocco di scambio netto simmetrico
(D-16), clearing iterativo consapevole dei blocchi (D-18, D-19).

Solo regime ORARIO: le giornate a quarto d'ora hanno 96 periodi, che rendono illeggibili
marcatori ed etichette e sono comunque ricostruite con accuratezza molto minore.

Esempi
------
    .\\.venv\\Scripts\\python.exe scripts\\10_profilo_spread.py --cerca
    .\\.venv\\Scripts\\python.exe scripts\\10_profilo_spread.py --giorni 20250120,20250516
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp import config, curve, grafici, io_gme  # noqa: E402

#: Le due giornate scelte per la tesi: una invernale e una primaverile.
#: La prima e' lo spread massimo del bacino; la seconda e' il massimo primaverile ed e'
#: li' perche' i due regimi di arbitraggio sono strutturalmente diversi (notte -> mattina
#: contro mezzogiorno -> sera), non per ragioni estetiche.
GIORNI_TESI: tuple[str, ...] = ("20250120", "20250516")


def ricostruisci(data: str) -> pd.DataFrame:
    """
    Prezzo di equilibrio orario di una giornata, con la configurazione adottata.

    Returns
    -------
    pd.DataFrame
        Colonne `ora` (1-24), `prezzo` (ricostruito) e `prezzo_ufficiale` (benchmark
        `AWARDED_PRICE_NO`, gia' dentro i file GME).

    Raises
    ------
    ValueError
        Se la giornata non e' in regime orario.
    """
    granularita = config.granularita_prevalente(data)
    if granularita != "PT60":
        raise ValueError(
            f"{data}: granularita' prevalente {granularita}, questo script vuole PT60. "
            "Il regime a quarto d'ora ha 96 periodi e una ricostruzione meno accurata."
        )

    df = io_gme.carica_giorno(data=data, zona=None)
    zone_presenti = set(df["ZONE_CD"].dropna().unique())
    perimetro = ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti]

    ric = curve.clearing_giorno_con_blocchi(
        df, granularita=granularita, zone=perimetro,
        includi_altra_granularita=True, con_import=True,
    )
    uff = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)

    giorno = (
        ric.merge(uff[["PERIOD", "prezzo_ufficiale"]], on="PERIOD", how="left")
           .sort_values("PERIOD")
           .rename(columns={"PERIOD": "ora"})
    )
    return giorno[["ora", "prezzo", "prezzo_ufficiale"]].reset_index(drop=True)


def giorni_in_cache_orari() -> list[str]:
    """Giornate gia' parsate in cache Parquet che ricadono nel regime orario."""
    date = {p.name.split("_")[1] for p in config.INTERIM_DIR.glob("offerte_*.parquet")}
    return sorted(d for d in date if config.granularita_prevalente(d) == "PT60")


def cerca(out) -> pd.DataFrame:
    """
    Classifica per spread le giornate orarie in cache.

    Il bacino e' quello che c'e': **non e' un campione casuale**. Se un mese e' presente
    per intero e gli altri solo per una settimana, il massimo tendera' a cadere nel mese
    piu' rappresentato per semplice numero di occasioni. La composizione del bacino va
    quindi letta insieme alla classifica, ed e' per questo che viene stampata.
    """
    giorni = giorni_in_cache_orari()
    out(f"Bacino: {len(giorni)} giornate in regime orario, gia' in cache.")
    out("")

    righe = []
    inizio = time.time()
    for i, data in enumerate(giorni, start=1):
        g = ricostruisci(data)
        p = g["prezzo"].to_numpy(dtype=float)
        u = g["prezzo_ufficiale"].to_numpy(dtype=float)
        righe.append({
            "data": data,
            "mese": int(data[4:6]),
            "stagione": curve.STAGIONI[int(data[4:6])],
            "n_senza_equilibrio": int((~np.isfinite(p)).sum()),
            "minimo": np.nanmin(p),
            "ora_minimo": int(g["ora"].iloc[int(np.nanargmin(p))]),
            "massimo": np.nanmax(p),
            "ora_massimo": int(g["ora"].iloc[int(np.nanargmax(p))]),
            "spread": np.nanmax(p) - np.nanmin(p),
            "spread_ufficiale": np.nanmax(u) - np.nanmin(u),
            "errore_mediano": float(np.nanmedian(np.abs(p - u))),
            "errore_massimo": float(np.nanmax(np.abs(p - u))),
        })
        if i % 10 == 0:
            print(f"  [{i:3d}/{len(giorni)}]  {data}  ({time.time() - inizio:.0f} s)",
                  flush=True)

    d = pd.DataFrame(righe)
    colonne = ["data", "stagione", "spread", "spread_ufficiale", "minimo", "ora_minimo",
               "massimo", "ora_massimo", "errore_mediano", "errore_massimo"]
    out("Prime quindici giornate per spread:")
    out(d.sort_values("spread", ascending=False).head(15)[colonne].round(2)
         .to_string(index=False))
    out("")
    out("Composizione del bacino e spread per mese (la classifica va letta insieme a questa):")
    out(d.groupby("mese")["spread"]
         .agg(giorni="size", mediana="median", massimo="max").round(2).to_string())
    out("")
    out(f"Spread mediano complessivo: {d['spread'].median():.2f} EUR/MWh")
    out(f"Aste senza equilibrio in tutto il bacino: {int(d['n_senza_equilibrio'].sum())}")
    return d


def disegna(giorni: list[str], out) -> None:
    """Ricostruisce le giornate indicate e ne salva le figure, singole e appaiate."""
    profili: dict[str, pd.DataFrame] = {}
    for data in giorni:
        g = ricostruisci(data)
        profili[data] = g

        figura = grafici.figura_profilo_prezzi(g, data)
        png = grafici.salva(figura, f"10_profilo_{data}")

        p = g["prezzo"].to_numpy(dtype=float)
        u = g["prezzo_ufficiale"].to_numpy(dtype=float)
        scarto = np.abs(p - u)
        out(f"{grafici.data_estesa(data)}  ({data})")
        out(f"  minimo  {np.nanmin(p):7.2f} EUR/MWh  ore {int(g['ora'].iloc[int(np.nanargmin(p))]):2d}")
        out(f"  massimo {np.nanmax(p):7.2f} EUR/MWh  ore {int(g['ora'].iloc[int(np.nanargmax(p))]):2d}")
        out(f"  spread  {np.nanmax(p) - np.nanmin(p):7.2f} EUR/MWh "
            f"(ufficiale {np.nanmax(u) - np.nanmin(u):.2f})")
        out(f"  scarto dal prezzo ufficiale: mediano {np.nanmedian(scarto):.2f}, "
            f"massimo {np.nanmax(scarto):.2f} EUR/MWh")
        out(f"  figura: {png} (e .pdf)")
        out("")

    if len(profili) > 1:
        figura = grafici.figura_profili_confronto(profili)
        nome = "10_profilo_confronto_" + "_".join(giorni)
        out(f"Confronto appaiato, scala verticale comune: {grafici.salva(figura, nome)} (e .pdf)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--giorni", default=",".join(GIORNI_TESI),
                    help="date AAAAMMGG separate da virgola")
    ap.add_argument("--cerca", action="store_true",
                    help="classifica per spread le giornate orarie in cache")
    args = ap.parse_args()

    config.assicura_cartelle()
    righe: list[str] = []

    def out(testo: str = "") -> None:
        print(testo, flush=True)
        righe.append(testo)

    out("=" * 92)
    out("PROFILO ORARIO DEL PREZZO DI EQUILIBRIO — zona NORD, regime orario")
    out("=" * 92)
    out("Configurazione adottata: perimetro NORD + frontiere confinanti (D-10), offerte in")
    out("gara (D-06), tutte le granularita' (D-13), quantita' rettificata (D-20), scambio")
    out("netto simmetrico (D-16), clearing iterativo consapevole dei blocchi (D-18, D-19).")
    out("")

    if args.cerca:
        d = cerca(out)
        d.to_csv(config.TABLE_DIR / "10_spread_giornaliero_NORD.csv", index=False)
        out("")
        out(f"Tabella completa: {config.TABLE_DIR / '10_spread_giornaliero_NORD.csv'}")
    else:
        disegna([g.strip() for g in args.giorni.split(",") if g.strip()], out)

    destinazione = config.TABLE_DIR / ("10_spread_ricerca.txt" if args.cerca
                                       else "10_profilo_spread.txt")
    destinazione.write_text("\n".join(righe), encoding="utf-8")
    print(f"\nReport salvato in {destinazione}")


if __name__ == "__main__":
    main()
