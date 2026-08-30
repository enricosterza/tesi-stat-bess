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


# ---------------------------------------------------------------------------
#  Profilo orario del prezzo di equilibrio: l'opportunita' di arbitraggio
# ---------------------------------------------------------------------------

MESI_IT: tuple[str, ...] = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

#: Due prezzi si considerano lo stesso estremo se distano meno di mezzo centesimo:
#: e' la risoluzione con cui il GME pubblica i prezzi zonali.
TOLLERANZA_ESTREMO: float = 0.005


def _it(valore: float, decimali: int = 1) -> str:
    """Formatta un numero con la virgola decimale, come vuole il testo italiano."""
    return f"{valore:,.{decimali}f}".replace(",", " ").replace(".", ",")


def data_estesa(data: str) -> str:
    """`'20250120'` -> `'20 gennaio 2025'`."""
    return f"{int(data[6:8])} {MESI_IT[int(data[4:6]) - 1]} {data[0:4]}"


def _intervalli(ore: list[int]) -> str:
    """
    Comprime una lista di ore in intervalli leggibili: `[9, 10, 18, 19, 20]` -> `'9-10, 18-20'`.

    Serve perche' il minimo o il massimo di giornata sono spesso raggiunti da piu' ore
    consecutive, quando la stessa unita' resta marginale. Segnalarlo evita che il lettore
    interpreti come un errore il fatto che il marcatore stia su una sola delle ore in cui
    la spezzata tocca il livello estremo.
    """
    blocchi, inizio, precedente = [], ore[0], ore[0]
    for ora in ore[1:]:
        if ora != precedente + 1:
            blocchi.append((inizio, precedente))
            inizio = ora
        precedente = ora
    blocchi.append((inizio, precedente))
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in blocchi)


