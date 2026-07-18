"""
main.py
-------
Hauptprogramm, keine eigene Berechnungslogik - nur Ablaufsteuerung.
"""

import os
import logging

from gps_track import GPSTrack
from ebike import EBike
from motor import Motor
from lipo_battery import LiPoBatteryPack
from nmc_battery import NMCBatteryPack
from ebike_simulator import EBikeSimulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    os.makedirs("output", exist_ok=True)

    # --- 1. GPS-Track einlesen und auswerten -----------------------------
    track = GPSTrack("data/final_project_input_data.csv")

    print("=== Streckendaten ===")
    print(track.df[["time", "distanz_m", "geschwindigkeit_ms",
                     "beschleunigung_ms2", "steigung_grad"]].head(10))
    print()
    track.kennzahlen_ausgeben()
    print()

    # --- 1b. Strecke auf Karte plotten (folium) --------------------------
    # Färbt die Strecke nach Geschwindigkeit ein und speichert eine
    # interaktive HTML-Karte, die sich im Browser öffnen lässt.
    track.karte_erstellen(
        farbwert="geschwindigkeit_ms",
        ausgabepfad="output/karte_strecke.html",
    )

    # --- 2. Fahrzeug & Motor definieren -----------------------------------
    bike = EBike(masse_fahrer_kg=70.0, masse_rad_kg=10.0, cw_a_m2=0.5625, raddurchmesser_inch=27.0)
    motor = Motor(motorkonstante_Nm_A=1.5)

    # --- 3. Simulation für beide Akkutypen (Polymorphismus über BatteryBase) ---
    akku_varianten = {
        "LiPo": LiPoBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
        "NMC":  NMCBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
    }

    for name, akku in akku_varianten.items():
        print(f"=== Simulation mit {name}-Akku ===")
        sim = EBikeSimulator(track=track, bike=bike, motor=motor, battery=akku)
        ergebnis_df = sim.simulate()
        sim.zusammenfassung_ausgeben()

        # Ladezustand entlang der Strecke auf eigener Karte darstellen.
        track.karte_erstellen(
            df=ergebnis_df,
            farbwert="soc",
            ausgabepfad=f"output/karte_soc_{name.lower()}.html",
        )
        print()


if __name__ == "__main__":
    main()
