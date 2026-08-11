"""
Passo 7, controllo 1: ispezione visiva delle curve nei periodi estremi.

Perche' serve
-------------
Il risultato centrale — una soglia di poche decine di megawatt — poggia interamente sulla
**pendenza della curva di offerta nelle ore in cui l'accumulo opera**, cioe' quella di minimo
e quella di massimo prezzo. Se quella pendenza fosse sostenuta da pochissime offerte isolate,
o fosse l'artefatto del modo in cui trattiamo le offerte ai prezzi limite, il risultato non
reggerebbe. Questo controllo lo verifica guardando le curve.

Che cosa produce
----------------
Per ciascuna giornata scelta, una figura con quattro riquadri: l'ora di minimo e quella di
picco, ciascuna in vista completa e ingrandita attorno all'equilibrio. Piu' una tabella con,
per ogni periodo ispezionato, il prezzo ricostruito, quello ufficiale, la quantita' scambiata
e **il numero di gradini di offerta compresi nella finestra di ingrandimento**, che e' il
controllo quantitativo dell'ispezione visiva.

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\07_ispezione_curve.py
    .\\.venv\\Scripts\\python.exe scripts\\07_ispezione_curve.py --giorni 20250115,20250120
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mgp import config, curve, grafici, io_gme  # noqa: E402


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def giorni_rappresentativi(etichetta: str = "202501") -> list[str]:
    """
    Sceglie due giornate a partire dal loro differenziale di prezzo.

    Non si prendono giorni a caso: si prende quello con il **differenziale mediano**, che
    rappresenta la giornata tipica, e quello con il **differenziale massimo**, che e' la
    giornata in cui l'arbitraggio rende di piu' e quindi quella su cui il risultato e' piu'
    sensibile. Se il file delle erosioni non c'e', si ripiega su due date fisse.
    """
    percorso = config.PROCESSED_DIR / f"erosioni_{etichetta}.csv"
    if not percorso.exists():
        return ["20250115", "20250120"]
    tabella = pd.read_csv(percorso, dtype={"data": str})
    per_giorno = tabella.groupby("data")["spread_giornaliero"].first().sort_values()
    mediano = per_giorno.index[len(per_giorno) // 2]
    massimo = per_giorno.index[-1]
    return [mediano, massimo]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--giorni", help="date AAAAMMGG separate da virgola")
    parser.add_argument("--etichetta", default="202501",
                        help="campione da cui dedurre le giornate rappresentative")
    args = parser.parse_args()

    giorni = args.giorni.split(",") if args.giorni else giorni_rappresentativi(args.etichetta)

    config.assicura_cartelle()
    pd.set_option("display.width", 140)
    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo, flush=True)
        buffer.write(testo + "\n")

    out(_sezione(f"ISPEZIONE DELLE CURVE — giornate {', '.join(giorni)}"))
    out("Per ogni giornata si ispezionano l'ora di minimo e l'ora di picco: sono i periodi")
    out("in cui l'accumulo carica e scarica, e quindi gli unici in cui la sua taglia conta.")

    diagnostiche = []
    for data in giorni:
        granularita = config.granularita_prevalente(data)
        df = io_gme.carica_giorno(data=data, zona=None)
        zone_presenti = set(df["ZONE_CD"].dropna().unique())
        perimetro = ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti]

        offerte_giorno = curve.offerte_giornata(df, granularita, zone=perimetro, con_import=True)
        periodi = sorted(offerte_giorno)
        prezzi = {p: curve.prezzo_equilibrio(offerte_giorno[p]).prezzo for p in periodi}
        validi = {p: v for p, v in prezzi.items() if v is not None}
        periodo_minimo = min(validi, key=validi.get)
        periodo_massimo = max(validi, key=validi.get)

        ufficiali = io_gme.prezzi_ufficiali(df[df["ZONE_CD"] == "NORD"], granularita=granularita)
        mappa_ufficiali = dict(zip(ufficiali["PERIOD"], ufficiali["prezzo_ufficiale"]))

        out(f"\n{data} ({granularita}): minimo al periodo {periodo_minimo} "
            f"({validi[periodo_minimo]:.2f} €/MWh), picco al periodo {periodo_massimo} "
            f"({validi[periodo_massimo]:.2f} €/MWh), "
            f"differenziale {validi[periodo_massimo] - validi[periodo_minimo]:.2f}")

        figura, diagnostica = grafici.figura_giornata(
            df, data, granularita, periodo_minimo, periodo_massimo,
            zone=perimetro, prezzi_ufficiali=mappa_ufficiali,
        )
        percorso = grafici.salva(figura, f"07_curve_{data}")
        out(f"  figura: {percorso}")

        # Curva di impatto marginale dei due periodi estremi: rende leggibile in un colpo
        # d'occhio quanto ciascuno sia elastico, e l'asimmetria fra carica e scarica.
        figura_imp = grafici.curva_impatto(
            {int(periodo_minimo): offerte_giorno[int(periodo_minimo)],
             int(periodo_massimo): offerte_giorno[int(periodo_massimo)]},
            griglia_mw=np.linspace(-2000, 2000, 161),
            granularita=granularita,
            etichette={int(periodo_minimo): "ora di minimo",
                       int(periodo_massimo): "ora di picco"},
            titolo=f"Impatto marginale sul prezzo — {data}",
        )
        out(f"  figura: {grafici.salva(figura_imp, f'07_impatto_{data}')}")

        diagnostica["prezzo_ufficiale"] = diagnostica["PERIOD"].map(mappa_ufficiali)
        diagnostica["scarto"] = diagnostica["prezzo"] - diagnostica["prezzo_ufficiale"]
        diagnostiche.append(diagnostica)

        # Composizione delle offerte attorno all'equilibrio: e' il controllo che la pendenza
        # non dipenda da poche offerte molto grandi.
        for periodo, tipo in [(periodo_minimo, "minimo"), (periodo_massimo, "picco")]:
            offerte = offerte_giorno[int(periodo)]
            eq = curve.prezzo_equilibrio(offerte)
            vendita = offerte[offerte["PURPOSE_CD"] == config.PURPOSE_VENDITA]
            finestra = vendita[(vendita["ENERGY_PRICE_NO"] >= eq.prezzo - 20)
                               & (vendita["ENERGY_PRICE_NO"] <= eq.prezzo + 20)]
            ai_limiti = vendita[(vendita["ENERGY_PRICE_NO"] <= config.PREZZO_MINIMO)
                                | (vendita["ENERGY_PRICE_NO"] >= config.PREZZO_MASSIMO)]
            out(f"  periodo {periodo} ({tipo}): "
                f"{len(finestra)} offerte di vendita entro ±20 €/MWh dall'equilibrio, "
                f"per {finestra['QUANTITY_NO'].sum():.0f} MW "
                f"(la piu' grande {finestra['QUANTITY_NO'].max() if len(finestra) else 0:.0f} MW); "
                f"{len(ai_limiti)} offerte ai limiti di prezzo per "
                f"{ai_limiti['QUANTITY_NO'].sum():.0f} MW")
            # Pendenza effettiva: di quanto si sposta il prezzo iniettando o sottraendo
            # potenza. E' la grandezza che determina l'erosione, quindi va misurata qui.
            for delta in (100.0, 500.0, 1500.0):
                giu = curve.impatto_prezzo(offerte, delta)      # scarica: offerta in piu'
                su = curve.impatto_prezzo(offerte, -delta)      # carica: domanda in piu'
                out(f"      {delta:>6.0f} MW: scaricando {giu['variazione']:+7.2f} €/MWh, "
                    f"caricando {su['variazione']:+7.2f} €/MWh")

    tabella = pd.concat(diagnostiche, ignore_index=True)
    out(_sezione("DIAGNOSTICA DEI PERIODI ISPEZIONATI"))
    out("`gradini_nello_zoom` conta i gradini di offerta compresi nella finestra di")
    out("ingrandimento: se fossero pochissimi, la pendenza sarebbe fragile.")
    out("\n" + tabella[["data", "PERIOD", "tipo", "prezzo", "prezzo_ufficiale", "scarto",
                        "quantita", "gradini_nello_zoom"]].round(2).to_string(index=False))

    f_tabella = config.TABLE_DIR / "07_ispezione_curve.csv"
    f_report = config.TABLE_DIR / "07_ispezione_curve.txt"
    tabella.to_csv(f_tabella, index=False)

    out(_sezione("FILE PRODOTTI"))
    for f in (f_tabella, f_report):
        out(f"  {f}")
    f_report.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