def profilo_prezzi(
    profilo: pd.DataFrame,
    ax: plt.Axes,
    colonna: str = "prezzo",
    freccia: bool = True,
) -> dict:
    """
    Disegna il profilo orario del prezzo di equilibrio evidenziando minimo, massimo e spread.

    Parameters
    ----------
    profilo : pd.DataFrame
        Una riga per periodo, con le colonne `ora` (1-24) e quella indicata da `colonna`.
        Si assume il regime ORARIO: con 96 quarti d'ora marcatori ed etichette si
        sovrappongono e la figura va ripensata.
    ax : plt.Axes
        Assi su cui disegnare.
    colonna : str
        Colonna del prezzo da tracciare. Il default e' il prezzo ricostruito dal motore.
    freccia : bool
        Se True quota lo spread con una doppia freccia nel margine destro.

    Returns
    -------
    dict
        `minimo`, `massimo`, `spread`, `ora_minimo`, `ora_massimo` piu' quanto serve a
        `_annota_estremi` per scrivere le etichette.

    Le etichette NON vengono scritte qui: vanno aggiunte con `_annota_estremi` dopo che i
    limiti verticali sono fissati, perche' la scelta di metterle sopra o sotto il marcatore
    dipende dallo spazio effettivamente disponibile, che prima di `set_ylim` non si conosce.

    Perche' e' fatto cosi'
    ----------------------
    Il prezzo di un'asta oraria e' **costante dentro l'ora**: si disegna quindi a gradini
    (`steps-post`) e non con una spezzata che interpola i vertici, che suggerirebbe una
    transizione graduale inesistente. I marcatori cadono al centro dell'ora, cioe' dove il
    gradino e' effettivamente in vigore.

    Lo **spread** e' il messaggio della figura, non il livello dei prezzi: per questo la
    banda fra minimo e massimo e' campita e la distanza fra i due e' quotata da una freccia
    nel margine. La leggibilita' in bianco e nero e' ottenuta distinguendo i due estremi per
    **forma** (cerchio il minimo, triangolo il massimo) e non per colore soltanto.

    Attenzione a che cosa misura lo spread: e' il ricavo lordo per MWh ciclato di un
    accumulo perfettamente informato e di potenza trascurabile, cioe' un limite superiore
    dell'arbitraggio price taker. Non e' il profitto, che sconta rendimento di ciclo, costo
    variabile e vincolo di potenza (l'energia non si sposta tutta in una sola ora).
    """
    d = profilo.sort_values("ora")
    ore = d["ora"].to_numpy(dtype=float)
    p = d[colonna].to_numpy(dtype=float)

    i_min, i_max = int(np.nanargmin(p)), int(np.nanargmax(p))
    p_min, p_max = float(p[i_min]), float(p[i_max])

    # Piu' ore possono toccare lo stesso estremo: si annotano tutte, si marca la prima.
    ore_min = [int(o) for o, v in zip(ore, p) if abs(v - p_min) <= TOLLERANZA_ESTREMO]
    ore_max = [int(o) for o, v in zip(ore, p) if abs(v - p_max) <= TOLLERANZA_ESTREMO]

    # La banda quotata: e' lei il soggetto della figura.
    ax.axhspan(p_min, p_max, color=COLORE_OFFERTA, alpha=0.06, lw=0, zorder=0)
    for livello in (p_min, p_max):
        ax.axhline(livello, color=INCHIOSTRO_TENUE, linestyle=(0, (4, 3)),
                   linewidth=0.9, zorder=1)

    # Il gradino: l'ora k copre l'intervallo [k-1, k) sull'asse.
    x = np.concatenate([ore - 1.0, [ore[-1]]])
    y = np.concatenate([p, [p[-1]]])
    ax.step(x, y, where="post", color=COLORE_OFFERTA, linewidth=2.0, zorder=3)

    centri = ore - 0.5
    ax.plot(centri[i_max], p_max, marker="^", markersize=10, color=INCHIOSTRO,
            markeredgecolor=SFONDO, markeredgewidth=2.0, linestyle="none", zorder=5)
    ax.plot(centri[i_min], p_min, marker="o", markersize=9, color=INCHIOSTRO,
            markeredgecolor=SFONDO, markeredgewidth=2.0, linestyle="none", zorder=5)

    ax.set_xlim(0, 26.4 if freccia else 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("Ora")
    ax.grid(True, axis="y", linewidth=0.7)
    ax.set_axisbelow(True)
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)

    if freccia:
        x_freccia = 25.2
        ax.annotate("", xy=(x_freccia, p_max), xytext=(x_freccia, p_min),
                    annotation_clip=False,
                    arrowprops=dict(arrowstyle="<->", color=INCHIOSTRO_SECONDARIO,
                                    linewidth=1.3, shrinkA=0, shrinkB=0))
        ax.text(x_freccia + 0.45, (p_min + p_max) / 2,
                f"spread {_it(p_max - p_min)} €/MWh",
                rotation=90, ha="left", va="center", fontsize=9,
                color=INCHIOSTRO_SECONDARIO)

    return {
        "minimo": p_min, "massimo": p_max, "spread": p_max - p_min,
        "ora_minimo": float(ore_min[0]), "ora_massimo": float(ore_max[0]),
        "_ax": ax,
        "_ore": ore,
        "_prezzi": p,
        "_punto_min": (float(centri[i_min]), p_min),
        "_punto_max": (float(centri[i_max]), p_max),
        "_testo_min": f"minimo {_it(p_min)} €/MWh\nore {_intervalli(ore_min)}",
        "_testo_max": f"massimo {_it(p_max)} €/MWh\nore {_intervalli(ore_max)}",
    }


#: Ingombro stimato di un'etichetta a due righe, in punti-schermo. Non serve che sia
#: esatto: serve a scegliere fra tre posizioni, non a impaginare.
INGOMBRO_ETICHETTA_PX: tuple[float, float] = (118.0, 30.0)
DISTACCO_ETICHETTA_PX: float = 14.0


