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
from plot_utils import plots_erstellen


def main():
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
    print()
    track.kennzahlen_ausgeben()
    print()

    # --- 1b. Strecke auf Karte plotten (folium, interaktiv) ---------------
    # Färbt die Strecke nach Geschwindigkeit ein und speichert eine
    # interaktive HTML-Karte, die sich im Browser öffnen lässt.
    track.karte_erstellen(
        farbwert="geschwindigkeit_ms",
        ausgabepfad="output/karte_strecke.html",
    )

    # --- 2. Fahrzeug & Motor definieren -----------------------------------
    bike = EBike.from_yaml(basisverzeichnis / "data" / "bike_config.yaml")
    motor = Motor(motorkonstante_Nm_A=1.5)

    # --- 3. Simulation für beide Akkutypen (Polymorphismus über BatteryBase) ---
    akku_varianten = {
        "LiPo": LiPoBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
        "NMC":  NMCBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
    }

    simulationsergebnisse = {}

    for name, akku in akku_varianten.items():
        print(f"=== Simulation mit {name}-Akku ===")
        sim = EBikeSimulator(track=track, bike=bike, motor=motor, battery=akku)
        ergebnis_df = sim.simulate()
        simulationsergebnisse[name] = ergebnis_df
        sim.zusammenfassung_ausgeben()

        # Ladezustand entlang der Strecke auf eigener Karte darstellen
        # (einmal interaktiv mit folium, einmal statisch mit geopandas).
        track.karte_erstellen(
            df=ergebnis_df,
            farbwert="soc",
            ausgabepfad=f"output/karte_soc_{name.lower()}.html",
        )
    
        print()

    plots_erstellen(track.df, simulationsergebnisse, output_dir="output/plot")


if __name__ == "__main__":
    main()
