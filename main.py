"""
main.py
-------
Hauptprogramm, keine eigene Berechnungslogik - nur Ablaufsteuerung.
"""

import os
import logging
from pathlib import Path

from gps_track import GPSTrack
from speed_smoothing import SpeedSmoothingConfig
from ebike import EBike
from motor import Motor
from lipo_battery import LiPoBatteryPack
from nmc_battery import NMCBatteryPack
from ebike_simulator import EBikeSimulator
<<<<<<< HEAD
from bericht_erstellen import bericht_erstellen

# Logging global konfigurieren: alle Module (gps_track, bericht_erstellen,
# ...) nutzen automatisch dieses Format, da sie ihren eigenen
# logging.getLogger(__name__) verwenden
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
=======
from plot_utils import plots_erstellen
>>>>>>> b492d1f496c722c96632ba499740007064923d97


def main():
    # Ausgabeordner für Karten/Bericht anlegen, falls noch nicht vorhanden
    os.makedirs("output", exist_ok=True)
    os.makedirs("output/plot", exist_ok=True)
    basisverzeichnis = Path(__file__).resolve().parent

    log_datei = Path("output") / "ebike_simulation.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_datei, mode="w", encoding="utf-8"),
        ],
        force=True,
    )
    logging.getLogger(__name__).info("Logging wird in %s geschrieben.", log_datei)

    # --- 1. GPS-Track einlesen und auswerten -----------------------------
<<<<<<< HEAD
    # Beim Erzeugen des GPSTrack-Objekts werden automatisch alle
    # Kinematik-Spalten (Distanz, Geschwindigkeit, ...) mitberechnet
    track = GPSTrack("data/final_project_input_data.csv")

    print("=== Streckendaten ===")
    # Nur die ersten 10 Zeilen anzeigen, als kurzer Überblick über die
    # eingelesenen und berechneten Spalten
    print(track.df[["time", "distanz_m", "geschwindigkeit_ms",
                     "beschleunigung_ms2", "steigung_grad"]].head(10))
=======
    smoothing_config = SpeedSmoothingConfig.from_yaml(
        basisverzeichnis / "data" / "speed_smoothing_config.yaml"
    )
    track = GPSTrack(
        basisverzeichnis / "data" / "final_project_input_data.csv",
        smoothing_config=smoothing_config,
    )

    logging.getLogger(__name__).info(
        "Geschwindigkeitsglättung: %s",
        "aktiviert" if smoothing_config.enabled else "deaktiviert",
    )
    logging.getLogger(__name__).info(
        "Verwendete Parameter: min_interval_s=%.3f, max_gap_s=%.3f, median_window_s=%.3f, "
        "time_constant_s=%.3f, max_reasonable_speed_kmh=%.1f",
        smoothing_config.min_interval_s,
        smoothing_config.max_gap_s,
        smoothing_config.median_window_s,
        smoothing_config.time_constant_s,
        smoothing_config.max_reasonable_speed_kmh,
    )

    print("=== Streckendaten ===")
    print(
        track.df[
            [
                "time",
                "dt_s",
                "distanz_m",
                "geschwindigkeit_roh_ms",
                "geschwindigkeit_geglaettet_ms",
                "geschwindigkeit_ms",
                "beschleunigung_ms2",
                "steigung_grad",
            ]
        ].head(10)
    )
    print(
        "Aktive Geschwindigkeitskurve: "
        + (
            "geglättet"
            if smoothing_config.enabled
            else "roh"
        )
    )
