"""
main.py
-------
Hauptprogramm, keine eigene Berechnungslogik - nur Ablaufsteuerung.
"""

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
    # --- 1. GPS-Track einlesen und auswerten -----------------------------
    track = GPSTrack("data/final_project_input_data.csv")

    print("=== Streckendaten ===")
    print(track.df[["time", "distanz_m", "geschwindigkeit_ms",
                     "beschleunigung_ms2", "steigung_grad"]].head(10))
    print()
    track.kennzahlen_ausgeben()
    print()

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
        sim.simulate()
        sim.zusammenfassung_ausgeben()
        print()


if __name__ == "__main__":
    main()
