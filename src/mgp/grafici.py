"""
Grafici delle curve d'asta e dei risultati.

Perche' esiste questo modulo
----------------------------
I numeri della ricostruzione dicono che il modello riproduce il prezzo, ma non dicono
**perche'** l'accumulo abbia l'effetto che ha. Quello dipende dalla forma delle curve nei
periodi in cui la batteria opera — l'ora di minimo e quella di massimo prezzo — e la forma si
guarda, non si riassume. Questi grafici servono a controllare che la pendenza attorno
all'equilibrio sia economicamente sensata e non l'artefatto di poche offerte isolate.

Scelte grafiche
---------------
Due sole serie, offerta e domanda, distinte **sia per colore sia per tratto**: il tratto
serve perche' la tesi si stampa, spesso in bianco e nero, e l'identita' non deve dipendere
dal solo colore. Griglia e assi sono volutamente poco marcati, cosi' l'occhio va sulle curve.
I colori vengono dalla palette di riferimento validata per fondo chiaro.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")          # nessuna finestra: si salva su file
import matplotlib.pyplot as plt  # noqa: E402

from . import config, curve  # noqa: E402

#: Palette di riferimento, fondo chiaro. Slot 1 e 2 della scala categoriale.
COLORE_OFFERTA = "#2a78d6"
COLORE_DOMANDA = "#eb6834"
COLORE_EQUILIBRIO = "#0b0b0b"
COLORE_UFFICIALE = "#008300"
INCHIOSTRO = "#0b0b0b"
INCHIOSTRO_SECONDARIO = "#52514e"
INCHIOSTRO_TENUE = "#898781"
GRIGLIA = "#e1e0d9"
SFONDO = "#fcfcfb"


def _stile() -> None:
    """Impostazioni comuni: testo leggibile in stampa, cromature poco invadenti."""
    plt.rcParams.update({
        "figure.facecolor": SFONDO,
        "axes.facecolor": SFONDO,
        "axes.edgecolor": INCHIOSTRO_TENUE,
        "axes.labelcolor": INCHIOSTRO_SECONDARIO,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.color": INCHIOSTRO_TENUE,
        "ytick.color": INCHIOSTRO_TENUE,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "grid.color": GRIGLIA,
        "grid.linewidth": 0.7,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "font.size": 10,
    })


def _scalini(prezzi: np.ndarray, quantita: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Trasforma una curva cumulata in una spezzata a gradini da disegnare.

    La curva d'asta e' una funzione a gradini della quantita': fra la quantita' cumulata
    precedente e quella corrente il prezzo marginale resta costante. Si disegna quindi con
    segmenti orizzontali raccordati da salti verticali, non con una linea che interpola i
    vertici — quella suggerirebbe una gradualita' che non esiste.
    """
    x = np.concatenate([[0.0], np.asarray(quantita, dtype=float)])
    y = np.concatenate([np.asarray(prezzi, dtype=float), [prezzi[-1]]])
    return x, y


