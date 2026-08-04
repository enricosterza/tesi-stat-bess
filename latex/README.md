# Sorgenti LaTeX della tesi

Documento modulare: `main.tex` contiene preambolo, frontespizio e indici, e richiama con
`\input{}` un file per capitolo dalla sottocartella `capitoli/`.

```
main.tex              preambolo, frontespizio segnaposto, indice, elenco figure
capitoli/
  01_introduzione.tex
  02_mercato_elettrico.tex
  03_strategia_ottima.tex
  04_simulazione.tex
  05_valutazione_economica.tex
  06_conclusioni.tex
bibliografia.bib      vuoto, con l'elenco commentato delle voci da inserire
figure/               immagini incluse nel documento
```

## Come compilare

Sul computer non è installata alcuna distribuzione LaTeX, quindi il documento va compilato
altrove.

**Su Overleaf** (via più rapida): caricare l'intera cartella `latex/` come progetto e
impostare il compilatore su **pdfLaTeX** (Menu → Compiler). Overleaf gestisce da sé le
esecuzioni multiple e biber.

**In locale**, dopo aver installato MiKTeX o TeX Live:

```powershell
cd latex
latexmk -pdf main.tex
```

oppure, a mano:

```powershell
pdflatex main
biber    main
pdflatex main
pdflatex main
```

Finché non ci sono citazioni nel testo, biber segnala che la bibliografia è vuota: è un
avviso, non un errore, e sparisce appena si inserisce la prima voce in `bibliografia.bib`.

## Convenzioni

* **Segnaposto.** Le parti non ancora scritte sono marcate con un commento `% DA COMPLETARE`
  che indica cosa andrà scritto lì. Cercare `DA COMPLETARE` per avere l'elenco di quanto
  manca.
* **Numeri.** Ogni numero citato nel testo proviene da uno script del progetto ed è
  riproducibile: i risultati della validazione stanno in `output/tabelle/`, le decisioni
  metodologiche in `docs/decisioni.md` e il ragionamento che le motiva in `docs/DIARIO.md`.
* **Figure.** `\graphicspath` punta sia a `figure/` sia a `../output/figure/`, così i
  grafici generati dagli script si possono includere senza copiarli.
* **Codice.** Gli estratti usano `listings` e non `minted`, che richiederebbe Python e la
  compilazione con `--shell-escape`, complicando l'uso su Overleaf.
* **Accenti.** Nel sorgente si usano sia i caratteri accentati diretti (`à`) sia la forma
  `\`a`: entrambe funzionano con `inputenc` UTF-8. Il simbolo dell'euro si scrive
  `\eur` o `\euromwh`, definiti nel preambolo.
