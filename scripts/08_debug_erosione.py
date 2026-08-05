"""
Passo 8, controllo 2: che cosa succede davvero, periodo per periodo, quando entra la flotta.

Perche' serve
-------------
Due domande a cui i numeri aggregati non rispondono.

La prima: oltre una certa capacita' l'erosione supera il 100%, cioe' il profitto price maker
diventa **negativo**. Va stabilito se sia economia reale — la flotta esegue un piano deciso su
prezzi che essa stessa distrugge, e finisce per comprare caro e vendere a poco — oppure un
artefatto di calcolo.

La seconda: il piano fisico di carica e scarica **non deve** essere riottimizzato quando si
ricalcolano i prezzi. Nello scenario adottato (D-25) le batterie sono piccole e non
coordinate: decidono sul segnale di prezzo storico e poi subiscono lo spostamento che hanno
causato. Una riottimizzazione nascosta reintrodurrebbe di fatto il punto fisso che si era
deciso di evitare, e cambierebbe la domanda a cui il modello risponde. Qui la si verifica
esplicitamente, confrontando il piano usato con quello ricalcolato sui prezzi di riferimento.

Esecuzione
----------
    .\\.venv\\Scripts\\python.exe scripts\\08_debug_erosione.py --giorno 20250120
    .\\.venv\\Scripts\\python.exe scripts\\08_debug_erosione.py --giorno 20250120 \\
        --capacita 25,100,1500
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mgp import batteria as bt  # noqa: E402
from mgp import config, curve, io_gme  # noqa: E402


def _sezione(titolo: str) -> str:
    return f"\n{'=' * 78}\n{titolo}\n{'=' * 78}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--giorno", default="20250120")
    parser.add_argument("--capacita", default="25,100,1500",
                        help="capacita' aggregate da ispezionare, in MW")
    parser.add_argument("--durata", type=float, default=4.0)
    args = parser.parse_args()

    capacita = [float(x) for x in args.capacita.split(",")]
    data = args.giorno
    granularita = config.granularita_prevalente(data)

    config.assicura_cartelle()
    pd.set_option("display.width", 150)
    buffer = io.StringIO()

    def out(*parti: object) -> None:
        testo = " ".join(str(p) for p in parti)
        print(testo, flush=True)
        buffer.write(testo + "\n")

    df = io_gme.carica_giorno(data=data, zona=None)
    zone_presenti = set(df["ZONE_CD"].dropna().unique())
    perimetro = ["NORD"] + [z for z in config.ZONE_FRONTIERA_NORD if z in zone_presenti]
    offerte_giorno = curve.offerte_giornata(df, granularita, zone=perimetro, con_import=True)
    periodi = sorted(offerte_giorno)
    delta = config.DURATA_ORE[granularita]
    riferimento = np.array(
        [curve.prezzo_equilibrio(offerte_giorno[p]).prezzo for p in periodi], dtype=float
    )

    out(_sezione(f"DEBUG DELL'EROSIONE — {data} ({granularita}), flotta da {args.durata} ore"))
    out(f"Prezzi di riferimento: minimo {np.nanmin(riferimento):.2f}, "
        f"massimo {np.nanmax(riferimento):.2f}, "
        f"differenziale {np.nanmax(riferimento) - np.nanmin(riferimento):.2f} €/MWh")

    riepiloghi = []
    for potenza in capacita:
        e = bt.erosione(df, potenza_aggregata_mw=potenza, granularita=granularita, data=data,
                        durata_ore=args.durata, zone=perimetro,
                        prezzi_riferimento=riferimento, offerte_giorno=offerte_giorno)
        profilo = e.profilo.copy()
        profilo["netto_mw"] = profilo["scarica_mw"] - profilo["carica_mw"]
        profilo["variazione_prezzo"] = (profilo["prezzo_con_accumulo"]
                                        - profilo["prezzo_riferimento"])
        profilo["contributo_PT"] = profilo["prezzo_riferimento"] * profilo["netto_mw"] * delta
        profilo["contributo_PM"] = profilo["prezzo_con_accumulo"] * profilo["netto_mw"] * delta
        profilo["erosione_periodo"] = profilo["contributo_PT"] - profilo["contributo_PM"]

        out(_sezione(f"CAPACITA' AGGREGATA {potenza:.0f} MW "
                     f"({potenza * args.durata:.0f} MWh)"))

        attivi = profilo[profilo["netto_mw"].abs() > 1e-6]
        out(f"Periodi in cui la flotta opera: {len(attivi)} su {len(profilo)}")
        colonne = ["PERIOD", "prezzo_riferimento", "prezzo_con_accumulo", "variazione_prezzo",
                   "carica_mw", "scarica_mw", "contributo_PT", "contributo_PM",
                   "erosione_periodo"]
        out("\n" + attivi[colonne].round(2).to_string(index=False))

        out(f"\nProfitto price taker : {e.profitto_price_taker:>12.2f} €")
        out(f"Profitto price maker : {e.profitto_price_maker:>12.2f} €")
        out(f"Erosione assoluta    : {e.erosione_assoluta:>12.2f} €")
        if np.isfinite(e.erosione_relativa):
            out(f"Erosione relativa    : {e.erosione_relativa:>12.2%}")
        else:
            out("Erosione relativa    :          non calcolabile")

        carica = attivi[attivi["carica_mw"] > 0]
        scarica = attivi[attivi["scarica_mw"] > 0]
        if len(carica) and len(scarica):
            out(f"\n  dai periodi di carica  : {carica['erosione_periodo'].sum():>12.2f} € "
                f"(prezzo medio {carica['prezzo_riferimento'].mean():.2f} -> "
                f"{carica['prezzo_con_accumulo'].mean():.2f})")
            out(f"  dai periodi di scarica : {scarica['erosione_periodo'].sum():>12.2f} € "
                f"(prezzo medio {scarica['prezzo_riferimento'].mean():.2f} -> "
                f"{scarica['prezzo_con_accumulo'].mean():.2f})")

            mwh_scaricati = float(scarica["scarica_mw"].sum() * delta)
            mwh_caricati = float(carica["carica_mw"].sum() * delta)
            ricavo = float((scarica["prezzo_con_accumulo"] * scarica["scarica_mw"] * delta).sum())
            costo = float((carica["prezzo_con_accumulo"] * carica["carica_mw"] * delta).sum())
            out(f"\n  prezzo medio di vendita realizzato : {ricavo / mwh_scaricati:>8.2f} €/MWh")
            out(f"  prezzo medio di acquisto realizzato : {costo / mwh_caricati:>8.2f} €/MWh")
            out(f"  energia comprata {mwh_caricati:.0f} MWh, venduta {mwh_scaricati:.0f} MWh "
                f"(la differenza e' la perdita di rendimento)")

        # --- Verifica che il piano non sia stato riottimizzato -------------------------
        accumulo = bt.flotta(potenza, args.durata)
        atteso_c, atteso_s = bt.profilo_ottimo(riferimento, accumulo, delta)
        coincide = (np.allclose(profilo["carica_mw"].to_numpy(), atteso_c, atol=1e-6)
                    and np.allclose(profilo["scarica_mw"].to_numpy(), atteso_s, atol=1e-6))
        riottimizzato_c, riottimizzato_s = bt.profilo_ottimo(
            np.nan_to_num(profilo["prezzo_con_accumulo"].to_numpy()), accumulo, delta)
        diverso = (not np.allclose(riottimizzato_c, atteso_c, atol=1e-6)
                   or not np.allclose(riottimizzato_s, atteso_s, atol=1e-6))
        out(f"\n  il piano usato coincide con quello ottimo sui prezzi di riferimento: "
            f"{'SI' if coincide else 'NO — RIOTTIMIZZAZIONE NASCOSTA'}")
        out(f"  ottimizzando sui prezzi con accumulo si otterrebbe un piano diverso: "
            f"{'si' if diverso else 'no'}")

        riepiloghi.append({
            "potenza_mw": potenza,
            "profitto_PT": e.profitto_price_taker,
            "profitto_PM": e.profitto_price_maker,
            "erosione_assoluta": e.erosione_assoluta,
            "erosione_relativa": e.erosione_relativa,
            "periodi_attivi": len(attivi),
            "piano_non_riottimizzato": coincide,
        })

    out(_sezione("RIEPILOGO"))
    out("\n" + pd.DataFrame(riepiloghi).round(3).to_string(index=False))

    f_report = config.TABLE_DIR / f"08_debug_erosione_{data}.txt"
    f_report.write_text(buffer.getvalue(), encoding="utf-8")
    out(f"\nFile prodotto: {f_report}")


if __name__ == "__main__":
    main()