def curve_periodo(
    offerte: pd.DataFrame,
    ax: plt.Axes,
    prezzo_ufficiale: float | None = None,
    zoom: bool = False,
    margine_quantita: float = 0.15,
    margine_prezzo: float = 60.0,
    titolo: str = "",
) -> dict:
    """
    Disegna le curve aggregate di domanda e offerta di una singola asta.

    Parameters
    ----------
    offerte : pd.DataFrame
        Offerte dell'asta, blocco di scambio incluso.
    ax : matplotlib.axes.Axes
        Assi su cui disegnare.
    prezzo_ufficiale : float | None
        Se indicato, viene tracciato come riferimento orizzontale.
    zoom : bool
        Se True, la vista si restringe attorno al punto di equilibrio, dove si legge la
        pendenza che determina l'effetto di una batteria.
    margine_quantita : float
        Semiampiezza della finestra di zoom sull'asse delle quantita', in quota della
        quantita' di equilibrio.
    margine_prezzo : float
        Semiampiezza della finestra di zoom sull'asse dei prezzi, in €/MWh.
    titolo : str

    Returns
    -------
    dict
        Diagnostica della vista: prezzo e quantita' di equilibrio, e numero di gradini di
        offerta compresi nella finestra di zoom — che e' il controllo chiave, perche' una
        pendenza sostenuta da pochissimi gradini sarebbe fragile.
    """
    _stile()
    offerta = curve.curva_offerta(offerte)
    domanda = curve.curva_domanda(offerte)
    eq = curve.prezzo_equilibrio(offerte)

    x_off, y_off = _scalini(offerta["prezzo"].to_numpy(), offerta["quantita_cumulata"].to_numpy())
    x_dom, y_dom = _scalini(domanda["prezzo"].to_numpy(), domanda["quantita_cumulata"].to_numpy())

    ax.step(x_off, y_off, where="post", color=COLORE_OFFERTA, linewidth=1.8,
            label="Offerta (vendita)")
    ax.step(x_dom, y_dom, where="post", color=COLORE_DOMANDA, linewidth=1.8,
            linestyle="--", label="Domanda (acquisto)")

    diagnostica = {"prezzo": eq.prezzo, "quantita": eq.quantita, "gradini_nello_zoom": np.nan}

    if eq.prezzo is not None:
        ax.plot([eq.quantita], [eq.prezzo], marker="o", markersize=6,
                color=COLORE_EQUILIBRIO, zorder=5, linestyle="none",
                label=f"Equilibrio: {eq.prezzo:.2f} €/MWh")
    if prezzo_ufficiale is not None and np.isfinite(prezzo_ufficiale):
        ax.axhline(prezzo_ufficiale, color=COLORE_UFFICIALE, linewidth=1.2, linestyle=":",
                   label=f"Prezzo ufficiale: {prezzo_ufficiale:.2f} €/MWh")

    if zoom and eq.prezzo is not None and eq.quantita:
        q0, q1 = eq.quantita * (1 - margine_quantita), eq.quantita * (1 + margine_quantita)
        ax.set_xlim(q0, q1)
        ax.set_ylim(eq.prezzo - margine_prezzo, eq.prezzo + margine_prezzo)
        dentro = offerta[(offerta["quantita_cumulata"] >= q0)
                         & (offerta["quantita_cumulata"] <= q1)]
        diagnostica["gradini_nello_zoom"] = int(len(dentro))
        # I singoli gradini vanno resi visibili: se la pendenza poggiasse su due o tre
        # offerte isolate, il grafico deve mostrarlo.
        ax.plot(dentro["quantita_cumulata"], dentro["prezzo"], linestyle="none",
                marker="o", markersize=3, color=COLORE_OFFERTA, alpha=0.55)

    ax.set_xlabel("Quantità cumulata (MW)")
    ax.set_ylabel("Prezzo (€/MWh)")
    ax.grid(True, linewidth=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)
    if titolo:
        ax.set_title(titolo, color=INCHIOSTRO, loc="left")
    return diagnostica


def figura_giornata(
    df: pd.DataFrame,
    data: str,
    granularita: str,
    periodo_minimo: int,
    periodo_massimo: int,
    zone: list[str] | str | None = None,
    prezzi_ufficiali: dict[int, float] | None = None,
) -> tuple[plt.Figure, pd.DataFrame]:
    """
    Compone la figura di controllo di una giornata: ora di minimo e ora di picco.

    Per ciascuno dei due periodi si disegnano la vista completa, che mostra i blocchi price
    taker agli estremi di prezzo, e lo zoom attorno all'equilibrio, che e' dove si legge la
    pendenza rilevante per l'effetto della batteria.

    Returns
    -------
    (figura, diagnostica) : tuple
        La figura e una tabella con prezzo, quantita' e numero di gradini nello zoom.
    """
    _stile()
    offerte_giorno = curve.offerte_giornata(df, granularita, zone=zone, con_import=True)
    prezzi_ufficiali = prezzi_ufficiali or {}

    figura, assi = plt.subplots(2, 2, figsize=(12, 8.5))
    righe = []
    for riga, (periodo, etichetta) in enumerate(
        [(periodo_minimo, "minimo di prezzo"), (periodo_massimo, "picco di prezzo")]
    ):
        offerte = offerte_giorno[int(periodo)]
        for colonna, zoom in enumerate([False, True]):
            vista = "vista completa" if not zoom else "ingrandimento sull'equilibrio"
            diagnostica = curve_periodo(
                offerte, assi[riga][colonna],
                prezzo_ufficiale=prezzi_ufficiali.get(int(periodo)),
                zoom=zoom,
                titolo=f"{data} · periodo {periodo} ({etichetta}) · {vista}",
            )
            if zoom:
                diagnostica.update({"data": data, "PERIOD": periodo, "tipo": etichetta})
                righe.append(diagnostica)
        assi[riga][0].legend(loc="upper left")

    figura.tight_layout()
    return figura, pd.DataFrame(righe)