def _annota_estremi(esito: dict, quota_ore: float = 24.0) -> None:
    """
    Scrive le etichette di minimo e massimo nel punto piu' libero attorno al marcatore.

    Va chiamata **dopo** `set_ylim`, perche' la posizione dipende dallo spazio davvero
    disponibile, che prima non si conosce.

    Come sceglie
    ------------
    Prima il verso: sopra il marcatore per il massimo e sotto per il minimo, salvo che da
    quel lato manchi lo spazio (un minimo vicino allo zero), nel qual caso si ribalta.
    Poi l'ancoraggio orizzontale fra centrato, a destra e a sinistra: si stima l'ingombro
    del testo, si guarda quali ore ricadrebbero sotto di esso e si sceglie la posizione in
    cui la spezzata non attraversa il rettangolo del testo.

    E' una regola grossolana e va bene che lo sia: risolve automaticamente le collisioni
    che altrimenti si scoprono solo aprendo il PNG, e nei casi dubbi ricade sulla posizione
    centrata, che e' quella che si sceglierebbe a mano.
    """
    ax = esito["_ax"]
    basso, alto = ax.get_ylim()
    ore, prezzi = esito["_ore"], esito["_prezzi"]

    inversa = ax.transData.inverted()
    origine = inversa.transform((0.0, 0.0))
    ingombro = inversa.transform(INGOMBRO_ETICHETTA_PX)
    larghezza = abs(ingombro[0] - origine[0])
    altezza_testo = abs(ingombro[1] - origine[1])
    distacco = abs(inversa.transform((0.0, DISTACCO_ETICHETTA_PX))[1] - origine[1])

    for chiave, marcatore, verso in (("max", "_punto_max", +1), ("min", "_punto_min", -1)):
        x, y = esito[marcatore]

        # Verso: si ribalta solo se dal lato naturale non c'e' posto.
        margine = (alto - y) if verso > 0 else (y - basso)
        if margine < distacco + altezza_testo:
            verso = -verso
        va = "bottom" if verso > 0 else "top"

        # Fascia verticale che il testo occuperebbe.
        if verso > 0:
            fascia = (y + distacco, y + distacco + altezza_testo)
        else:
            fascia = (y - distacco - altezza_testo, y - distacco)

        # Il criterio: l'etichetta di un massimo dev'essere tutta sopra la spezzata, quella
        # di un minimo tutta sotto. Si misura di quanto la spezzata invade il rettangolo del
        # testo — in euro, non in numero di ore — e si sceglie l'ancoraggio meno invaso.
        candidati = {
            "center": (x - larghezza / 2, x + larghezza / 2, 0),
            "left":   (x, x + larghezza, 6),
            "right":  (x - larghezza, x, -6),
        }
        scala = max(alto - basso, 1e-9)
        ha, dx, migliore = "center", 0, None
        for nome, (da, a, scarto) in candidati.items():
            coperti = prezzi[(ore - 0.5 >= da) & (ore - 0.5 <= a)]
            if len(coperti) == 0:
                invasione = 0.0
            elif verso > 0:
                invasione = max(0.0, float(np.nanmax(coperti)) - fascia[0])
            else:
                invasione = max(0.0, fascia[1] - float(np.nanmin(coperti)))
            fuori = max(0.0, -da) + max(0.0, a - quota_ore)
            punteggio = invasione / scala + fuori
            if migliore is None or punteggio < migliore - 1e-9:
                migliore, ha, dx = punteggio, nome, scarto

        ax.annotate(esito[f"_testo_{chiave}"], xy=(x, y),
                    xytext=(dx, DISTACCO_ETICHETTA_PX * verso),
                    textcoords="offset points", ha=ha, va=va,
                    fontsize=9, color=INCHIOSTRO, linespacing=1.3, zorder=6)


def figura_profilo_prezzi(
    profilo: pd.DataFrame,
    data: str,
    zona: str = "NORD",
    colonna: str = "prezzo",
) -> plt.Figure:
    """Figura singola: il profilo orario di una giornata, con lo spread quotato."""
    _stile()
    figura, ax = plt.subplots(figsize=(8.2, 5.0))
    esito = profilo_prezzi(profilo, ax, colonna=colonna)
    ax.set_ylabel("Prezzo di equilibrio [€/MWh]")
    ax.set_title(f"Zona {zona} — {data_estesa(data)}\n"
                 f"spread infragiornaliero {_it(esito['spread'])} €/MWh")
    _respiro_verticale(ax, esito)
    _annota_estremi(esito)
    figura.tight_layout()
    return figura


def figura_profili_confronto(
    profili: dict[str, pd.DataFrame],
    zona: str = "NORD",
    colonna: str = "prezzo",
    scala_comune: bool = True,
) -> plt.Figure:
    """
    Due o piu' giornate affiancate, per default sulla **stessa scala verticale**.

    La scala comune e' una scelta di sostanza, non di stile: con assi indipendenti due
    spread di ampiezza diversa occupano la stessa altezza sulla pagina e il confronto
    visivo diventa ingannevole. Condividendo l'asse si leggono insieme l'ampiezza
    dell'oscillazione e il livello attorno a cui avviene, che sono due informazioni
    distinte ed entrambe utili.
    """
    _stile()
    figura, assi = plt.subplots(1, len(profili), figsize=(12.6, 5.2), sharey=scala_comune)
    assi = np.atleast_1d(assi)

    esiti = {}
    for ax, (data, profilo) in zip(assi, profili.items()):
        esiti[data] = profilo_prezzi(profilo, ax, colonna=colonna)
        ax.set_title(f"{data_estesa(data)}\nspread {_it(esiti[data]['spread'])} €/MWh")
    assi[0].set_ylabel("Prezzo di equilibrio [€/MWh]")

    if scala_comune:
        _respiro_verticale(assi[0], *esiti.values())
    else:
        for ax, esito in zip(assi, esiti.values()):
            _respiro_verticale(ax, esito)
    for esito in esiti.values():
        _annota_estremi(esito)

    figura.suptitle(f"Prezzo di equilibrio ricostruito, zona {zona}: "
                    f"ampiezza dell'oscillazione infragiornaliera", fontsize=11)
    figura.tight_layout()
    return figura


