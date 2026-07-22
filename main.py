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
from bericht_erstellen import bericht_erstellen

# Logging global konfigurieren: alle Module (gps_track, bericht_erstellen,
# ...) nutzen automatisch dieses Format, da sie ihren eigenen
# logging.getLogger(__name__) verwenden
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    # Ausgabeordner für Karten/Bericht anlegen, falls noch nicht vorhanden
    os.makedirs("output", exist_ok=True)

    # --- 1. GPS-Track einlesen und auswerten -----------------------------
    # Beim Erzeugen des GPSTrack-Objekts werden automatisch alle
    # Kinematik-Spalten (Distanz, Geschwindigkeit, ...) mitberechnet
    track = GPSTrack("data/final_project_input_data.csv")

    print("=== Streckendaten ===")
    # Nur die ersten 10 Zeilen anzeigen, als kurzer Überblick über die
    # eingelesenen und berechneten Spalten
    print(track.df[["time", "distanz_m", "geschwindigkeit_ms",
                     "beschleunigung_ms2", "steigung_grad"]].head(10))
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
    # Diese Objekte sind für beide Akku-Varianten identisch, daher nur
    # einmal außerhalb der Schleife erzeugt
    bike = EBike(masse_fahrer_kg=70.0, masse_rad_kg=10.0, cw_a_m2=0.5625, raddurchmesser_inch=27.0)
    motor = Motor(motorkonstante_Nm_A=1.5)

    # --- 3. Simulation für beide Akkutypen (Polymorphismus über BatteryBase) ---
    # Dictionary aus Anzeigename -> Akku-Objekt, damit die Schleife unten
    # generisch für beliebig viele Akku-Varianten funktioniert
    akku_varianten = {
        "LiPo": LiPoBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
        "NMC":  NMCBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1),
    }

    for name, akku in akku_varianten.items():
        print(f"=== Simulation mit {name}-Akku ===")
        # Simulation mit dem gleichen Track/Fahrzeug/Motor, aber jeweils
        # anderem Akku durchführen (akku wird über die Schleife getauscht)
        sim = EBikeSimulator(track=track, bike=bike, motor=motor, battery=akku)
        ergebnis_df = sim.simulate()
        sim.zusammenfassung_ausgeben()

        # Ladezustand entlang der Strecke auf einer interaktiven Karte darstellen
        track.karte_erstellen(
            df=ergebnis_df,
            farbwert="soc",
            ausgabepfad=f"output/karte_soc_{name.lower()}.html",
        )
    
        print()

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


if __name__ == "__main__":
    # Nur ausführen, wenn die Datei direkt gestartet wird (nicht beim
    # Importieren als Modul, z.B. aus einem Test heraus)
    main()
