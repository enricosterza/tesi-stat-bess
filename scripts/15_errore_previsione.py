"""
Caratterizzazione dell'errore di previsione: il pezzo statistico centrale della fase 1.

Non interessa quanto il modello sbagli in media — quello lo dice l'RMSE — ma **come** sbaglia:
in quali ore, se e' centrato, con che code, con che memoria, se l'ampiezza dipenda dal regime
di mercato, e se l'incertezza che il modello dichiara corrisponda a quella che realizza.
E' questa struttura che si propaga al piano della batteria e al risultato economico, e che un
indicatore aggregato nasconderebbe.

Sei dimensioni, sei sezioni
---------------------------
1. **Ora del giorno**: dove si concentra l'errore, e che cosa gli si puo' attribuire.
2. **Distorsione contro dispersione**: il modello e' centrato, o sbaglia sistematicamente?
3. **Code e forma**: sbaglia poco quasi sempre e molto in pochi giorni? E quei giorni sono
   proprio quelli a spread ampio, cioe' i piu' redditizi per l'arbitraggio?
4. **Autocorrelazione**: i residui sono bianchi o resta segnale non sfruttato?
5. **Eteroschedasticita'**: la varianza dipende dal livello del prezzo o dalla volatilita'
   della giornata?
6. **Calibrazione**: gli intervalli all'80, 90 e 95% contengono il prezzo nella proporzione
   attesa?

Esempio
-------
    .\\.venv\\Scripts\\python.exe scripts\\15_errore_previsione.py
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from mgp import config, grafici  # noqa: E402


def _sezione(out, titolo: str) -> None:
    out("\n" + "=" * 88)
    out(titolo)
    out("=" * 88)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--previsioni", default="previsioni_NORD_2024.csv")
    args = ap.parse_args()

    config.assicura_cartelle()
    buffer = io.StringIO()

    def out(testo: object = "") -> None:
        print(testo, flush=True)
        buffer.write(str(testo) + "\n")

    p = pd.read_csv(config.PROCESSED_DIR / args.previsioni, dtype={"data": str})
    p["istante"] = pd.to_datetime(p["istante"])
    p = p.sort_values("istante").reset_index(drop=True)
    e = p["errore"].to_numpy(dtype=float)
    sd = float(np.std(e, ddof=1))
    pd.set_option("display.width", 170)

    out("=" * 88)
    out(f"CARATTERIZZAZIONE DELL'ERRORE — {len(p):,} ore, {p['data'].nunique()} giorni")
    out("=" * 88)
    out("e(g,h) = prezzo reale meno prezzo previsto. Positivo = il modello ha sottostimato.")

    # ================================================================= 1. ora del giorno
    _sezione(out, "1. STRUTTURA PER ORA DEL GIORNO")
    out("Avvertenza di identificazione: l'origine della previsione e' sempre la fine di D-1,")
    out("quindi l'orizzonte h corrisponde SEMPRE all'ora h-1. Ora e orizzonte sono la stessa")
    out("variabile per costruzione e non sono separabili su questi dati. Si puo' pero'")
    out("escludere che sia un puro effetto di orizzonte, se lo schema non e' monotono.")
    out("")
    per_ora = p.groupby("slot").agg(
        prezzo_medio=("prezzo", "mean"),
        dev_std_prezzo=("prezzo", "std"),
        rmse=("errore", lambda s: float(np.sqrt(np.mean(s ** 2)))),
        mae=("errore", lambda s: float(np.mean(np.abs(s)))),
        bias=("errore", "mean"),
        copertura=("dentro_ic", "mean"),
        se_dichiarato=("errore_standard", "mean"))
    per_ora["rapporto"] = per_ora["rmse"] / per_ora["se_dichiarato"]
    out(per_ora.round(2).to_string())
    monotono = bool(np.all(np.diff(per_ora["rmse"].to_numpy()) >= 0))
    out(f"\n  RMSE monotono nell'orizzonte: {monotono}   "
        f"minimo ora {int(per_ora['rmse'].idxmin())} ({per_ora['rmse'].min():.2f}), "
        f"massimo ora {int(per_ora['rmse'].idxmax())} ({per_ora['rmse'].max():.2f})")
    out(f"  correlazione RMSE ~ VARIABILITA' del prezzo nell'ora: "
        f"{np.corrcoef(per_ora['rmse'], per_ora['dev_std_prezzo'])[0,1]:+.3f}")
    out(f"  correlazione RMSE ~ LIVELLO medio del prezzo nell'ora: "
        f"{np.corrcoef(per_ora['rmse'], per_ora['prezzo_medio'])[0,1]:+.3f}")
    out("  LETTURA: l'errore segue la variabilita' dell'ora, non il livello. La batteria")
    out("  pianifica la carica nel ventre pomeridiano, che e' l'ora peggio prevista.")

    # ============================================================ 2. distorsione/dispersione
    _sezione(out, "2. DISTORSIONE CONTRO DISPERSIONE")
    t = stats.ttest_1samp(e, 0.0)
    out(f"  media    {np.mean(e):8.4f}      mediana  {np.median(e):8.4f}")
    out(f"  RMSE     {np.sqrt(np.mean(e**2)):8.4f}      MAE      {np.mean(np.abs(e)):8.4f}")
    out(f"  dev.std  {sd:8.4f}")
    out(f"  test t su media nulla: t = {t.statistic:+.3f}, p = {t.pvalue:.3f}")
    out("")
    out("  Quantili dell'errore (EUR/MWh):")
    q = np.percentile(e, [1, 5, 10, 25, 50, 75, 90, 95, 99])
    out("    " + "  ".join(f"p{n}:{v:+7.2f}" for n, v in
                           zip([1, 5, 10, 25, 50, 75, 90, 95, 99], q)))
    out("")
    out("  Bias per ora del giorno (dove la distorsione si annida, se c'e'):")
    out("    " + "  ".join(f"{int(h):02d}:{v:+5.2f}" for h, v in per_ora["bias"].items()))
    out(f"    bias massimo in valore assoluto: {per_ora['bias'].abs().max():.2f} EUR/MWh, "
        f"contro una dispersione di {sd:.2f}")
    out("  LETTURA: il modello e' praticamente non distorto; tutto l'errore e' dispersione.")
    out("  Non c'e' una correzione sistematica da applicare: si puo' solo convivere con la")
    out("  varianza, ed e' questa che si propaghera' al piano.")

    # ======================================================================= 3. code e forma
    _sezione(out, "3. CODE E FORMA DELLA DISTRIBUZIONE")
    out(f"  asimmetria {stats.skew(e):+.4f}   curtosi in eccesso {stats.kurtosis(e):+.4f}"
        "   (0 = gaussiana)")
    jb = stats.jarque_bera(e)
    out(f"  Jarque-Bera: statistica {jb.statistic:,.0f}, p = {jb.pvalue:.3g}")
    out("")
    out("  Quota di ore oltre k deviazioni standard, contro l'attesa gaussiana:")
    out("     k   osservata   gaussiana   rapporto")
    for k in (1, 2, 3, 4, 5):
        oss = float(np.mean(np.abs(e) > k * sd))
        att = 2 * (1 - stats.norm.cdf(k))
        out(f"    {k}    {100*oss:7.3f}%   {100*att:7.3f}%   "
            f"{oss/att if att else float('nan'):8.1f}x")
    ordinati = np.sort(e ** 2)
    out(f"\n  L'1% peggiore delle ore porta il "
        f"{100 * ordinati[-(len(e)//100):].sum() / ordinati.sum():.1f}% della somma dei "
        f"quadrati; il 5% peggiore il "
        f"{100 * ordinati[-(len(e)//20):].sum() / ordinati.sum():.1f}%.")

    # il legame fra giornate a errore grande e giornate a spread ampio
    per_giorno = p.groupby("data").agg(
        rmse=("errore", lambda s: float(np.sqrt(np.mean(s ** 2)))),
        errore_medio=("errore", "mean"),
        prezzo_medio=("prezzo", "mean"),
        volatilita=("prezzo", "std"),
        spread_reale=("prezzo", lambda s: float(s.max() - s.min())),
        spread_previsto=("previsione", lambda s: float(s.max() - s.min())))
    per_giorno["errore_spread"] = per_giorno["spread_reale"] - per_giorno["spread_previsto"]

    out("\n  I GIORNI A ERRORE GRANDE SONO QUELLI A SPREAD AMPIO?")
    out("  E' la domanda che collega la fase 1 alla redditivita': lo spread e' il ricavo")
    out("  lordo dell'arbitraggio, quindi un errore che si concentra li' morde dove conta.")
    r_sp = stats.pearsonr(per_giorno["spread_reale"], per_giorno["rmse"])
    r_vo = stats.pearsonr(per_giorno["volatilita"], per_giorno["rmse"])
    r_li = stats.pearsonr(per_giorno["prezzo_medio"], per_giorno["rmse"])
    out(f"    correlazione RMSE giornaliero ~ spread reale del giorno : "
        f"{r_sp.statistic:+.3f} (p = {r_sp.pvalue:.2e})")
    out(f"    correlazione RMSE giornaliero ~ volatilita' del giorno  : "
        f"{r_vo.statistic:+.3f} (p = {r_vo.pvalue:.2e})")
    out(f"    correlazione RMSE giornaliero ~ livello medio del giorno: "
        f"{r_li.statistic:+.3f} (p = {r_li.pvalue:.2e})")
    quintili = pd.qcut(per_giorno["spread_reale"], 5, labels=False)
    tab = per_giorno.groupby(quintili).agg(
        spread_min=("spread_reale", "min"), spread_max=("spread_reale", "max"),
        rmse_medio=("rmse", "mean"), errore_spread=("errore_spread", "mean"), n=("rmse", "size"))
    out("\n    Per quintile di spread giornaliero:")
    out("    " + tab.round(2).to_string().replace("\n", "\n    "))
    out("  LETTURA: se il RMSE cresce con lo spread, l'errore e' massimo proprio nelle")
    out("  giornate in cui l'arbitraggio vale di piu'. La colonna `errore_spread` dice")
    out("  inoltre se il modello SOTTOSTIMA lo spread, che e' l'errore piu' dannoso: porta")
    out("  la batteria a rinunciare a operare in giornate che sarebbero redditizie.")

    # ================================================================= 4. autocorrelazione
    _sezione(out, "4. AUTOCORRELAZIONE DEI RESIDUI")
    from statsmodels.tsa.stattools import acf, pacf
    from statsmodels.stats.diagnostic import acorr_ljungbox
    a = acf(e, nlags=200, fft=True)
    pa = pacf(e, nlags=50, method="ywm")
    banda = 1.96 / np.sqrt(len(e))
    out(f"  banda di non significativita': +/- {banda:.4f}\n")
    out("  lag      ACF      PACF   significativa")
    for lag in (1, 2, 3, 6, 12, 23, 24, 25, 48, 72, 168):
        pv = f"{pa[lag]:+8.4f}" if lag < len(pa) else "       -"
        out(f"  {lag:4d}  {a[lag]:+8.4f}  {pv}   {'si' if abs(a[lag]) > banda else 'no'}")
    lb = acorr_ljungbox(e, lags=[24, 48, 168], return_df=True)
    out("\n  Ljung-Box:")
    out("    " + lb.round(4).to_string().replace("\n", "\n    "))
    a_g = acf(per_giorno["errore_medio"].to_numpy(), nlags=10, fft=True)
    banda_g = 1.96 / np.sqrt(len(per_giorno))
    out(f"\n  ACF dell'errore MEDIO GIORNALIERO (banda +/- {banda_g:.3f}): "
        f"lag1 {a_g[1]:+.3f}  lag2 {a_g[2]:+.3f}  lag7 {a_g[7]:+.3f}")
    if abs(a_g[1]) <= banda_g:
        out("  LETTURA: forte memoria DENTRO la giornata, nessuna FRA giornate. E' il verso")
        out("  peggiore per il piano: un errore coerente per l'intera giornata sbaglia")
        out("  l'ORDINAMENTO delle ore, mentre errori indipendenti si compenserebbero.")
    else:
        out("  LETTURA: le giornate difficili si presentano a grappoli.")

    # ================================================================ 5. eteroschedasticita'
    _sezione(out, "5. ETEROSCHEDASTICITA'")
    out("I decili si costruiscono sul prezzo PREVISTO, non su quello realizzato: raggruppare")
    out("per il realizzato e' contaminato per costruzione, perche' nel gruppo dei prezzi alti")
    out("finiscono per definizione le ore con errore positivo. Si misurerebbe la regressione")
    out("verso la media, non l'eteroschedasticita'.")
    out("")
    p["decile"] = pd.qcut(p["previsione"], 10, labels=False, duplicates="drop")
    per_decile = p.groupby("decile").agg(
        previsto_min=("previsione", "min"), previsto_max=("previsione", "max"),
        rmse=("errore", lambda s: float(np.sqrt(np.mean(s ** 2)))),
        bias=("errore", "mean"), n=("errore", "size"))
    out(per_decile.round(2).to_string())
    rho = stats.spearmanr(p["previsione"], np.abs(p["errore"]))
    basso = float(per_decile["rmse"].iloc[0])
    alto = float(per_decile["rmse"].iloc[-1])
    centro = float(per_decile["rmse"].iloc[3:7].mean())
    out(f"\n  correlazione di rango prezzo previsto ~ |errore|: rho = {rho.statistic:+.3f} "
        f"(p = {rho.pvalue:.2e})")
    out(f"  RMSE: decile piu' basso {basso:.2f}, centrali {centro:.2f}, piu' alto {alto:.2f}")
    if basso > 1.25 * centro and alto > 1.25 * centro:
        out("  Andamento a U: errore grande a ENTRAMBI gli estremi, piccolo al centro. Una")
        out("  correlazione di rango non lo rivela, perche' cerca monotonia: qui la tabella")
        out("  dice piu' del coefficiente.")
    contaminata = (p.assign(d=pd.qcut(p["prezzo"], 10, labels=False, duplicates="drop"))
                    .groupby("d")["errore"].mean())
    out(f"\n  Per confronto, raggruppando per prezzo REALIZZATO: bias da "
        f"{contaminata.iloc[0]:+.2f} a {contaminata.iloc[-1]:+.2f} EUR/MWh — in larga parte")
    out("  artefatto del raggruppamento, ed e' la ragione per cui si usa il previsto.")

    out("\n  Per quintile di VOLATILITA' della giornata:")
    qv = pd.qcut(per_giorno["volatilita"], 5, labels=False)
    tabv = per_giorno.groupby(qv).agg(
        volat_min=("volatilita", "min"), volat_max=("volatilita", "max"),
        rmse_medio=("rmse", "mean"), n=("rmse", "size"))
    out("  " + tabv.round(2).to_string().replace("\n", "\n  "))
    out("  LETTURA: se il RMSE cresce con la volatilita' del giorno, l'errore di previsione")
    out("  e' legato al REGIME di mercato, ed e' l'anello che collega la fase 1 alla")
    out("  domanda della tesi: i regimi volatili sono quelli in cui l'accumulo guadagna.")

    # ==================================================================== 6. calibrazione
    _sezione(out, "6. CALIBRAZIONE DEGLI INTERVALLI DI PREVISIONE")
    out("Gli intervalli si ricostruiscono dall'errore standard, che e' salvato ora per ora:")
    out("il SARIMAX li costruisce gaussiani, quindi l'estremo e' previsione +/- z * se.")
    out("")
    out("  livello   copertura   ampiezza mediana   giudizio")
    righe_cal = []
    for livello in (0.50, 0.80, 0.90, 0.95, 0.99):
        z = stats.norm.ppf(0.5 + livello / 2)
        dentro = (np.abs(e) <= z * p["errore_standard"].to_numpy())
        cop = float(dentro.mean())
        ampiezza = float(np.median(2 * z * p["errore_standard"]))
        scarto = cop - livello
        giudizio = ("troppo largo" if scarto > 0.02 else
                    "troppo stretto" if scarto < -0.02 else "calibrato")
        righe_cal.append({"nominale": livello, "copertura": cop, "ampiezza": ampiezza,
                          "scarto": scarto})
        out(f"    {100*livello:4.0f}%    {100*cop:7.1f}%   {ampiezza:14.2f}   {giudizio}")
    cal = pd.DataFrame(righe_cal)
    out(f"\n  errore standard medio DICHIARATO  : {p['errore_standard'].mean():7.2f} EUR/MWh")
    out(f"  errore quadratico medio REALIZZATO: {np.sqrt(np.mean(e**2)):7.2f} EUR/MWh")
    out(f"  rapporto realizzato/dichiarato    : "
        f"{np.sqrt(np.mean(e**2)) / p['errore_standard'].mean():7.3f}")
    out("\n  Copertura al 90% per ora del giorno (nominale 90%):")
    out("  " + "  ".join(f"{int(h):02d}:{100*v:5.1f}"
                         for h, v in per_ora["copertura"].items()))
    out("  LETTURA: se la copertura e' buona ai livelli centrali ma cede a quelli estremi,")
    out("  il difetto non e' l'ampiezza ma la FORMA: code gaussiane su un errore che non lo")
    out("  e'. E' la stessa cosa vista alla dimensione 3, letta dal lato dell'incertezza")
    out("  dichiarata.")

    # ========================================================================== le figure
    figure = []
    figure.append(grafici.salva(grafici.figura_errore_orario(per_ora), "15_errore_orario"))
    figure.append(grafici.salva(grafici.figura_distribuzione_errore(e), "15_errore_forma"))
    figure.append(grafici.salva(
        grafici.figura_errore_contro_spread(per_giorno), "15_errore_spread"))
    figure.append(grafici.salva(grafici.figura_calibrazione(cal), "15_calibrazione"))

    per_ora.to_csv(config.TABLE_DIR / "15_errore_per_ora.csv")
    per_decile.to_csv(config.TABLE_DIR / "15_errore_per_decile.csv")
    per_giorno.to_csv(config.TABLE_DIR / "15_errore_per_giorno.csv")
    cal.to_csv(config.TABLE_DIR / "15_calibrazione.csv", index=False)
    destinazione = config.TABLE_DIR / "15_errore_previsione.txt"
    destinazione.write_text(buffer.getvalue(), encoding="utf-8")
    print("\nFigure:")
    for f in figure:
        print(f"  {f}")
    print(f"Report salvato in {destinazione}")


if __name__ == "__main__":
    main()
