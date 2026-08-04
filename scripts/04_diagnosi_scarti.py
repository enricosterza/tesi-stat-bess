"""
Passo 4: diagnosi degli scarti residui fra prezzo ricostruito e prezzo ufficiale.

Le due domande
--------------
1. **Perche' le aste a quarto d'ora si ricostruiscono peggio di quelle orarie?**
2. **Perche' gli scarti residui si concentrano in poche giornate?**

Come si risponde
----------------
Per ogni asta si scompone lo scarto nelle sue possibili cause, misurandole separatamente.

* **Equilibrio non unico.** L'eccesso di offerta S(p) - D(p) e' monotono non decrescente,
  quindi i prezzi che pareggiano il mercato formano sempre una semiretta. Se pero' l'eccesso
  vale esattamente zero su un tratto, ogni prezzo di quel tratto e' un equilibrio: la nostra
  regola sceglie il piu' basso, GME potrebbe sceglierne un altro. In quel caso lo scarto non
  e' un errore di ricostruzione ma una convenzione diversa, e si riconosce dal fatto che il
  prezzo ufficiale **cade dentro l'intervallo**.
* **Errore sul lato domanda / sul lato offerta.** Si confrontano la domanda e l'offerta
  ricostruite al prezzo ufficiale con le quantita' effettivamente assegnate: se la domanda
  coincide e l'offerta no, l'errore e' tutto sulla curva di vendita (e viceversa).
* **Caratteristiche della giornata.** Quota di offerte a granularita' non prevalente, quota
  di offerte a blocchi, ampiezza dello scambio netto: si verifica se le giornate peggiori
  hanno qualcosa in comune.

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\04_diagnosi_scarti.py --mese 202501
    .\\.venv\\Scripts\\python.exe scripts\\04_diagnosi_scarti.py --giorni 20260331
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from mgp import config, curve, io_gme  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

_mese = import_module("03_valida_mese")
giorni_del_mese = _mese.giorni_del_mese
congestione = _mese.congestione


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def diagnosi_giorno(data: str, usa_cache: bool = True) -> pd.DataFrame:
    """
    Scompone lo scarto di ciascuna asta di una giornata.

    Returns
    -------
    pd.DataFrame
        Una riga per periodo con prezzo ricostruito e ufficiale, estremi dell'intervallo di
        equilibrio, domanda e offerta ricostruite al prezzo ufficiale confrontate con le
        quantita' assegnate, e le caratteristiche strutturali del periodo.
    """
    granularita = config.granularita_prevalente(data)
    df = io_gme.carica_giorno(data=data, zona=None, usa_cache=usa_cache)
    zone_presenti = set(df["ZONE_CD"].dropna().unique())
    perimetro = ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti]

    ufficiale = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)
    prezzi_uff = dict(zip(ufficiale["PERIOD"], ufficiale["prezzo_ufficiale"]))

    nel_perimetro = df[df["ZONE_CD"].isin(perimetro)]
    righe = []
    for periodo in sorted(df.loc[df["GRANULARITY"] == granularita, "PERIOD"].dropna().unique()):
        periodo = int(periodo)
        offerte = curve.offerte_periodo(df, periodo, granularita, zone=perimetro,
                                        includi_altra_granularita=True)
        scambio = curve.import_netto(df, periodo, granularita, zone=perimetro)
        con_scambio = curve.aggiungi_import(offerte, scambio)

        eq = curve.prezzo_equilibrio(con_scambio)
        intervallo = curve.intervallo_equilibrio(con_scambio)
        p_uff = prezzi_uff.get(periodo, float("nan"))
        # Sensibilita' del prezzo a 100 MW di offerta aggiuntiva: dove le curve sono quasi
        # tangenti un piccolo errore di quantita' produce un grande errore di prezzo.
        impatto = curve.impatto_prezzo(con_scambio, 100.0)

        # Curve ricostruite valutate al prezzo ufficiale, **al netto del blocco di scambio**:
        # il blocco non e' un'offerta del perimetro, quindi non compare fra le quantita'
        # assegnate e includerlo nel confronto falserebbe la diagnosi.
        vend = offerte[offerte["PURPOSE_CD"] == config.PURPOSE_VENDITA]
        acq = offerte[offerte["PURPOSE_CD"] == config.PURPOSE_ACQUISTO]
        S_uff = float(vend.loc[vend["ENERGY_PRICE_NO"] <= p_uff, "QUANTITY_NO"].sum())
        D_uff = float(acq.loc[acq["ENERGY_PRICE_NO"] >= p_uff, "QUANTITY_NO"].sum())

        # Quantita' effettivamente assegnate nel perimetro (somma delle granularita').
        assegnate: dict[str, float] = {}
        for g in df["GRANULARITY"].dropna().unique():
            per = periodo if g == granularita else curve.periodo_contenitore(periodo, g, granularita)
            fetta = nel_perimetro[(nel_perimetro["GRANULARITY"] == g) & (nel_perimetro["PERIOD"] == per)]
            for lato, valore in fetta.groupby("PURPOSE_CD")["AWARDED_QUANTITY_NO"].sum().items():
                assegnate[lato] = assegnate.get(lato, 0.0) + float(valore)
        bid_ass = assegnate.get(config.PURPOSE_ACQUISTO, 0.0)
        off_ass = assegnate.get(config.PURPOSE_VENDITA, 0.0)

        # Composizione delle offerte del periodo.
        altra_gran = offerte[offerte["GRANULARITY"] != granularita]
        blocchi = offerte[offerte.get("OFFER_TYPE", pd.Series(dtype=object)) == "B"]

        righe.append({
            "data": data,
            "PERIOD": periodo,
            "granularita": granularita,
            "prezzo_ric": eq.prezzo,
            "prezzo_uff": p_uff,
            "scarto": (eq.prezzo - p_uff) if eq.prezzo is not None else float("nan"),
            "p_equilibrio_min": intervallo["prezzo_minimo"],
            "p_equilibrio_max": intervallo["prezzo_massimo"],
            "ampiezza_intervallo": intervallo["ampiezza"],
            "degenere": intervallo["degenere"],
            "uff_nell_intervallo": bool(
                intervallo["prezzo_minimo"] - 1e-6 <= p_uff <= intervallo["prezzo_massimo"] + 1e-6
            ),
            "S_al_prezzo_uff": S_uff,
            "D_al_prezzo_uff": D_uff,
            "OFF_assegnata": off_ass,
            "BID_assegnata": bid_ass,
            "err_offerta_pct": 100 * (S_uff - off_ass) / off_ass if off_ass else float("nan"),
            "err_domanda_pct": 100 * (D_uff - bid_ass) / bid_ass if bid_ass else float("nan"),
            "scambio_netto": scambio,
            "sensibilita_100MW": impatto["sensibilita"],
            "quantita_scambiata": eq.quantita,
            "n_offerte": len(offerte),
            "quota_altra_gran_pct": 100 * len(altra_gran) / len(offerte) if len(offerte) else 0.0,
            "quota_blocchi_pct": 100 * len(blocchi) / len(offerte) if len(offerte) else 0.0,
        })
    diag = pd.DataFrame(righe)
    return diag.merge(congestione(df, granularita), on="PERIOD", how="left")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mese", help="mese da diagnosticare, formato AAAAMM")
    parser.add_argument("--giorni", help="elenco di date AAAAMMGG separate da virgola")
    parser.add_argument("--etichetta", help="nome per i file prodotti")
    args = parser.parse_args()

    if args.giorni:
        giorni = args.giorni.split(",")
    elif args.mese:
        giorni = giorni_del_mese(args.mese)
    else:
        parser.error("indicare --mese oppure --giorni")
    etichetta = args.etichetta or (args.mese or giorni[0])

    config.assicura_cartelle()
    pd.set_option("display.width", 140)
    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo, flush=True)
        buffer.write(testo + "\n")

    out(_sezione(f"DIAGNOSI DEGLI SCARTI — {etichetta}, {len(giorni)} giorni"))
    diag = pd.concat([diagnosi_giorno(g) for g in giorni], ignore_index=True)
    validi = diag.dropna(subset=["prezzo_ric", "prezzo_uff"]).copy()
    validi["scarto_assoluto"] = validi["scarto"].abs()

    # ----------------------------------------------------------------------------------
    out(_sezione("A. L'EQUILIBRIO E' UNICO?"))
    out("L'eccesso di offerta e' monotono, quindi i prezzi che pareggiano il mercato formano")
    out("una semiretta. Se l'eccesso e' nullo su un tratto, ogni prezzo del tratto e' un")
    out("equilibrio valido e la scelta del punto e' una convenzione, non un dato.")
    n_deg = int(validi["degenere"].sum())
    out(f"\nAste con equilibrio non unico: {n_deg} su {len(validi)} "
        f"({100 * n_deg / len(validi):.1f}%)")
    if n_deg:
        deg = validi[validi["degenere"]]
        out(f"Ampiezza dell'intervallo (€/MWh): mediana {deg['ampiezza_intervallo'].median():.2f}, "
            f"massima {deg['ampiezza_intervallo'].max():.2f}")
        out(f"Prezzo ufficiale dentro l'intervallo: {int(deg['uff_nell_intervallo'].sum())} "
            f"su {n_deg}")
    out("\nScarto medio secondo l'unicita' dell'equilibrio:")
    out(validi.groupby("degenere").agg(
        aste=("scarto", "size"),
        scarto_mediano=("scarto", "median"),
        errore_mediano=("scarto_assoluto", "median"),
        match_1EUR=("scarto_assoluto", lambda s: 100 * (s <= 1).mean()),
    ).round(2).to_string())

    # ----------------------------------------------------------------------------------
    out(_sezione("B. QUALE LATO DEL MERCATO SBAGLIA"))
    out("Domanda e offerta ricostruite al prezzo ufficiale, confrontate con le quantita'")
    out("effettivamente assegnate (scarto percentuale).")
    out("\nPer granularita' dell'asta:")
    out(validi.groupby("granularita").agg(
        aste=("scarto", "size"),
        err_domanda_mediano=("err_domanda_pct", "median"),
        err_domanda_assoluto=("err_domanda_pct", lambda s: s.abs().median()),
        err_offerta_mediano=("err_offerta_pct", "median"),
        err_offerta_assoluto=("err_offerta_pct", lambda s: s.abs().median()),
        errore_prezzo_mediano=("scarto_assoluto", "median"),
    ).round(3).to_string())

    # ----------------------------------------------------------------------------------
    out(_sezione("C. SENSIBILITA' DEL PREZZO: QUANTO VALE UN ERRORE DI QUANTITA'"))
    out("Sensibilita' = variazione del prezzo di equilibrio per 100 MW di offerta")
    out("aggiuntiva. Dove le curve sono quasi tangenti la sensibilita' e' alta, e un")
    out("piccolo errore sulle quantita' produce un grande errore sul prezzo.")
    out("\nDistribuzione della sensibilita' (€/MWh per 100 MW):")
    out(validi.groupby("granularita")["sensibilita_100MW"]
        .describe(percentiles=[0.25, 0.5, 0.75, 0.9]).round(3).to_string())
    out("\nErrore sul prezzo per classe di sensibilita':")
    # Soglie fisse invece di quantili: un quarto delle aste ha sensibilita' esattamente
    # nulla (100 MW non spostano il prezzo di un centesimo) e i quantili collasserebbero.
    classi = pd.cut(
        validi["sensibilita_100MW"],
        bins=[-0.001, 0.001, 0.5, 2.0, 10.0, float("inf")],
        labels=["nulla (curve ripide)", "bassa", "media", "alta", "molto alta (quasi tangenti)"],
    )
    out(validi.groupby(classi, observed=True).agg(
        aste=("scarto_assoluto", "size"),
        sensibilita_mediana=("sensibilita_100MW", "median"),
        errore_prezzo_mediano=("scarto_assoluto", "median"),
        match_1EUR=("scarto_assoluto", lambda s: 100 * (s <= 1).mean()),
        err_offerta_assoluto=("err_offerta_pct", lambda s: s.abs().median()),
    ).round(3).to_string())
    correlazione = validi["sensibilita_100MW"].corr(validi["scarto_assoluto"])
    out(f"\nCorrelazione fra sensibilita' ed errore assoluto sul prezzo: {correlazione:.2f}")

    # ----------------------------------------------------------------------------------
    out(_sezione("D. CHE COSA HANNO IN COMUNE LE GIORNATE PEGGIORI"))
    per_giorno = validi.groupby("data").agg(
        errore_mediano=("scarto_assoluto", "median"),
        errore_massimo=("scarto_assoluto", "max"),
        match_1EUR=("scarto_assoluto", lambda s: 100 * (s <= 1).mean()),
        sensibilita_mediana=("sensibilita_100MW", "median"),
        quota_degeneri=("degenere", lambda s: 100 * s.mean()),
        quota_altra_gran=("quota_altra_gran_pct", "mean"),
        quota_blocchi=("quota_blocchi_pct", "mean"),
        scambio_medio=("scambio_netto", "mean"),
        err_offerta_assoluto=("err_offerta_pct", lambda s: s.abs().median()),
        periodi_congestionati=("congestionato", "sum"),
    ).round(3).sort_values("errore_mediano", ascending=False)
    out(per_giorno.to_string())

    if len(per_giorno) > 2:
        out("\nCorrelazione fra l'errore mediano della giornata e le sue caratteristiche:")
        correlazioni = per_giorno.corr(numeric_only=True)["errore_mediano"].drop("errore_mediano")
        out(correlazioni.round(2).sort_values(ascending=False).to_string())

    # ----------------------------------------------------------------------------------
    out(_sezione("E. I DIECI SCARTI PIU' GRANDI, SCOMPOSTI"))
    colonne = ["data", "PERIOD", "prezzo_ric", "prezzo_uff", "scarto", "sensibilita_100MW",
               "err_domanda_pct", "err_offerta_pct", "degenere", "scambio_netto",
               "congestionato"]
    peggiori = validi.reindex(validi["scarto_assoluto"].sort_values(ascending=False).index)
    out(peggiori[colonne].head(10).round(2).to_string(index=False))

    f_diag = config.PROCESSED_DIR / f"diagnosi_scarti_{etichetta}.csv"
    f_giorni = config.TABLE_DIR / f"04_per_giorno_{etichetta}.csv"
    f_report = config.TABLE_DIR / f"04_diagnosi_{etichetta}.txt"
    diag.to_csv(f_diag, index=False)
    per_giorno.to_csv(f_giorni)

    out(_sezione("FILE PRODOTTI"))
    for f in (f_diag, f_giorni, f_report):
        out(f"  {f}")
    f_report.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
