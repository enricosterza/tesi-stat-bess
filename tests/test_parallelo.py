"""
Test della griglia di capacita' e delle garanzie su cui poggia la parallelizzazione.

Che cosa si testa qui e che cosa no
-----------------------------------
La non regressione «stessi giorni, stessi numeri in sequenza e in parallelo» ha bisogno dei
dati reali e di alcuni minuti di calcolo: sta in `scripts/11_verifica_parallelo.py`, che va
rieseguito ogni volta che si tocca `mgp.parallelo` o `mgp.batteria`.

Qui si testano le proprieta' che si possono verificare su casi giocattolo e che, se si
rompessero, produrrebbero risultati **plausibili ma sbagliati**: la forma della griglia, e
soprattutto le due garanzie da cui dipende la riproducibilita' del bootstrap in esecuzione
parallela — che lo stesso seme dia lo stesso risultato, e che l'ordine delle righe in
ingresso non lo tocchi.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import pytest

from mgp import batteria as bt
from mgp import parallelo


class TestGrigliaCapacita:
    def test_numero_di_punti(self):
        assert len(bt.GRIGLIA_CAPACITA_MW) == 132

    def test_crescente_e_senza_ripetizioni(self):
        g = bt.GRIGLIA_CAPACITA_MW
        assert all(b > a for a, b in zip(g, g[1:]))

    def test_estremi(self):
        # Il minimo NON va abbassato sotto 1 MW: `sottrai_pavimento` usa la capacita' piu'
        # piccola come riferimento di effetto nullo, e cambiarla ridefinirebbe il pavimento
        # (D-30) rendendo i risultati non confrontabili con quelli gia' prodotti.
        assert bt.GRIGLIA_CAPACITA_MW[0] == 1.0
        assert bt.GRIGLIA_CAPACITA_MW[-1] == 6000.0

    def test_passo_unitario_nella_regione_del_pavimento(self):
        fondo = [k for k in bt.GRIGLIA_CAPACITA_MW if k <= 20]
        assert fondo == [float(x) for x in range(1, 21)]

    def test_passo_di_dieci_nella_regione_della_soglia(self):
        # Dove cadono le soglie al 5, 10 e 20 per cento: e' li' che serve risoluzione.
        soglia = [k for k in bt.GRIGLIA_CAPACITA_MW if 30 <= k <= 400]
        assert soglia == [float(x) for x in range(30, 401, 10)]

    def test_arriva_oltre_la_saturazione(self):
        # Il 100% di erosione viene attraversato attorno ai 1600 MW sul 90esimo percentile
        # e ai 2450 sulla mediana: la griglia deve andare ben oltre entrambi.
        assert max(bt.GRIGLIA_CAPACITA_MW) >= 5000

    def test_la_funzione_e_la_costante_coincidono(self):
        assert bt.griglia_capacita() == bt.GRIGLIA_CAPACITA_MW


def _tabella_finta(n_giorni: int = 40, semelocale: int = 3) -> pd.DataFrame:
    """
    Tabella giorno x capacita' con erosione crescente nella capacita', come la vera.

    Non serve che i numeri siano realistici: servono la forma e la crescita, perche' e'
    su quelle che `bootstrap_soglia` lavora.
    """
    rng = np.random.default_rng(semelocale)
    griglia = [1.0, 25.0, 50.0, 100.0, 200.0, 400.0, 800.0]
    righe = []
    for i in range(n_giorni):
        pendenza = 0.0004 * (1 + rng.random())
        for k in griglia:
            righe.append({"data": f"2024{(i // 28) + 1:02d}{(i % 28) + 1:02d}",
                          "potenza_mw": k,
                          "erosione_relativa": float(pendenza * k + 0.01 * rng.random())})
    return pd.DataFrame(righe)


class TestRiproducibilitaBootstrap:
    """
    Le due garanzie da cui dipende la replicabilita' della tesi in esecuzione parallela.

    Il parallelismo sta interamente a monte del generatore casuale: i lavoratori calcolano
    una tabella deterministica e non estraggono nulla. Restano da garantire che il bootstrap
    sia riproducibile a parita' di seme, e che non veda l'ordine delle righe — perche' e'
    l'ordine la sola cosa che un'esecuzione parallela potrebbe cambiare.
    """

    ARGOMENTI = dict(soglia=0.10, quantile=0.90, n_boot=200)

    def test_stesso_seme_stesso_risultato(self):
        t = _tabella_finta()
        a = bt.bootstrap_soglia(t, seme=12345, **self.ARGOMENTI)
        b = bt.bootstrap_soglia(t, seme=12345, **self.ARGOMENTI)
        assert a.equals(b)

    def test_seme_diverso_intervallo_diverso(self):
        # Se questo test passasse per caso anche con semi diversi, il seme non starebbe
        # facendo il suo lavoro e i due precedenti non proverebbero nulla.
        t = _tabella_finta()
        a = bt.bootstrap_soglia(t, seme=12345, **self.ARGOMENTI)
        c = bt.bootstrap_soglia(t, seme=999, **self.ARGOMENTI)
        assert not a.equals(c)

    def test_ordine_delle_righe_irrilevante(self):
        t = _tabella_finta()
        mescolata = t.sample(frac=1.0, random_state=7).reset_index(drop=True)
        a = bt.bootstrap_soglia(t, seme=12345, **self.ARGOMENTI)
        d = bt.bootstrap_soglia(mescolata, seme=12345, **self.ARGOMENTI)
        assert a.equals(d)

    def test_stima_puntuale_invariante_all_ordine(self):
        t = _tabella_finta()
        mescolata = t.sample(frac=1.0, random_state=11).reset_index(drop=True)
        assert bt.bootstrap_soglia(t, seme=1, **self.ARGOMENTI)["K_stella"][0] == \
               pytest.approx(
                   bt.bootstrap_soglia(mescolata, seme=1, **self.ARGOMENTI)["K_stella"][0])


class TestRunner:
    def test_campione_vuoto(self):
        assert parallelo.erosioni_campione([]).empty

    def test_stagioni_coprono_i_dodici_mesi(self):
        assert sorted(parallelo.STAGIONI) == list(range(1, 13))
        assert set(parallelo.STAGIONI.values()) == {"inverno", "primavera", "estate", "autunno"}

    def test_erosioni_giorno_e_esposta(self):
        # Lo script 06 e il runner parallelo devono chiamare la stessa identica funzione:
        # se si duplicasse, le due strade potrebbero divergere senza che nessuno se ne accorga.
        assert callable(parallelo.erosioni_giorno)