def curva_impatto(
    offerte_per_periodo: dict[int, pd.DataFrame],
    griglia_mw: np.ndarray | list[float],
    granularita: str,
    etichette: dict[int, str] | None = None,
    in_energia: bool = False,
    titolo: str | None = None,
) -> plt.Figure:
    """
    Disegna la curva di impatto marginale DeltaPrezzo = f(DeltaQuantita') di uno o piu'
    periodi, con l'origine sul punto di clearing reale di ciascuno.

    Parameters
    ----------
    offerte_per_periodo : dict[int, pd.DataFrame]
        Offerte di ciascun periodo da rappresentare, blocco di scambio gia' incluso.
        Tipicamente due: l'ora di minimo e quella di picco.
    griglia_mw : array
        Quantita' con segno, in MW. Positive = accumulo che scarica (offerta addizionale),
        negative = accumulo che carica (domanda addizionale).
    granularita : str
        Serve a convertire in energia e a etichettare l'asse.
    etichette : dict[int, str] | None
        Nome descrittivo di ciascun periodo (es. "ora di minimo").
    in_energia : bool
        Se True l'asse delle ascisse e' in MWh anziche' in MW.
    titolo : str | None

    Returns
    -------
    plt.Figure

    Come si legge
    -------------
    Il quadrante di **destra** (delta positivo) e' l'accumulo che scarica: aggiunge offerta e
    abbassa il prezzo, quindi la curva scende. Quello di **sinistra** e' l'accumulo che
    carica: aggiunge domanda e alza il prezzo. La pendenza attorno all'origine e' l'elasticita'
    locale del periodo; i tratti piatti sono i gradini larghi, dove l'accumulo passa
    inosservato, e i salti sono i bordi fra un gradino e il successivo.

    Le due curve insieme mostrano l'asimmetria fra carica e scarica, che e' la ragione per cui
    l'erosione non si puo' dedurre da un solo numero di elasticita'.

    Nota sull'asse in energia
    -------------------------
    Con `in_energia=True` le ascisse valgono `MW * durata del periodo`: su PT15 un MW vale
    0,25 MWh. Le due scale coincidono **solo** sulle aste orarie, e per questo l'asse porta
    sempre l'unita' esplicita.
    """
    _stile()
    griglia = np.asarray(griglia_mw, dtype=float)
    etichette = etichette or {}
    colori = [COLORE_OFFERTA, COLORE_DOMANDA, "#7d3fb8", "#008300"]
    tratti = ["-", "--", "-.", ":"]

    figura, ax = plt.subplots(figsize=(7.5, 4.6))
    for i, (periodo, offerte) in enumerate(sorted(offerte_per_periodo.items())):
        dati = curve.curva_impatto(offerte, griglia, granularita=granularita)
        x = dati["delta_mwh"] if in_energia else dati["delta_mw"]
        nome = etichette.get(periodo, f"periodo {periodo}")
        ax.plot(x, dati["variazione"], color=colori[i % len(colori)],
                linestyle=tratti[i % len(tratti)], linewidth=2.0,
                label=f"{nome} (periodo {periodo})")

    # L'origine e' il clearing osservato: si marca, perche' e' il riferimento di lettura.
    ax.axhline(0.0, color=INCHIOSTRO_TENUE, linewidth=0.9)
    ax.axvline(0.0, color=INCHIOSTRO_TENUE, linewidth=0.9)

    unita = "MWh" if in_energia else "MW"
    ax.set_xlabel(f"Quantita' aggiunta [{unita}]   "
                  f"(< 0: l'accumulo carica   ·   > 0: l'accumulo scarica)")
    ax.set_ylabel("Variazione del prezzo [€/MWh]")
    ax.set_title(titolo or "Impatto marginale sul prezzo, origine sul clearing osservato")
    ax.grid(True, linewidth=0.7)
    ax.set_axisbelow(True)
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)
    ax.legend(loc="best")

    figura.tight_layout()
    return figura


def salva(figura: plt.Figure, nome: str) -> str:
    """Salva una figura in `output/figure/` in PNG e PDF, e restituisce il path del PNG."""
    config.assicura_cartelle()
    png = config.FIGURE_DIR / f"{nome}.png"
    figura.savefig(png, dpi=160, bbox_inches="tight")
    figura.savefig(config.FIGURE_DIR / f"{nome}.pdf", bbox_inches="tight")
    plt.close(figura)
    return str(png)
