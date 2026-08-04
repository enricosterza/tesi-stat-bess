"""
Passo 3 della pipeline: validazione della ricostruzione su un mese intero.

Perche' un mese e non un giorno
-------------------------------
La validazione su singole giornate (passo 2) dice se la pipeline funziona, non se e'
affidabile: un giorno puo' essere fortunato. Su un mese si vede se l'accuratezza e'
**stabile** — nel tempo, nell'arco della giornata, e fra condizioni di mercato diverse — che
e' cio' che conta per poter usare il modello come base della simulazione della batteria.

La domanda a cui questo script risponde non e' solo "quanto sbaglia" ma "**dove** sbaglia":

* per giorno, per individuare giornate anomale;
* per ora del giorno, perche' le ore di picco sono quelle in cui la batteria scarica ed e'
  li' che l'accuratezza serve di piu';
* per **presenza di congestione**, distinguendo i periodi in cui tutte le zone italiane
  hanno lo stesso prezzo (mercato di fatto unico) da quelli in cui i prezzi divergono
  (vincoli di transito attivi). E' il test diretto del limite noto del modello zonale
  semplificato (D-10): quando la rete e' congestionata, ricostruire una zona ignorando i
  limiti di transito deve funzionare peggio.

Configurazione adottata
-----------------------
Perimetro NORD piu' le zone virtuali di frontiera confinanti (D-10), offerte in gara
`ACC`+`REJ`+`PREJ` (D-06), tutte le granularita' (D-13), blocco di import netto (D-16),
granularita' dell'asta dedotta dalla data (D-12).

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\03_valida_mese.py --mese 202501

Il primo passaggio riparsa un XML per giorno (alcuni minuti in tutto) e lascia in
`data/interim/` una cache Parquet per giornata; le esecuzioni successive sono immediate.
"""

from __future__ import annotations

import argparse
import calendar
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from mgp import config, curve, io_gme  # noqa: E402

#: Zone fisiche italiane: servono per stabilire se in un periodo il mercato e' congestionato.
ZONE_ITALIANE = ["NORD", "CNOR", "CSUD", "SUD", "CALA", "SICI", "SARD"]


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def giorni_del_mese(mese: str) -> list[str]:
    """Elenca le date 'YYYYMMDD' di un mese 'YYYYMM' per cui esiste un file di offerte."""
    anno, mm = int(mese[:4]), int(mese[4:6])
    giorni = []
    for g in range(1, calendar.monthrange(anno, mm)[1] + 1):
        data = f"{anno}{mm:02d}{g:02d}"
        try:
            config.path_giorno(data)
        except FileNotFoundError:
            continue
        giorni.append(data)
    return giorni