def _respiro_verticale(ax: plt.Axes, *esiti: dict) -> None:
    """
    Allarga l'asse verticale quel tanto che basta a non far uscire le etichette.

    Le annotazioni degli estremi stanno sopra e sotto i marcatori: senza margine finiscono
    tagliate dal bordo, e con `tight_layout` il taglio non si vede finche' non si guarda la
    figura salvata.

    Il margine inferiore **non** viene tagliato a zero. La tentazione sarebbe forte — nel
    campione non esistono prezzi di equilibrio negativi — ma un minimo vicino allo zero
    resterebbe senza spazio sotto e l'etichetta finirebbe ribaltata dentro la spezzata. Un
    asse che scende di qualche euro sotto lo zero non afferma che vi siano prezzi negativi:
    la linea dello zero resta visibile e sotto non c'e' alcun dato.
    """
    basso = min(e["minimo"] for e in esiti)
    alto = max(e["massimo"] for e in esiti)
    respiro = 0.20 * (alto - basso)
    ax.set_ylim(basso - respiro, alto + respiro)



def figura_distribuzione_errore(errore) -> plt.Figure:
    """
    La forma della distribuzione dell'errore, contro la gaussiana che il modello assume.

    Parameters
    ----------
    errore : array
        Errori di previsione, in EUR/MWh.

    Returns
    -------
    plt.Figure

    Due pannelli, perche' l'istogramma da solo inganna
    --------------------------------------------------
    Sull'istogramma una distribuzione a code spesse sembra semplicemente "un po' piu'
    appuntita": le code, essendo rare, sono invisibili proprio dove contano. Il diagramma
    quantile-quantile le rende leggibili, perche' mette sull'asse cio' che la gaussiana si
    aspetta e mostra di quanto la realta' se ne discosti agli estremi.

    La retta del pannello destro non e' una regressione ma la **bisettrice**: se l'errore
    fosse gaussiano i punti vi cadrebbero sopra. Lo scostamento agli estremi e' la misura
    visiva di quanto le code siano piu' spesse dell'assunzione.
    """
    from scipy import stats as _st

    errore = np.asarray(errore, dtype=float)
    sd = float(np.std(errore, ddof=1))
    _stile()
    figura, (sx, dx) = plt.subplots(1, 2, figsize=(12.4, 5.2))

    # ---- istogramma con la gaussiana di pari media e varianza
    sx.hist(errore, bins=120, density=True, color=COLORE_OFFERTA, alpha=0.55,
            edgecolor="none", label="errore osservato")
    griglia = np.linspace(errore.min(), errore.max(), 500)
    sx.plot(griglia, _st.norm.pdf(griglia, errore.mean(), sd), color=INCHIOSTRO,
            linewidth=2.0, linestyle="--", label="gaussiana di pari varianza")
    sx.set_xlabel("Errore [€/MWh]")
    sx.set_ylabel("Densità")
    sx.set_title(f"Curtosi in eccesso {_st.kurtosis(errore):+.2f}: più massa al centro\n"
                 "e nelle code, meno nelle spalle", fontsize=10.5)
    sx.legend(loc="upper left")
    sx.set_xlim(np.percentile(errore, 0.2), np.percentile(errore, 99.8))

    # ---- quantile-quantile
    teorici = _st.norm.ppf((np.arange(1, len(errore) + 1) - 0.5) / len(errore),
                           loc=errore.mean(), scale=sd)
    osservati = np.sort(errore)
    dx.plot(teorici, osservati, marker="o", markersize=1.6, linestyle="none",
            color=COLORE_OFFERTA, alpha=0.5)
    estremi = [min(teorici.min(), osservati.min()), max(teorici.max(), osservati.max())]
    dx.plot(estremi, estremi, color=INCHIOSTRO, linewidth=1.6, linestyle="--",
            label="se l'errore fosse gaussiano")
    dx.set_xlabel("Quantili attesi sotto la gaussiana [€/MWh]")
    dx.set_ylabel("Quantili osservati [€/MWh]")
    dx.set_title("Le code osservate escono dalla retta:\n"
                 "gli errori estremi sono molto più frequenti", fontsize=10.5)
    dx.legend(loc="upper left")

    for ax in (sx, dx):
        ax.grid(True, linewidth=0.7)
        ax.set_axisbelow(True)
        for lato in ("top", "right"):
            ax.spines[lato].set_visible(False)

    figura.tight_layout()
    return figura


