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
import math
import pandas as pd

from battery_base import BatteryBase
from motor import Motor
from ebike import EBike
from gps_track import GPSTrack
from luftdichte import luftdichte_kg_m3

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
        self.bremswiderstand_profile: list[float] = []  

    def simulate(self) -> pd.DataFrame:
        """
        Geht den GPSTrack Punkt für Punkt durch (analog zur simulate()-Methode
        des Kurs-BatterySimulator/EBikeSimulator, nur mit GPS-Daten statt
        einer vorgegebenen Liste aus Strömen/Leistungen als Eingabe).
        """
        df = self.track.df
        n = len(df)
        if n == 0:
            raise ValueError("GPSTrack enthält keine Daten.")

        logger.info(
            "Starte Simulation mit %d Messpunkten für Akku %s.",
            n,
            type(self.battery).__name__,
        )
        letzter_gueltiger_index = n - 1

        # erster Punkt hat keinen Vorgänger -> Startzustand
        self.leistung_profile = [0.0]
        self.drehmoment_profile = [0.0]
        self.strom_profile = [0.0]
        self.spannung_profile = [self.battery.voltage()]
        self.soc_profile = [self.battery.soc]
        self.bremswiderstand_profile = [0.0]  

        for i in range(1, n):
            v = df["geschwindigkeit_ms"].iloc[i]
            a = df["beschleunigung_ms2"].iloc[i]
            phi = df["steigung_grad"].iloc[i]
            dt = (df["time"].iloc[i] - df["time"].iloc[i - 1]).total_seconds()

            if not math.isfinite(v) or not math.isfinite(a):
                raise ValueError(
                    f"Nicht-endlicher Simulationswert bei Index {i}: v={v}, a={a}."
                )

            if dt < 0:
                logger.error("Zeitstempel sind nicht monoton steigend bei Index %d.", i)
                raise ValueError("GPSTrack-Zeitstempel müssen monoton steigend sein.")

            rho = None
            hoehe = df["ele"].iloc[i] if "ele" in df.columns else None
            temperatur = df["temperature"].iloc[i] if "temperature" in df.columns else None
            if hoehe is not None and temperatur is not None and pd.notna(hoehe) and pd.notna(temperatur):
                try:
                    rho = luftdichte_kg_m3(hoehe, temperatur)
                except ValueError:
                    logger.warning(f"Ungültige Höhe/Temperatur bei Index {i}, verwende Standard-Luftdichte.")

            werte = self.bike.punkt_auswerten(v, a, phi, rho)
            strom = self.motor.get_current_draw(werte["drehmoment_Nm"])
            if temperatur is not None and pd.notna(temperatur):
                self.battery.set_temperatur(temperatur)

            diessipierte_leistung = 0.0
            if dt > 0:
                try:
                    self.battery.apply_current(strom, dt)
                    dissipierte_leistung = self.battery.letzte_dissipierte_leistung_W
                    if not math.isfinite(self.battery.soc) or not 0.0 <= self.battery.soc <= 1.0:
                        logger.error(
                            "Ungültiger SoC %.6f nach Schritt %d.",
                            self.battery.soc,
                            i,
                        )
                        raise ValueError("Akku-SoC ist außerhalb des gültigen Bereichs [0, 1].")
                except RuntimeError:
                    logger.error(f"Simulation bei Index {i} abgebrochen: Akku leer.")
                    letzter_gueltiger_index = i - 1
                    break
                except ValueError as exc:
                    logger.error("Simulation bei Index %d abgebrochen: %s", i, exc)
                    raise

            self.leistung_profile.append(werte["leistung_W"])
            self.drehmoment_profile.append(werte["drehmoment_Nm"])
            self.strom_profile.append(strom)
            self.spannung_profile.append(self.battery.voltage(strom))
            self.soc_profile.append(self.battery.soc)
            self.bremswiderstand_profile.append(dissipierte_leistung)

        df_ergebnis = df.iloc[: letzter_gueltiger_index + 1].copy()
        df_ergebnis["leistung_W"] = self.leistung_profile
        df_ergebnis["drehmoment_Nm"] = self.drehmoment_profile
        df_ergebnis["motorstrom_A"] = self.strom_profile
        df_ergebnis["spannung_V"] = self.spannung_profile
        df_ergebnis["soc"] = self.soc_profile
        logger.info(
            "Simulation beendet nach %d Messpunkten, End-SoC %.1f%%.",
            len(df_ergebnis),
            self.endladezustand_prozent(),
        )
        return df_ergebnis

    def maximalleistung_W(self) -> float:
        return max(self.leistung_profile) if self.leistung_profile else 0.0

    def bremswiderstand_energie_Wh(self) -> float:
        """Über die gesamte Fahrt als Wärme dissipierte Energie (Wattstunden)."""
        df = self.track.df
        gesamtenergie_Wh = 0.0
        for i in range(1, len(self.bremswiderstand_profile)):
            dt = (df["time"].iloc[i] - df["time"].iloc[i - 1]).total_seconds()
            if dt > 0:
                gesamtenergie_Wh += self.bremswiderstand_profile[i] * dt
        return gesamtenergie_Wh / 3600.0  # von Ws in Wh umrechnen

    def endladezustand_prozent(self) -> float:
        return self.soc_profile[-1] * 100 if self.soc_profile else self.battery.soc * 100

    def zusammenfassung_ausgeben(self) -> None:
        print(f"Akku:                {self.battery}")
        print(f"Maximalleistung:     {self.maximalleistung_W():.1f} W")
        print(f"Ladezustand am Ende: {self.endladezustand_prozent():.1f} %")
        print(f"Bremswiderstand:     {self.bremswiderstand_energie_Wh():.2f} Wh dissipiert")