>>>>>>> b492d1f496c722c96632ba499740007064923d97
    print()
    track.kennzahlen_ausgeben()
    print()

    # --- 1a. Reverse Geocoding: GPS-Koordinaten -> Adressen ----------------
    # Fragt Start, Ziel und ein paar Zwischenpunkte bei Nominatim (OSM) ab.
    # Ergebnis bleibt nur im Arbeitsspeicher (self.orte) - keine CSV-Datei.
    print("=== Adressen entlang der Strecke (Reverse Geocoding) ===")
    orte = track.orte_ermitteln(anzahl_wegpunkte=6)
    # Jede gefundene Adresse mit ihrem Index in der Strecke ausgeben,
    # ":>4" richtet den Index rechtsbündig auf 4 Zeichen aus
    for _, zeile in orte.iterrows():
        print(f"  [{zeile['index']:>4}] {zeile['adresse']}")
    print()

    # --- 1b. Strecke auf Karte plotten (folium, interaktiv) ---------------
    # Färbt die Strecke nach Geschwindigkeit ein und speichert eine
    # interaktive HTML-Karte, die sich im Browser öffnen lässt.
    track.karte_erstellen(
        farbwert="geschwindigkeit_ms",
        ausgabepfad="output/karte_strecke.html",
    )

    # --- 2. Fahrzeug & Motor definieren -----------------------------------
<<<<<<< HEAD
    # Diese Objekte sind für beide Akku-Varianten identisch, daher nur
    # einmal außerhalb der Schleife erzeugt
    bike = EBike(masse_fahrer_kg=70.0, masse_rad_kg=10.0, cw_a_m2=0.5625, raddurchmesser_inch=27.0)
=======
    bike = EBike.from_yaml(basisverzeichnis / "data" / "bike_config.yaml")
>>>>>>> b492d1f496c722c96632ba499740007064923d97
    motor = Motor(motorkonstante_Nm_A=1.5)

    # --- 3. Simulation für beide Akkutypen (Polymorphismus über BatteryBase) ---
    # Dictionary aus Anzeigename -> Akku-Objekt, damit die Schleife unten
    # generisch für beliebig viele Akku-Varianten funktioniert
    akku_varianten = {
        "LiPo": LiPoBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
        "NMC":  NMCBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
    }

    simulationsergebnisse = {}

    for name, akku in akku_varianten.items():
        print(f"=== Simulation mit {name}-Akku ===")
        # Simulation mit dem gleichen Track/Fahrzeug/Motor, aber jeweils
        # anderem Akku durchführen (akku wird über die Schleife getauscht)
        sim = EBikeSimulator(track=track, bike=bike, motor=motor, battery=akku)
        ergebnis_df = sim.simulate()
        simulationsergebnisse[name] = ergebnis_df
        sim.zusammenfassung_ausgeben()

        # Ladezustand entlang der Strecke auf einer interaktiven Karte darstellen
        track.karte_erstellen(
            df=ergebnis_df,
            farbwert="soc",
            ausgabepfad=f"output/karte_soc_{name.lower()}.html",
        )
    
        print()

<<<<<<< HEAD
    # --- 4. LaTeX-Bericht automatisch erstellen ---------------------------
    # Fasst Kennzahlen, Orte (Reverse Geocoding) und eine Kartenübersicht
    # in einem .tex-Dokument zusammen. Wird bei JEDEM Programmlauf neu
    # erzeugt und überschrieben (kein manueller Zwischenschritt nötig).
    # Übergeben wird hier bewusst `track` (die reine GPS-Strecke), nicht
    # `ergebnis_df` (das Simulationsergebnis mit SoC) - der Bericht bezieht
    # sich auf die Streckendaten, nicht auf eine bestimmte Akku-Simulation.
    print("=== LaTeX-Bericht ===")
    bericht_erstellen(
        track,
        tex_pfad="output/bericht.tex",
        karte_pfad="output/bericht_karte.png",
    )
    print("Bericht gespeichert unter: output/bericht.tex")
=======
    plots_erstellen(track.df, simulationsergebnisse, output_dir="output/plot")
>>>>>>> b492d1f496c722c96632ba499740007064923d97


if __name__ == "__main__":
    # Nur ausführen, wenn die Datei direkt gestartet wird (nicht beim
    # Importieren als Modul, z.B. aus einem Test heraus)
    main()
