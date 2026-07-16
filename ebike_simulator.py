"""
ebike_simulator.py
-------------------
Entspricht dem EBikeSimulator aus Kapitel 09.5 (dort per Umbenennung aus
BatterySimulator entstanden). Verbindet Akku, Motor und Fahrzeugmodell
per ASSOZIATION (Klasse "hat ein" Objekt der jeweils anderen Klasse) -
genau wie im UML-Diagramm des Kurses:

    EBikeSimulator --> BatteryBase
    EBikeSimulator --> Motor

Erweitert um die Assoziation zu GPSTrack, da hier (anders als im Kurs)
kein synthetisches Lastprofil vorliegt, sondern eine reale GPS-Aufzeichnung
als Datenquelle dient (siehe Kommentare in gps_track.py und ebike.py).

Wie im Kurs-Vorbild wird der Type Hint auf die ABSTRAKTE Basisklasse
`BatteryBase` gesetzt, nicht auf eine konkrete Akku-Klasse -> der
Simulator funktioniert dadurch mit jedem beliebigen Akkutyp (Polymorphismus).
"""

import logging
import pandas as pd

from battery_base import BatteryBase
from motor import Motor
from ebike import EBike
from gps_track import GPSTrack

logger = logging.getLogger(__name__)


class EBikeSimulator:
    """
    Führt die Simulation über einen GPSTrack aus: berechnet pro Punkt über
    EBike/Motor den nötigen Motorstrom und wendet ihn auf den Akku an.
    Zeichnet dabei - analog zu self.voltage_profile im Kurs-Vorbild -
    mehrere Profile über die Zeit auf.

    Attribute:
        track (GPSTrack):
        bike (EBike):
        motor (Motor):
        battery (BatteryBase):     Type Hint auf die ABC -> beliebiger Akkutyp möglich
        leistung_profile, drehmoment_profile, strom_profile,
        spannung_profile, soc_profile (list[float]): werden erst durch simulate() befüllt
    """

    def __init__(self, track: GPSTrack, bike: EBike, motor: Motor, battery: BatteryBase):
        self.track = track
        self.bike = bike
        self.motor = motor
        self.battery = battery

        # Profile analog zu self.voltage_profile aus dem Kurs-Vorbild
        self.leistung_profile: list[float] = []
        self.drehmoment_profile: list[float] = []
        self.strom_profile: list[float] = []
        self.spannung_profile: list[float] = []
        self.soc_profile: list[float] = []

    def simulate(self) -> pd.DataFrame:
        """
        Geht den GPSTrack Punkt für Punkt durch (analog zur simulate()-Methode
        des Kurs-BatterySimulator/EBikeSimulator, nur mit GPS-Daten statt
        einer vorgegebenen Liste aus Strömen/Leistungen als Eingabe).
        """
        df = self.track.df
        n = len(df)
        letzter_gueltiger_index = n - 1

        # erster Punkt hat keinen Vorgänger -> Startzustand
        self.leistung_profile = [0.0]
        self.drehmoment_profile = [0.0]
        self.strom_profile = [0.0]
        self.spannung_profile = [self.battery.voltage()]
        self.soc_profile = [self.battery.soc]

        for i in range(1, n):
            v = df["geschwindigkeit_ms"].iloc[i]
            a = df["beschleunigung_ms2"].iloc[i]
            phi = df["steigung_grad"].iloc[i]
            dt = (df["time"].iloc[i] - df["time"].iloc[i - 1]).total_seconds()

            werte = self.bike.punkt_auswerten(v, a, phi)
            strom = self.motor.get_current_draw(werte["drehmoment_Nm"])

            if dt > 0:
                try:
                    self.battery.apply_current(strom, dt)
                except RuntimeError:
                    logger.error(f"Simulation bei Index {i} abgebrochen: Akku leer.")
                    letzter_gueltiger_index = i - 1
                    break

            self.leistung_profile.append(werte["leistung_W"])
            self.drehmoment_profile.append(werte["drehmoment_Nm"])
            self.strom_profile.append(strom)
            self.spannung_profile.append(self.battery.voltage(strom))
            self.soc_profile.append(self.battery.soc)

        df_ergebnis = df.iloc[: letzter_gueltiger_index + 1].copy()
        df_ergebnis["leistung_W"] = self.leistung_profile
        df_ergebnis["drehmoment_Nm"] = self.drehmoment_profile
        df_ergebnis["motorstrom_A"] = self.strom_profile
        df_ergebnis["spannung_V"] = self.spannung_profile
        df_ergebnis["soc"] = self.soc_profile
        return df_ergebnis

    def maximalleistung_W(self) -> float:
        return max(self.leistung_profile) if self.leistung_profile else 0.0

    def endladezustand_prozent(self) -> float:
        return self.soc_profile[-1] * 100 if self.soc_profile else self.battery.soc * 100

    def zusammenfassung_ausgeben(self) -> None:
        print(f"Akku:                {self.battery}")
        print(f"Maximalleistung:     {self.maximalleistung_W():.1f} W")
        print(f"Ladezustand am Ende: {self.endladezustand_prozent():.1f} %")