def figura_errore_contro_spread(per_giorno: pd.DataFrame) -> plt.Figure:
    """
    L'errore giornaliero contro lo spread della giornata: l'errore morde dove si guadagna?

    Parameters
    ----------
    per_giorno : pd.DataFrame
        Una riga per giorno, con `rmse`, `spread_reale`, `spread_previsto`.

    Returns
    -------
    plt.Figure

    Perche' questa figura conta piu' di un coefficiente
    ---------------------------------------------------
    Lo spread giornaliero e' il ricavo lordo per MWh ciclato dell'arbitraggio: se l'errore
    di previsione cresce con lo spread, il modello sbaglia di piu' proprio nelle giornate
    che valgono di piu'. Il pannello di destra mostra la stessa cosa dal lato che alla
    batteria interessa davvero: quanto il modello sbaglia lo **spread**, non il livello.
    Sotto la bisettrice il modello lo sottostima, e sottostimarlo e' l'errore piu' costoso —
    porta a rinunciare a operare in giornate redditizie.
    """
    _stile()
    figura, (sx, dx) = plt.subplots(1, 2, figsize=(12.4, 5.2))

    sx.plot(per_giorno["spread_reale"], per_giorno["rmse"], marker="o", markersize=4,
            linestyle="none", color=COLORE_OFFERTA, alpha=0.55)
    coef = np.polyfit(per_giorno["spread_reale"], per_giorno["rmse"], 1)
    xs = np.linspace(per_giorno["spread_reale"].min(), per_giorno["spread_reale"].max(), 50)
    sx.plot(xs, np.polyval(coef, xs), color=INCHIOSTRO, linewidth=1.8, linestyle="--")
    r = float(np.corrcoef(per_giorno["spread_reale"], per_giorno["rmse"])[0, 1])
    sx.set_xlabel("Spread reale della giornata [€/MWh]")
    sx.set_ylabel("RMSE della giornata [€/MWh]")
    sx.set_title(f"L'errore cresce con lo spread (r = {r:+.2f}):\n"
                 "il modello sbaglia dove l'arbitraggio vale di più", fontsize=10.5)

    dx.plot(per_giorno["spread_reale"], per_giorno["spread_previsto"], marker="o",
            markersize=4, linestyle="none", color=COLORE_DOMANDA, alpha=0.55)
    lim = [0, max(per_giorno["spread_reale"].max(), per_giorno["spread_previsto"].max())]
    dx.plot(lim, lim, color=INCHIOSTRO, linewidth=1.6, linestyle="--",
            label="previsione esatta dello spread")
    sotto = float((per_giorno["spread_previsto"] < per_giorno["spread_reale"]).mean())
    dx.set_xlabel("Spread reale [€/MWh]")
    dx.set_ylabel("Spread previsto [€/MWh]")
    dx.set_title(f"Lo spread è sottostimato nel {100*sotto:.0f}% delle giornate\n"
                 "(punti sotto la bisettrice)", fontsize=10.5)
    dx.legend(loc="upper left")

    for ax in (sx, dx):
        ax.grid(True, linewidth=0.7)
        ax.set_axisbelow(True)
        for lato in ("top", "right"):
            ax.spines[lato].set_visible(False)

    figura.tight_layout()
    return figura


