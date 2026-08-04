"""
Passo 5: clearing consapevole delle offerte a blocchi, e indagine sul residuo.

Le due domande
--------------
1. **Quanto guadagna la ricostruzione trattando i blocchi come tutto-o-niente** (D-18)
   invece che come offerte divisibili (D-03)?
2. **Che cosa resta del divario** fra aste a quarto d'ora e aste orarie una volta tolti i
   blocchi dall'equazione? I candidati sono l'accettazione parziale delle offerte e i
   vincoli fra periodi consecutivi.

Che cosa confronta
------------------
Quattro varianti sulle stesse aste:

* **blocchi come semplici**: la ricostruzione attuale, che li tratta come divisibili;
* **blocchi esclusi**: controllo negativo, per verificare che il volume dei blocchi serva;
* **clearing iterativo**: i blocchi sono accettati o rifiutati per intero, sul prezzo medio
  ponderato dei periodi che coprono (D-18);
* **blocchi con esito osservato**: si usa la soluzione vera dell'asta. Non e' un modello
  utilizzabile — usa l'informazione che il modello dovrebbe prevedere — ma misura il
  massimo guadagno ottenibile trattando perfettamente i blocchi, cioe' il limite superiore
  contro cui giudicare l'euristica.

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\05_blocchi_e_residuo.py --giorni 20260112,20260113
    .\\.venv\\Scripts\\python.exe scripts\\05_blocchi_e_residuo.py --mese 202501
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

giorni_del_mese = import_module("03_valida_mese").giorni_del_mese


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def _perimetro(df: pd.DataFrame) -> list[str]:
    presenti = set(df["ZONE_CD"].dropna().unique())
    return ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in presenti]


def varianti_giorno(data: str) -> pd.DataFrame:
    """Ricostruisce una giornata con i quattro trattamenti dei blocchi."""
    granularita = config.granularita_prevalente(data)
    df = io_gme.carica_giorno(data=data, zona=None)
    perimetro = _perimetro(df)
    ufficiale = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)
    prezzi_uff = dict(zip(ufficiale["PERIOD"], ufficiale["prezzo_ufficiale"]))

    iterativo = curve.clearing_giorno_con_blocchi(
        df, granularita, zone=perimetro, includi_altra_granularita=True, con_import=True
    ).set_index("PERIOD")

    righe = []
    for periodo in sorted(df.loc[df["GRANULARITY"] == granularita, "PERIOD"].dropna().unique()):
        periodo = int(periodo)
        if periodo not in prezzi_uff:
            continue
        base = curve.offerte_periodo(df, periodo, granularita, zone=perimetro,
                                     includi_altra_granularita=True)
        scambio = curve.import_netto(df, periodo, granularita, zone=perimetro)
        maschera = curve._e_blocco(base)

        prezzi = {}
        for nome, offerte in [
            ("blocchi come semplici", base),
            ("blocchi esclusi", base[~maschera]),
            ("blocchi con esito osservato", base[~maschera | (base["AWARDED_QUANTITY_NO"] > 0)]),
        ]:
            eq = curve.prezzo_equilibrio(curve.aggiungi_import(offerte, scambio))
            prezzi[nome] = eq.prezzo
        prezzi["clearing iterativo (D-18)"] = iterativo.loc[periodo, "prezzo"]

        voce = {"data": data, "PERIOD": periodo, "granularita": granularita,
                "prezzo_uff": prezzi_uff[periodo],
                "blocchi_accettati": iterativo.loc[periodo, "blocchi_accettati"],
                "blocchi_totali": iterativo.loc[periodo, "blocchi_totali"],
                "iterazioni": iterativo.loc[periodo, "iterazioni"]}
        for nome, prezzo in prezzi.items():
            voce[nome] = prezzo
        righe.append(voce)
    return pd.DataFrame(righe)


def residuo_giorno(data: str) -> pd.DataFrame:
    """
    Misura i due candidati residui, per ciascuna asta.

    * **accettazione parziale**: quante offerte il mercato accetta solo in parte, e quanti
      MW valgono. La nostra ricostruzione accetta parzialmente sempre e solo l'offerta
      marginale: se il mercato ne accetta parzialmente molte di piu', la differenza e' una
      fonte di errore.
    * **vincoli fra periodi consecutivi**: quanto spesso una stessa unita' risulta
      assegnata con quantita' costante lungo l'ora, indizio di un impegno che non si decide
      quarto d'ora per quarto d'ora.
    """
    granularita = config.granularita_prevalente(data)
    df = io_gme.carica_giorno(data=data, zona=None)
    nord = df[(df["ZONE_CD"] == "NORD") & (df["GRANULARITY"] == granularita)
              & (df["STATUS_CD"].isin(config.STATUS_IN_GARA))]

    righe = []
    for periodo in sorted(nord["PERIOD"].dropna().unique()):
        periodo = int(periodo)
        fetta = nord[nord["PERIOD"] == periodo]
        accettate = fetta[fetta["AWARDED_QUANTITY_NO"] > 0]
        parziali = accettate[accettate["AWARDED_QUANTITY_NO"]
                             < accettate["QUANTITY_NO"] - 1e-6]
        righe.append({
            "data": data,
            "PERIOD": periodo,
            "granularita": granularita,
            "offerte_accettate": len(accettate),
            "accettate_parzialmente": len(parziali),
            "MW_accettati_parzialmente": float(parziali["AWARDED_QUANTITY_NO"].sum()),
            "MW_accettati": float(accettate["AWARDED_QUANTITY_NO"].sum()),
        })
    diag = pd.DataFrame(righe)

    # Costanza dell'assegnazione lungo l'ora (solo per le giornate a quarto d'ora).
    if granularita == "PT15":
        vendite = nord[nord["PURPOSE_CD"] == config.PURPOSE_VENDITA].copy()
        vendite["ora"] = ((vendite["PERIOD"] - 1) // 4) + 1
        per_unita = vendite.groupby(["UNIT_REFERENCE_NO", "ora"])["AWARDED_QUANTITY_NO"].agg(
            quarti="size", distinti=lambda s: s.round(3).nunique()
        )
        complete = per_unita[per_unita["quarti"] == 4]
        quota_costanti = (
            100.0 * (complete["distinti"] == 1).mean() if len(complete) else float("nan")
        )
        diag["quota_unita_costanti_nell_ora"] = quota_costanti
    else:
        diag["quota_unita_costanti_nell_ora"] = float("nan")
    return diag


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mese", help="mese da elaborare, formato AAAAMM")
    parser.add_argument("--giorni", help="date AAAAMMGG separate da virgola")
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

    out(_sezione(f"BLOCCHI E RESIDUO — {etichetta}, {len(giorni)} giorni"))

    varianti = pd.concat([varianti_giorno(g) for g in giorni], ignore_index=True)
    colonne_varianti = ["blocchi come semplici", "blocchi esclusi",
                        "clearing iterativo (D-18)", "blocchi con esito osservato"]

    out(_sezione("A. TRATTAMENTO DELLE OFFERTE A BLOCCHI"))
    out("L'ultima variante usa la soluzione vera dell'asta: non e' un modello, e' il limite")
    out("superiore contro cui giudicare l'euristica iterativa.")
    risultati = []
    for nome in colonne_varianti:
        scarto = (varianti[nome] - varianti["prezzo_uff"]).dropna()
        risultati.append({
            "variante": nome,
            "aste": len(scarto),
            "errore_mediano": scarto.abs().median(),
            "scarto_medio": scarto.mean(),
            "dev_standard": scarto.std(),
            "match_1EUR": 100 * (scarto.abs() <= 1).mean(),
            "match_5EUR": 100 * (scarto.abs() <= 5).mean(),
        })
    out("\n" + pd.DataFrame(risultati).set_index("variante").round(2).to_string())

    out("\nBlocchi accettati dall'euristica, per giornata:")
    per_giorno = varianti.groupby("data").agg(
        blocchi_totali=("blocchi_totali", "first"),
        blocchi_accettati=("blocchi_accettati", "first"),
        iterazioni=("iterazioni", "first"),
    )
    per_giorno["quota_accettati_%"] = (
        100 * per_giorno["blocchi_accettati"] / per_giorno["blocchi_totali"]
    ).round(1)
    out(per_giorno.to_string())
    non_convergenti = int((per_giorno["iterazioni"] >= 15).sum())
    out(f"\nGiornate in cui l'euristica non converge (oscillazione): {non_convergenti} "
        f"su {len(per_giorno)}")

    # ----------------------------------------------------------------------------------
    out(_sezione("B. IL RESIDUO: ACCETTAZIONE PARZIALE"))
    out("La nostra ricostruzione accetta parzialmente una sola offerta per asta, quella")
    out("marginale. Se il mercato ne accetta parzialmente molte di piu', la differenza")
    out("spiega parte dell'errore residuo.")
    residuo = pd.concat([residuo_giorno(g) for g in giorni], ignore_index=True)
    riepilogo = residuo.groupby("granularita").agg(
        aste=("PERIOD", "size"),
        offerte_accettate_per_asta=("offerte_accettate", "mean"),
        accettate_parzialmente_per_asta=("accettate_parzialmente", "mean"),
        MW_parziali_per_asta=("MW_accettati_parzialmente", "mean"),
        MW_accettati_per_asta=("MW_accettati", "mean"),
    ).round(2)
    riepilogo["quota_MW_parziali_%"] = (
        100 * riepilogo["MW_parziali_per_asta"] / riepilogo["MW_accettati_per_asta"]
    ).round(2)
    out("\n" + riepilogo.to_string())

    out(_sezione("C. IL RESIDUO: VINCOLI FRA QUARTI D'ORA CONSECUTIVI"))
    out("Quota di unita' la cui quantita' assegnata resta identica nei quattro quarti")
    out("d'ora di un'ora: se e' alta, l'impegno non si decide quarto per quarto e la")
    out("nostra ricostruzione, che tratta ogni asta come indipendente, non puo' seguirlo.")
    quote = residuo.groupby("data")["quota_unita_costanti_nell_ora"].first().dropna()
    if len(quote):
        out(f"\nMedia sulle giornate a quarto d'ora: {quote.mean():.1f}%")
        out(quote.round(1).to_string())
    else:
        out("\nNessuna giornata a quarto d'ora nel campione.")

    f_varianti = config.PROCESSED_DIR / f"varianti_blocchi_{etichetta}.csv"
    f_report = config.TABLE_DIR / f"05_blocchi_e_residuo_{etichetta}.txt"
    varianti.to_csv(f_varianti, index=False)

    out(_sezione("FILE PRODOTTI"))
    for f in (f_varianti, f_report):
        out(f"  {f}")
    f_report.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
