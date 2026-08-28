"""
Test delle funzioni di supporto ai grafici.

Del disegno in se' non si fa test automatico: una figura si giudica guardandola. Si
testano invece le due regole che il disegno incorpora e che, se sbagliate, producono una
figura *plausibile ma falsa*: la compressione delle ore in intervalli (un estremo raggiunto
da piu' ore) e la misura di minimo, massimo e spread.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from mgp import grafici  # noqa: E402


class TestIntervalli:
    def test_ora_singola(self):
        assert grafici._intervalli([14]) == "14"

    def test_ore_consecutive(self):
        assert grafici._intervalli([1, 2, 3]) == "1-3"

    def test_blocchi_separati(self):
        # Il caso del 20 gennaio 2025: il massimo e' toccato dal picco del mattino e da
        # quello della sera. Annotare solo la prima ora farebbe sembrare un errore il
        # fatto che la spezzata tocchi il livello massimo anche altrove.
        assert grafici._intervalli([9, 10, 19, 20]) == "9-10, 19-20"

    def test_blocchi_misti(self):
        assert grafici._intervalli([3, 7, 8, 12]) == "3, 7-8, 12"


class TestFormatoItaliano:
    def test_virgola_decimale(self):
        assert grafici._it(161.31) == "161,3"

    def test_separatore_migliaia_non_e_un_punto(self):
        # Il punto e' il separatore decimale nell'XML del GME ma non nel testo italiano:
        # confonderli in una figura della tesi cambierebbe un numero di tre ordini.
        assert grafici._it(1234.5).endswith("234,5")
        assert "." not in grafici._it(1234.5)

    def test_decimali_configurabili(self):
        assert grafici._it(15.409, decimali=2) == "15,41"


class TestDataEstesa:
    def test_conversione(self):
        assert grafici.data_estesa("20250120") == "20 gennaio 2025"
        assert grafici.data_estesa("20250516") == "16 maggio 2025"


class TestProfiloPrezzi:
    """Il profilo restituisce gli estremi che poi finiscono in didascalia e nel testo."""

    @staticmethod
    def _profilo(prezzi: list[float]) -> pd.DataFrame:
        return pd.DataFrame({"ora": range(1, len(prezzi) + 1), "prezzo": prezzi})

    def test_estremi_e_spread(self):
        prezzi = [50.0, 20.0, 30.0, 90.0] + [40.0] * 20
        _, ax = plt.subplots()
        esito = grafici.profilo_prezzi(self._profilo(prezzi), ax)
        plt.close("all")

        assert esito["minimo"] == pytest.approx(20.0)
        assert esito["massimo"] == pytest.approx(90.0)
        assert esito["spread"] == pytest.approx(70.0)
        assert esito["ora_minimo"] == 2
        assert esito["ora_massimo"] == 4

    def test_estremo_condiviso_da_piu_ore(self):
        prezzi = [10.0, 10.0, 50.0, 80.0, 80.0] + [30.0] * 19
        _, ax = plt.subplots()
        esito = grafici.profilo_prezzi(self._profilo(prezzi), ax)
        plt.close("all")

        assert esito["_testo_min"].endswith("ore 1-2")
        assert esito["_testo_max"].endswith("ore 4-5")

    def test_ordine_delle_righe_irrilevante(self):
        prezzi = [50.0, 20.0, 30.0, 90.0] + [40.0] * 20
        mescolato = self._profilo(prezzi).sample(frac=1.0, random_state=0)

        _, ax = plt.subplots()
        esito = grafici.profilo_prezzi(mescolato, ax)
        plt.close("all")

        assert esito["ora_minimo"] == 2
        assert esito["ora_massimo"] == 4
        assert np.all(np.diff(esito["_ore"]) > 0)
