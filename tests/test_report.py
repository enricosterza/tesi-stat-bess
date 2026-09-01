"""
Test della conversione Markdown -> Word dei report settimanali (`mgp.report`).

Il documento che esce da qui va al relatore, quindi gli errori di formattazione non
sono cosmetici: una barra rovesciata rimasta a vista o un corsivo aperto per sbaglio
si notano subito e tolgono credibilita' al resto.

I casi sono tutti verificabili a mano: si scrive un frammento di Markdown e si
controlla che cosa finisce nei "run" di Word.
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgp.report import _aggiungi_testo, markdown_to_docx  # noqa: E402


def _run(testo: str) -> list[tuple[str, bool, bool]]:
    """Converte un frammento inline e restituisce (testo, grassetto, corsivo) per run."""
    p = Document().add_paragraph()
    _aggiungi_testo(p, testo)
    return [(r.text, bool(r.bold), bool(r.italic)) for r in p.runs]


# --- escape Markdown ----------------------------------------------------------------


def test_escape_asterisco_perde_la_barra():
    """`K\\*` deve arrivare in Word come `K*`, non come `K\\*`.

    E' il caso che ricorre nei report, dove la soglia si scrive K\\* per impedire che
    l'asterisco apra un corsivo.
    """
    assert _run(r"La soglia K\* vale 50 MW") == [("La soglia K* vale 50 MW", False, False)]


def test_due_escape_sulla_stessa_riga_non_diventano_corsivo():
    """Il caso che la sola rimozione della barra non risolverebbe.

    Senza protezione, il testo fra i due asterischi verrebbe letto come un corsivo e
    si perderebbero entrambi i delimitatori.
    """
    assert _run(r"K\* scende mentre K\* sale") == [
        ("K* scende mentre K* sale", False, False)
    ]


def test_escape_dentro_il_codice_resta_letterale():
    """In Markdown gli escape non agiscono dentro il codice inline.

    Chi scrive `\\*` fra apici inversi vuole vedere proprio quei due caratteri.
    """
    (testo, _, _), = _run(r"il carattere `\*` in regex")[1:2]
    assert testo == r"\*"


def test_escape_dentro_il_grassetto():
    assert _run(r"**K\* definitiva**") == [("K* definitiva", True, False)]


# --- formattazione inline gia' supportata, per non farla regredire -------------------


def test_grassetto_e_corsivo_restano_distinti():
    assert _run("testo **grasso** e *corsivo* qui") == [
        ("testo ", False, False),
        ("grasso", True, False),
        (" e ", False, False),
        ("corsivo", False, True),
        (" qui", False, False),
    ]


def test_codice_inline_non_viene_interpretato():
    """Un asterisco dentro il codice non deve aprire un corsivo."""
    assert [t for t, _, _ in _run("vedi `a * b` nel testo")] == ["vedi ", "a * b", " nel testo"]


# --- documento completo -------------------------------------------------------------


def test_conversione_di_un_report_minimo(tmp_path):
    """Titoli, tabella con escape nell'intestazione e corpo del testo."""
    sorgente = tmp_path / "2026-01-01_report.md"
    sorgente.write_text(
        "# Report di prova\n"
        "\n"
        "## Risultati\n"
        "\n"
        "| Anno | K\\* |\n"
        "|---|---|\n"
        "| 2024 | **50,1** |\n"
        "\n"
        "La soglia K\\* e' scesa.\n",
        encoding="utf-8",
    )
    destinazione = markdown_to_docx(sorgente, tmp_path / "prova.docx")

    doc = Document(destinazione)
    titoli = [p.text for p in doc.paragraphs if p.style.name.startswith(("Title", "Heading"))]
    assert titoli == ["Report di prova", "Risultati"]

    tabella = doc.tables[0]
    # L'intestazione passa da un percorso diverso dal corpo: va controllata a parte.
    assert [c.text for c in tabella.rows[0].cells] == ["Anno", "K*"]
    assert [c.text for c in tabella.rows[1].cells] == ["2024", "50,1"]

    assert any("La soglia K* e' scesa." == p.text for p in doc.paragraphs)


def test_nessuna_barra_rovesciata_residua_nei_report_veri(tmp_path):
    """Controllo di regressione sui report effettivamente scritti.

    Se un report contiene un escape che il convertitore non scioglie, il difetto si
    vede solo aprendo il `.docx`: questo test lo fa fallire prima.
    """
    from mgp import config

    sorgenti = sorted(
        p for p in (config.DOCS_DIR / "report").glob("*_report.md") if not p.name.startswith("_")
    )
    assert sorgenti, "nessun report da controllare"

    for sorgente in sorgenti:
        doc = Document(markdown_to_docx(sorgente, tmp_path / f"{sorgente.stem}.docx"))
        fuori_codice = [
            r.text
            for p in doc.paragraphs
            for r in p.runs
            if r.font.name != "Consolas" and "\\" in r.text
        ]
        assert not fuori_codice, f"{sorgente.name}: barre rovesciate residue {fuori_codice[:3]}"
