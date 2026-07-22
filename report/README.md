# LaTeX-Projektbericht

Dieses Verzeichnis enthaelt den deutschsprachigen Projektbericht zum E-Bike-Simulationsprojekt auf Basis der Dokumentklasse `mcidoc`.

## Herkunft der Klasse

Die Klasse stammt aus dem Repository [dTmC0945/C-MCI-LaTeX-Class-mcidoc](https://github.com/dTmC0945/C-MCI-LaTeX-Class-mcidoc).

## Verwendeter Commit

Verwendet wurde der Commit `735b49b5686375e546b5f7329eabcbc99a2001b8`.

## Lizenzhinweis

`mcidoc.cls` bleibt unveraendert und wird unter den Bedingungen der LaTeX Project Public License (LPPL) weitergegeben. Der urspruengliche Lizenzkopf ist im Class-File erhalten.

## Build

Voraussetzung ist eine LaTeX-Installation mit LuaLaTeX und `latexmk`.

Aus diesem Verzeichnis heraus bauen:

```powershell
make
```

Weitere Ziele:

```powershell
make clean
make distclean
```

Das PDF wird unter `build/abschlussprojekt_report.pdf` erzeugt.
