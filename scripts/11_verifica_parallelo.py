"""
Verifica che la parallelizzazione acceleri senza cambiare i risultati, e ne misura lo speedup.

Perche' serve uno script e non una prova estemporanea
-----------------------------------------------------
La parallelizzazione e' un cambiamento infrastrutturale che tocca **tutti** i numeri della
tesi: se introducesse una differenza, anche minima, la scoprirebbe il lettore e non l'autore.
La verifica va quindi rifatta ogni volta che si tocca `mgp.parallelo`, `mgp.batteria` o la
griglia, ed e' per questo che sta in uno script numerato e non in un notebook.

Tre verifiche, tre domande diverse
----------------------------------
1. **Non regressione**: gli stessi giorni calcolati in sequenza e su piu' processi danno gli
   stessi numeri? Il confronto e' **esatto**, non a due decimali: `erosioni_giorno` e' pura
   rispetto alla data, quindi i float devono coincidere bit a bit. Accontentarsi del
   centesimo nasconderebbe una differenza sistematica piccola, che e' il sintomo peggiore
   perche' non si nota e si propaga.
2. **Ordine**: la tabella prodotta in parallelo ha le righe nella stessa sequenza?
3. **Seme**: il bootstrap resta riproducibile, ed e' invariante rispetto all'ordine delle
   righe in ingresso?

Esempi
------
    .\\.venv\\Scripts\\python.exe scripts\\11_verifica_parallelo.py
    .\\.venv\\Scripts\\python.exe scripts\\11_verifica_parallelo.py --speedup --giorni-speedup 16
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mgp import batteria as bt  # noqa: E402
from mgp import config, io_gme, parallelo  # noqa: E402

#: Giorni della verifica: sparsi sull'anno, per non provare la parallelizzazione su
#: giornate tutte simili fra loro.
GIORNI_VERIFICA = ["20240115", "20240116", "20240320", "20240615", "20240918", "20241215"]

#: Giorni per la misura di speedup: consecutivi, cosi' il carico e' realistico.
def giorni_speedup(quanti: int) -> list[str]:
    base = pd.date_range("2024-03-01", periods=quanti, freq="D")
    return [d.strftime("%Y%m%d") for d in base]


def verifica(giorni: list[str], processi: int, out) -> bool:
    out("=" * 86)
    out(f"1-2. NON REGRESSIONE E ORDINE — {len(giorni)} giorni, "
        f"{len(bt.GRIGLIA_CAPACITA_MW)} capacita'")
    out("=" * 86)

    t0 = time.perf_counter()
    seq = parallelo.erosioni_campione(giorni, processi=1)
    t_seq = time.perf_counter() - t0
    out(f"sequenza : {len(seq):,} righe in {t_seq:.1f} s")

    t0 = time.perf_counter()
    par = parallelo.erosioni_campione(giorni, processi=processi)
    t_par = time.perf_counter() - t0
    out(f"parallelo: {len(par):,} righe in {t_par:.1f} s   ({processi} processi)")

    if list(seq.columns) != list(par.columns) or len(seq) != len(par):
        out("FALLITA: forma della tabella diversa.")
        return False

    ordine = seq[["data", "potenza_mw"]].equals(par[["data", "potenza_mw"]])
    out(f"\nrighe (data, potenza_mw) nella stessa sequenza: {ordine}")

    numeriche = [c for c in seq.columns if seq[c].dtype.kind in "fi"]
    identiche = True
    for c in numeriche:
        a, b = seq[c].to_numpy(float), par[c].to_numpy(float)
        if not np.array_equal(a, b, equal_nan=True):
            identiche = False
            out(f"  {c}: DIVERSA, scarto massimo {np.nanmax(np.abs(a - b)):.3e}")
    out(f"confronto esatto sulle {len(numeriche)} colonne numeriche: "
        + ("tutte identiche bit a bit" if identiche else "DIFFERENZE PRESENTI"))

    testuali = [c for c in seq.columns if c not in numeriche]
    testo_ok = all(seq[c].equals(par[c]) for c in testuali)
    out(f"colonne non numeriche identiche: {testo_ok}")

    # ------------------------------------------------------------------ il seme
    out("\n" + "=" * 86)
    out("3. SEME — riproducibilita' del bootstrap e invarianza all'ordine")
    out("=" * 86)
    out("Il parallelismo sta a monte del generatore: i lavoratori non estraggono numeri")
    out("casuali, il bootstrap gira dopo e in un solo processo. Qui se ne da' la prova.")

    netta = bt.sottrai_pavimento(seq)
    argomenti = dict(soglia=0.10, quantile=0.90, n_boot=500,
                     colonna_erosione="erosione_netta")

    a = bt.bootstrap_soglia(netta, seme=12345, **argomenti)
    b = bt.bootstrap_soglia(netta, seme=12345, **argomenti)
    c = bt.bootstrap_soglia(netta, seme=999, **argomenti)
    mescolata = netta.sample(frac=1.0, random_state=7).reset_index(drop=True)
    d = bt.bootstrap_soglia(mescolata, seme=12345, **argomenti)
    e = bt.bootstrap_soglia(bt.sottrai_pavimento(par), seme=12345, **argomenti)

    def riga(nome: str, tab: pd.DataFrame) -> str:
        return (f"  {nome:32s} K* {tab['K_stella'][0]:7.2f}   "
                f"IC [{tab['K_inf'][0]:6.1f}, {tab['K_sup'][0]:6.1f}]")

    out("")
    out(riga("stesso seme, prima chiamata", a))
    out(riga("stesso seme, seconda chiamata", b))
    out(riga("seme diverso (999)", c))
    out(riga("righe mescolate, stesso seme", d))
    out(riga("tabella parallela, stesso seme", e))

    riproducibile = a.equals(b)
    invariante = a.equals(d) and a.equals(e)
    seme_conta = not a.equals(c)
    out(f"\nstesso seme -> stesso risultato          : {riproducibile}")
    out(f"ordine delle righe irrilevante           : {invariante}")
    out(f"seme diverso -> intervallo diverso       : {seme_conta}")

    esito = identiche and ordine and testo_ok and riproducibile and invariante and seme_conta
    out("\n" + "=" * 86)
    out("ESITO: " + ("VERIFICA SUPERATA" if esito else
                     "VERIFICA FALLITA — fermarsi e indagare prima di procedere"))
    out("=" * 86)
    return esito


def speedup(quanti: int, out) -> None:
    giorni = giorni_speedup(quanti)
    out("\n" + "=" * 86)
    out(f"SPEEDUP — {quanti} giorni consecutivi, {len(bt.GRIGLIA_CAPACITA_MW)} capacita'")
    out("=" * 86)
    out("La macchina ha 4 core fisici e 8 thread logici: oltre i 4 processi il guadagno")
    out("viene dal solo SMT ed e' molto minore di quanto suggerisca il conteggio dei thread.")
    out("")
    out("PRIMA di cronometrare si scalda la cache Parquet, leggendo una volta tutti i giorni.")
    out("Senza questo passaggio la misura e' priva di senso: la prima esecuzione paga ~15 s")
    out("per giorno di parsing dagli zip e le successive no, e il confronto attribuisce alla")
    out("parallelizzazione un guadagno che e' soltanto cache calda. E' un errore che si")
    out("riconosce dall'efficienza maggiore di uno, cioe' da uno speedup superlineare su")
    out("lavoro che superlineare non puo' essere.")
    t0 = time.perf_counter()
    for giorno in giorni:
        io_gme.carica_giorno(data=giorno, zona=None)
    out(f"cache scaldata in {time.perf_counter() - t0:.0f} s.")

    misure = []
    for nproc in (1, 2, 4, 6, 8):
        t0 = time.perf_counter()
        parallelo.erosioni_campione(giorni, processi=nproc)
        durata = time.perf_counter() - t0
        misure.append({"processi": nproc, "secondi": durata,
                       "s_per_giorno": durata / quanti})
        out(f"  {nproc} process{'o' if nproc == 1 else 'i'}: {durata:7.1f} s  "
            f"({durata / quanti:5.2f} s per giorno)", )

    t = pd.DataFrame(misure)
    base = float(t.loc[t["processi"] == 1, "secondi"].iloc[0])
    t["speedup"] = base / t["secondi"]
    t["efficienza"] = t["speedup"] / t["processi"]
    t["anno_2024_ore"] = t["s_per_giorno"] * 366 / 3600

    out("\n" + t.round(2).to_string(index=False))
    migliore = t.loc[t["secondi"].idxmin()]
    out(f"\nMigliore: {int(migliore['processi'])} processi, speedup "
        f"{migliore['speedup']:.2f}x, anno 2024 in {migliore['anno_2024_ore']:.2f} ore.")
    t.to_csv(config.TABLE_DIR / "11_speedup.csv", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--giorni", help="date AAAAMMGG separate da virgola")
    ap.add_argument("--processi", type=int, default=4,
                    help="processi da usare nel confronto (default 4, i core fisici)")
    ap.add_argument("--speedup", action="store_true",
                    help="misura anche lo speedup al variare del numero di processi")
    ap.add_argument("--giorni-speedup", type=int, default=16)
    args = ap.parse_args()

    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    giorni = args.giorni.split(",") if args.giorni else list(GIORNI_VERIFICA)
    esito = verifica(giorni, args.processi, out)
    if args.speedup:
        speedup(args.giorni_speedup, out)

    destinazione = config.TABLE_DIR / "11_verifica_parallelo.txt"
    destinazione.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"\nReport salvato in {destinazione}")
    sys.exit(0 if esito else 1)


if __name__ == "__main__":
    main()
