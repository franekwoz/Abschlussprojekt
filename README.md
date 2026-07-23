# E-Bike-Batteriesimulation

Das Projekt simuliert den Energiebedarf einer E-Bike-Fahrt auf Basis realer GPS-Daten. Aus einer CSV-Datei werden Strecke, Geschwindigkeit, Beschleunigung, Steigung und weitere Fahrgrößen abgeleitet. Darauf aufbauend berechnet das Programm das Fahrverhalten für LiPo- und NMC-Akkus und stellt die Ergebnisse in der Konsole sowie in der Flask-Weboberfläche dar.

## Funktionsüberblick

- Einlesen und Auswerten von GPS-Daten
- Berechnung von Fahrdynamik, Leistung, Strom und Ladezustand
- Simulation von LiPo- und NMC-Akkus
- optionale Geschwindigkeitsglättung
- optionale Orts- und Wetterdaten entlang der Strecke
- Konsolenanwendung
- Flask-Weboberfläche
- Parameterstudie mit CSV-Export
- HTML-Karten, PNG-Plots und CSV-Dateien als Ausgaben

## Voraussetzungen

- Python 3.14.2 wurde in der lokalen Entwicklungsumgebung verwendet
- Abhängigkeiten aus `requirements.txt`
- LuaLaTeX und `latexmk` für den Bericht

## Installation

```bash
git clone https://github.com/franekwoz/Abschlussprojekt.git
cd Abschlussprojekt
python -m venv .venv
```

Windows PowerShell:

```powershell
\.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

## Konsolenanwendung starten

```bash
python main.py
```

## Webanwendung starten

```bash
python app.py
```

## Tests ausführen

```bash
python -m pytest -q
```

## Dokumentation

Der ausführliche Projektbericht liegt in [report/main.pdf](report/main.pdf). Die LaTeX-Quelle ist unter [report/main.tex](report/main.tex) verfügbar. Technische Details, mathematische Grundlagen, Architektur, Modelle, Tests und Ergebnisse sind dort dokumentiert.

## Autoren

Thea Welk, Emil Kupfer, Franciszek Wozniak