def figura_calibrazione(calibrazione: pd.DataFrame) -> plt.Figure:
    """
    Copertura osservata contro copertura nominale degli intervalli di previsione.

    Parameters
    ----------
    calibrazione : pd.DataFrame
        Colonne `nominale` e `copertura`, in frazione.

    Returns
    -------
    plt.Figure

    La bisettrice e' la calibrazione perfetta. Sopra, il modello e' **prudente**: dichiara
    piu' incertezza di quanta ne realizzi, e chi usasse i suoi intervalli per dimensionare
    un margine di rischio sovradimensionerebbe. Sotto, e' **sovra-sicuro**, che e' il verso
    pericoloso.
    """
    _stile()
    figura, ax = plt.subplots(figsize=(7.2, 5.6))

    x = calibrazione["nominale"].to_numpy(dtype=float) * 100
    y = calibrazione["copertura"].to_numpy(dtype=float) * 100
    ax.plot([40, 100], [40, 100], color=INCHIOSTRO, linewidth=1.6, linestyle="--",
            label="calibrazione perfetta")
    ax.plot(x, y, marker="o", markersize=8, linewidth=2.0, color=COLORE_OFFERTA,
            label="copertura osservata")
    for xi, yi in zip(x, y):
        ax.annotate(f"{yi:.1f}%", xy=(xi, yi), xytext=(0, 10),
                    textcoords="offset points", ha="center", fontsize=9, color=INCHIOSTRO)

    ax.set_xlabel("Livello nominale dell'intervallo [%]")
    ax.set_ylabel("Copertura osservata [%]")
    ax.set_title("Il modello dichiara più incertezza di quanta ne realizzi,\n"
                 "ma il margine si assottiglia ai livelli estremi", fontsize=11)
    ax.grid(True, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right")
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)

    figura.tight_layout()
    return figura




def figura_curva_erosione(
    curve: dict,
    soglie: tuple[float, ...] = (0.10, 0.20),
    soglie_k: dict | None = None,
) -> plt.Figure:
    """
    La curva erosione-capacita' nelle due varianti di piano, con le soglie e i K*.

    Parameters
    ----------
    curve : dict
        `{etichetta: DataFrame}` indicizzato per capacita', con le colonne `mediana` e `q90`
        dell'erosione **netta**.
    soglie : tuple[float, ...]
        Livelli di erosione da tracciare come riferimenti orizzontali.
    soglie_k : dict | None
        `{(etichetta, soglia): K}` da annotare sull'asse delle capacita'.

    Returns
    -------
    plt.Figure

    Perche' l'asse delle capacita' e' logaritmico
    ---------------------------------------------
    La griglia va da 1 MW a 6 GW, quattro ordini di grandezza, e la regione che decide —
    dove la curva attraversa il 10 e il 20 per cento — sta nelle prime centinaia di MW. Su
    scala lineare quella regione occuperebbe un ventesimo della larghezza e la figura
    mostrerebbe soprattutto il tratto di saturazione, che e' il meno informativo.

    Si tracciano **due** quantili e non uno. La mediana descrive la giornata tipica; il 90°
    percentile e' quello su cui K* e' definita (D-27), perche' la decisione di investimento
    dipende dal caso avverso ragionevole e non da quello medio. Vederli insieme mostra
    quanto siano distanti, cioe' quanto l'erosione vari fra le giornate.
    """
    _stile()
    figura, ax = plt.subplots(figsize=(9.6, 6.2))

    stili = {"perfetta": (INCHIOSTRO, "--"), "previsione": (COLORE_OFFERTA, "-")}
    nomi = {"perfetta": "previsione perfetta", "previsione": "previsione SARIMAX"}

    for etichetta, tabella in curve.items():
        colore, tratto = stili.get(etichetta, (COLORE_DOMANDA, "-."))
        ax.plot(tabella.index, tabella["q90"], color=colore, linestyle=tratto,
                linewidth=2.2, label=f"{nomi.get(etichetta, etichetta)} — 90° perc.")
        ax.plot(tabella.index, tabella["mediana"], color=colore, linestyle=tratto,
                linewidth=1.2, alpha=0.55,
                label=f"{nomi.get(etichetta, etichetta)} — mediana")

    for soglia in soglie:
        ax.axhline(soglia, color=INCHIOSTRO_TENUE, linewidth=0.9, linestyle=(0, (4, 3)))
        ax.annotate(f"{soglia:.0%}", xy=(1.05, soglia), xytext=(2, 3),
                    textcoords="offset points", fontsize=9, color=INCHIOSTRO_SECONDARIO)

    if soglie_k:
        for (etichetta, soglia), k in sorted(soglie_k.items(), key=lambda x: x[1]):
            if not np.isfinite(k):
                continue
            colore, _ = stili.get(etichetta, (COLORE_DOMANDA, "-."))
            ax.plot([k], [soglia], marker="o", markersize=8, color=colore,
                    markeredgecolor=SFONDO, markeredgewidth=2.0, linestyle="none", zorder=6)

    ax.set_xscale("log")
    ax.set_xlabel("Capacità aggregata installata [MW]")
    ax.set_ylabel("Erosione di profitto (netta del pavimento)")
    ax.set_ylim(0, 1.25)
    ax.set_title("La flotta che pianifica su previsioni erode di più,\n"
                 "e diventa price maker a una capacità inferiore", fontsize=11)
    ax.grid(True, which="major", linewidth=0.7)
    ax.grid(True, which="minor", linewidth=0.4, alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left")
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)

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


