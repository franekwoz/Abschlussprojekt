# E-Bike Route Simulation

This project simulates the energy demand of an e-bike along a real GPS track. It reads route data from a CSV file, derives speed, acceleration, and slope from the track, and then calculates the required motor power, torque, current draw, battery state of charge, and voltage for two battery types: LiPo and NMC.

## Installation

The project is designed to run with Python and a local virtual environment.

1. Open a terminal in the project folder.
2. Create a virtual environment:

```powershell
python -m venv .venv
```

3. Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

4. Install the dependencies:

```powershell
pip install -r requirements.txt
```

5. Run the main script:

```powershell
python main.py
```

## Input and Output

### Input

The main input is the GPS track file at `data/final_project_input_data.csv`. The file is read as semicolon-separated CSV data and is expected to contain at least these columns:

- `time`
- `lat`
- `lon`
- `ele`

The bike parameters are loaded from `data/bike_config.yaml`.

Example keys:

- `masse_fahrer_kg`
- `masse_rad_kg`
- `cw_a_m2`
- `raddurchmesser_inch`
- `rollwiderstandkoeffizient`

The program derives additional track values from this input, including:

- distance per step
- speed
- acceleration
- slope angle

### Output

When you run `main.py`, the script prints track statistics and simulation summaries in the terminal. It also creates HTML map files in the `output/` folder:

- `output/karte_strecke.html` for the route colored by speed
- `output/karte_soc_lipo.html` for the LiPo simulation colored by state of charge
- `output/karte_soc_nmc.html` for the NMC simulation colored by state of charge

Additionally, static PNG plots are generated in `output/plot/`:

- `output/plot/hoehenprofil_fahrt.png` for the elevation profile of the route
- `output/plot/zeitverlauf_lipo.png` with speed, power, state of charge, current and voltage over time (LiPo)
- `output/plot/zeitverlauf_nmc.png` with speed, power, state of charge, current and voltage over time (NMC)
- `output/plot/ladezustand_vergleich.png` for SoC comparison of battery types over time

The program also writes a log file to `output/ebike_simulation.log` with the same timestamped messages that appear in the console.

The output folder is created automatically if it does not exist.

## Project Structure

- `main.py` - program entry point and orchestration
- `gps_track.py` - reads the GPS data, computes kinematics, and creates maps
- `ebike.py` - vehicle physics model
- `motor.py` - motor model and current calculation
- `ebike_simulator.py` - runs the simulation over the GPS track
- `battery_base.py` - abstract battery base class
- `battery_pack.py` - shared battery-pack functionality
- `lipo_battery.py` - LiPo battery implementation
- `nmc_battery.py` - NMC battery implementation
- `akkutemperatur.py` - battery temperature helper functions
- `luftdichte.py` - air density helper functions
- `data/` - input data files
- `output/` - generated simulation and map output
- `plot_utils.py` - static plot generation (time series and elevation profile)
- `karte_plotten_folium/` - additional folium example files

## Functionality

The project works in three main steps:

1. The GPS route is loaded from the CSV file and converted into derived motion data.
2. The e-bike model calculates the physical forces and power required at each point of the route.
3. The simulator applies the load profile to two different battery models and records the resulting battery behavior.

The results are then visualized as interactive HTML maps. One map shows the route colored by speed, and two maps show the route colored by battery state of charge for the LiPo and NMC simulations.

## Notes

- The project uses `folium` for interactive maps.
- If you want to open the generated HTML files locally, simply open them in a browser after running the script.

## LaTeX-Projektbericht

Ein vollstaendiger deutschsprachiger Projektbericht befindet sich im Verzeichnis `report/`.

- Voraussetzungen: LuaLaTeX, `latexmk` und die in `requirements.txt` aufgefuehrten Python-Pakete
- Build: `cd report` und dann `make` oder direkt `latexmk -lualatex -interaction=nonstopmode -halt-on-error main.tex`
- Ausgabe-PDF: `report/build/abschlussprojekt_report.pdf`

## Geschwindigkeitsglättung

Die aus GPS-Punkten berechnete Geschwindigkeit kann bei sehr kurzen Zeitabständen und Messrauschen stark schwanken. Diese Schwankungen wirken direkt auf die Beschleunigung und damit auf die berechnete Leistung. Deshalb besitzt das Projekt eine optional ein- und ausschaltbare, zeitbasierte Geschwindigkeitsglättung.

Die Konfiguration liegt in:

- `data/speed_smoothing_config.yaml`

Aktivieren:

```yaml
enabled: true
```

Deaktivieren:

```yaml
enabled: false
```

Weitere Parameter in derselben Datei:

- `min_interval_s`: Kleinste Intervallzeit, die als gültige Filterstützstelle akzeptiert wird
- `max_gap_s`: Zeitlücke, ab der ein neuer Messabschnitt beginnt
- `median_window_s`: Breite des zeitbasierten Medianfensters
- `time_constant_s`: Zeitkonstante der exponentiellen Glättung
- `max_reasonable_speed_kmh`: Plausibilitätsgrenze für Filterstützstellen (kein hartes Abschneiden)

Filterablauf (pro zusammenhängendem Messabschnitt):

1. Rohgeschwindigkeit aus Distanz und `dt_s` berechnen.
2. Ungültige Stützstellen markieren (`dt_s <= 0`, sehr kurze Intervalle, unplausible Ausreißer).
3. Zeitbasierten Medianfilter anwenden.
4. Fehlende Werte nur innerhalb des Abschnitts zeitbasiert interpolieren.
5. Zeitabhängige exponentielle Glättung vorwärts und rückwärts ausführen.
6. Beide Verläufe mitteln.
7. Beschleunigung aus der jeweils verwendeten Geschwindigkeitskurve berechnen.

Wichtig:

- Es werden keine Leistungs-, Geschwindigkeits- oder Beschleunigungswerte hart begrenzt.
- Rohwerte bleiben erhalten.

Neue/erweiterte Spalten im Track-DataFrame:

- `dt_s`
- `segment_id`
- `geschwindigkeit_roh_ms`
- `geschwindigkeit_geglaettet_ms`
- `beschleunigung_roh_ms2`
- `beschleunigung_geglaettet_ms2`
- `geschwindigkeit_ms` (aktive Simulationsgeschwindigkeit)
- `beschleunigung_ms2` (aktive Simulationsbeschleunigung)
- `filter_gueltige_stuetzstelle`
- `filter_kurzes_intervall`
- `filter_grosse_zeitluecke`
- `filter_geschwindigkeitsausreisser`
- `speed_smoothing_enabled`

Damit bleibt die Simulationsschnittstelle unverändert: Der Simulator arbeitet weiterhin mit `geschwindigkeit_ms` und `beschleunigung_ms2`.