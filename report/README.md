N# LaTeX Report Scaffold

This folder contains a LaTeX project scaffold matching the section structure from `docs/Report_P1_NBA-compressed.pdf`.

## Files

- `main.tex`: entry point for the report.
- `sections/*.tex`: one file per major section and subsection.
- `figures/`: place screenshots/diagrams used in the report.

## Build

```bash
cd report
pdflatex main.tex
pdflatex main.tex
```

For references and ToC updates, run LaTeX twice.