def congestione(df: pd.DataFrame, granularita: str) -> pd.DataFrame:
    """
    Per ogni periodo, stabilisce se le zone italiane hanno tutte lo stesso prezzo.

    Returns
    -------
    pd.DataFrame
        Colonne `PERIOD`, `n_prezzi_zonali`, `congestionato` (bool), `spread_zonale`
        (differenza fra prezzo zonale massimo e minimo, €/MWh).

    Nota
    ----
    Prezzi zonali tutti uguali implicano che nessun vincolo di transito e' attivo in modo
    vincolante: il mercato si comporta come un mercato unico. Prezzi diversi segnalano
    congestione, ed e' li' che un modello che ignora i limiti di transito e' piu' debole.
    """
    acc = df[(df["STATUS_CD"] == "ACC")
             & (df["GRANULARITY"] == granularita)
             & (df["ZONE_CD"].isin(ZONE_ITALIANE))]
    per_zona = acc.groupby(["PERIOD", "ZONE_CD"])["AWARDED_PRICE_NO"].median().unstack()
    return pd.DataFrame({
        "PERIOD": per_zona.index,
        "n_prezzi_zonali": per_zona.round(2).nunique(axis=1).to_numpy(),
        "spread_zonale": (per_zona.max(axis=1) - per_zona.min(axis=1)).to_numpy(),
    }).assign(congestionato=lambda d: d["n_prezzi_zonali"] > 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mese", default="202501", help="mese da validare, formato AAAAMM")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    config.assicura_cartelle()
    pd.set_option("display.width", 130)
    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo, flush=True)
        buffer.write(testo + "\n")

    giorni = giorni_del_mese(args.mese)
    out(_sezione(f"VALIDAZIONE SUL MESE {args.mese} — {len(giorni)} giorni"))
    out("Configurazione: perimetro NORD + frontiere confinanti (D-10), offerte in gara")
    out("ACC+REJ+PREJ (D-06), tutte le granularita' (D-13), blocco di import netto (D-16).")

    tutti = []
    per_giorno = []
    inizio = time.time()

    for i, data in enumerate(giorni, start=1):
        granularita = config.granularita_prevalente(data)
        df = io_gme.carica_giorno(data=data, zona=None, usa_cache=not args.no_cache)

        zone_presenti = set(df["ZONE_CD"].dropna().unique())
        perimetro = ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti]

        ric = curve.clearing_giorno(df, granularita=granularita, zone=perimetro,
                                    includi_altra_granularita=True, con_import=True)
        uff = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)

        giorno = (
            ric.merge(uff[["PERIOD", "prezzo_ufficiale"]], on="PERIOD", how="left")
               .merge(congestione(df, granularita), on="PERIOD", how="left")
        )
        giorno["data"] = data
        giorno["granularita"] = granularita
        giorno["scarto"] = giorno["prezzo"] - giorno["prezzo_ufficiale"]
        # Ora del giorno: utile per confrontare giornate a granularita' diversa.
        giorno["ora"] = ((giorno["PERIOD"] - 1) * config.DURATA_ORE[granularita]).astype(int) + 1
        tutti.append(giorno)

        esito = curve.confronta_con_ufficiale(ric, uff)
        esito["data"] = data
        esito["prezzo_medio_ufficiale"] = float(uff["prezzo_ufficiale"].mean())
        esito["import_medio_MW"] = float(ric["import_netto"].mean())
        esito["periodi_congestionati"] = int(giorno["congestionato"].sum())
        per_giorno.append(esito)

        out(f"  [{i:>2}/{len(giorni)}] {data}  {granularita}  "
            f"err.mediano {esito['errore_mediano']:>7.2f}  "
            f"match ±1€ {esito['match_1.0']:>5.1f}%  "
            f"congestionati {esito['periodi_congestionati']:>2}/{len(giorno)}")

    mese = pd.concat(tutti, ignore_index=True)
    tab_giorni = pd.DataFrame(per_giorno).set_index("data")
    out(f"\nElaborazione completata in {time.time() - inizio:.0f} secondi.")

    # ----------------------------------------------------------------------------------
    out(_sezione("A. RISULTATO COMPLESSIVO DEL MESE"))
    validi = mese.dropna(subset=["prezzo", "prezzo_ufficiale"])
    out(f"Periodi totali             : {len(mese)}")
    out(f"Periodi con equilibrio     : {len(validi)} ({100 * len(validi) / len(mese):.1f}%)")
    if len(validi) < len(mese):
        out("Motivi di mancata intersezione:")
        out(mese.loc[mese["prezzo"].isna(), "motivo"].value_counts().to_string())
    out(f"\nPrezzo ufficiale medio     : {validi['prezzo_ufficiale'].mean():.2f} €/MWh")
    out(f"Prezzo ricostruito medio   : {validi['prezzo'].mean():.2f} €/MWh")
    out("\nScarto (ricostruito - ufficiale, €/MWh):")
    out(validi["scarto"].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).round(2).to_string())
    for t in (0.01, 0.5, 1.0, 5.0, 10.0):
        quota = 100 * (validi["scarto"].abs() <= t).mean()
        out(f"  match entro ±{t:>5.2f} €/MWh : {quota:>5.1f}%")

    # ----------------------------------------------------------------------------------
    out(_sezione("B. STABILITA' NEL TEMPO (per giorno)"))
    out(tab_giorni[["prezzo_medio_ufficiale", "errore_mediano", "bias_mediano",
                    "match_1.0", "match_5.0", "import_medio_MW",
                    "periodi_congestionati"]].round(2).to_string())
    out("\nDispersione fra giornate:")
    out(tab_giorni[["errore_mediano", "bias_mediano", "match_1.0", "match_5.0"]]
        .describe().round(2).to_string())

    # ----------------------------------------------------------------------------------
    out(_sezione("C. ACCURATEZZA PER ORA DEL GIORNO"))
    out("Le ore di picco sono quelle in cui la batteria scarica: e' li' che serve precisione.")
    per_ora = validi.groupby("ora").agg(
        prezzo_ufficiale_medio=("prezzo_ufficiale", "mean"),
        errore_mediano=("scarto", lambda s: s.abs().median()),
        bias_mediano=("scarto", "median"),
        match_1EUR=("scarto", lambda s: 100 * (s.abs() <= 1).mean()),
        match_5EUR=("scarto", lambda s: 100 * (s.abs() <= 5).mean()),
    ).round(2)
    out(per_ora.to_string())

    # ----------------------------------------------------------------------------------
    out(_sezione("D. EFFETTO DELLA CONGESTIONE (test del limite di D-10)"))
    out("Un periodo e' 'congestionato' quando le sette zone italiane non hanno tutte lo")
    out("stesso prezzo: significa che almeno un vincolo di transito e' attivo.")
    per_cong = validi.groupby("congestionato").agg(
        periodi=("scarto", "size"),
        prezzo_ufficiale_medio=("prezzo_ufficiale", "mean"),
        errore_mediano=("scarto", lambda s: s.abs().median()),
        bias_mediano=("scarto", "median"),
        match_1EUR=("scarto", lambda s: 100 * (s.abs() <= 1).mean()),
        match_5EUR=("scarto", lambda s: 100 * (s.abs() <= 5).mean()),
    ).round(2)
    out(per_cong.to_string())
    if validi["congestionato"].any():
        cong = validi[validi["congestionato"]]
        out(f"\nSpread zonale nei periodi congestionati (€/MWh): "
            f"mediano {cong['spread_zonale'].median():.2f}, "
            f"massimo {cong['spread_zonale'].max():.2f}")
        correlazione = cong[["spread_zonale"]].assign(err=cong["scarto"].abs()).corr().iloc[0, 1]
        out(f"Correlazione fra spread zonale ed errore assoluto: {correlazione:.2f}")

    # ----------------------------------------------------------------------------------
    out(_sezione("E. DOVE SBAGLIA DI PIU'"))
    peggiori = validi.reindex(validi["scarto"].abs().sort_values(ascending=False).index)
    colonne = ["data", "PERIOD", "ora", "prezzo", "prezzo_ufficiale", "scarto",
               "congestionato", "spread_zonale", "import_netto"]
    out("\nI 10 periodi con lo scarto piu' grande:")
    out(peggiori[colonne].head(10).round(2).to_string(index=False))

    # ----------------------------------------------------------------------------------
    f_serie = config.PROCESSED_DIR / f"validazione_{args.mese}_NORD.csv"
    f_giorni = config.TABLE_DIR / f"03_per_giorno_{args.mese}.csv"
    f_ore = config.TABLE_DIR / f"03_per_ora_{args.mese}.csv"
    f_report = config.TABLE_DIR / f"03_validazione_{args.mese}.txt"
    mese.to_csv(f_serie, index=False)
    tab_giorni.to_csv(f_giorni)
    per_ora.to_csv(f_ore)

    out(_sezione("FILE PRODOTTI"))
    for f in (f_serie, f_giorni, f_ore, f_report):
        out(f"  {f}")
    f_report.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
