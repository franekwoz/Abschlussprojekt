LATEXMK = latexmk
LATEXMK_FLAGS = -lualatex -interaction=nonstopmode -halt-on-error
TARGET = main.tex
OUTPUT = build/abschlussprojekt_report.pdf
JOBNAME = abschlussprojekt_report

all:
	$(LATEXMK) $(LATEXMK_FLAGS) -jobname=$(JOBNAME) -outdir=build $(TARGET)

clean:
	$(LATEXMK) -c -jobname=$(JOBNAME) -outdir=build $(TARGET)

distclean: clean
	powershell -NoProfile -Command "if (Test-Path 'build') { Remove-Item -Recurse -Force 'build' }"