# ---------------------------------------------------------------------------
#  Errore di previsione: come si distribuisce lungo la giornata
# ---------------------------------------------------------------------------

def figura_errore_orario(per_ora: pd.DataFrame) -> plt.Figure:
    """
    L'errore di previsione ora per ora, accanto a cio' che lo spiega.

    Parameters
    ----------
    per_ora : pd.DataFrame
        Indicizzato per `slot` (0-23), con almeno `rmse`, `mae`, `se_dichiarato`,
        `prezzo_medio`, `dev_std_prezzo`.

    Returns
    -------
    plt.Figure

    Che cosa deve far vedere
    ------------------------
    Due fatti che una tabella non rende immediati.

    Il primo: l'errore **realizzato** non ha la stessa forma di quello **dichiarato** dal
    modello. L'errore standard di un SARIMA cresce in modo monotono con l'orizzonte, perche'
    e' cosi' che la teoria lo costruisce; quello vero segue invece l'ora del giorno. Le due
    curve del pannello superiore si incrociano, ed e' li' il risultato.

    Il secondo: cio' che l'errore segue e' la **variabilita'** del prezzo in quell'ora, non
    il suo livello. Il pannello inferiore mette le due grandezze una accanto all'altra
    perche' il lettore possa verificarlo con l'occhio invece che fidarsi del coefficiente
    di correlazione.
    """
    _stile()
    figura, (alto, mezzo, basso) = plt.subplots(
        3, 1, figsize=(9.5, 8.6), sharex=True, height_ratios=[3, 2, 2])

    ore = per_ora.index.to_numpy()
    alto.plot(ore, per_ora["rmse"], color=COLORE_OFFERTA, linewidth=2.2,
              marker="o", markersize=4, label="errore realizzato (RMSE)")
    alto.plot(ore, per_ora["mae"], color=COLORE_OFFERTA, linewidth=1.4,
              linestyle=(0, (1, 2)), label="errore realizzato (MAE)")
    alto.plot(ore, per_ora["se_dichiarato"], color=INCHIOSTRO, linewidth=2.0,
              linestyle="--", label="errore dichiarato dal modello")
    alto.set_ylabel("Errore [€/MWh]")
    alto.set_title("L'errore realizzato segue l'ora del giorno,\n"
                   "quello dichiarato dal modello segue solo l'orizzonte", fontsize=11)
    alto.legend(loc="lower right")

    # I due pannelli inferiori hanno scale molto diverse (decine contro centinaia) e vanno
    # tenuti separati: sovrapporli su un asse solo schiaccerebbe la variabilita' fino a
    # farla sembrare piatta, cioe' nasconderebbe proprio la grandezza che spiega l'errore.
    mezzo.plot(ore, per_ora["dev_std_prezzo"], color=COLORE_DOMANDA, linewidth=2.2,
               marker="s", markersize=4)
    mezzo.set_ylabel("Variabilità del\nprezzo [€/MWh]")

    basso.plot(ore, per_ora["prezzo_medio"], color=INCHIOSTRO_SECONDARIO, linewidth=2.0,
               linestyle="-.")
    basso.set_ylabel("Livello medio del\nprezzo [€/MWh]")
    basso.set_xlabel("Ora del giorno")

    for ax in (alto, mezzo, basso):
        ax.grid(True, linewidth=0.7)
        ax.set_axisbelow(True)
        ax.set_xticks(range(0, 24, 3))
        ax.set_xlim(-0.5, 23.5)
        for lato in ("top", "right"):
            ax.spines[lato].set_visible(False)

    figura.tight_layout()
    return figura
