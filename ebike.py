"""
ebike.py
--------
Modelliert die Fahrzeugphysik (Kräfte, Leistung, Drehmoment).

Rolle im Vergleich zum Kurs-Vorbild (Kapitel 09.5, VehicleModel):
Im Kurs bekommt VehicleModel.step(power, duration) eine Leistung
VORGEGEBEN und SIMULIERT daraus vorwärts Geschwindigkeit und Weg
(v_{k+1} = v_k + a*dt, mit a = P/(m*v_k)).

Für das Abschlussprojekt liegt der Bewegungsverlauf aber bereits als
GEMESSENE GPS-Aufzeichnung vor (siehe gps_track.py) - Geschwindigkeit,
Beschleunigung und Steigung sind also schon bekannt, nicht gesucht.
EBike rechnet deshalb in die entgegengesetzte Richtung: aus einem
gegebenen Bewegungszustand (v, a, phi) wird die dafür NÖTIGE Kraft/
Leistung/Drehmoment berechnet - keine Zeitintegration nötig.

EBike ist damit der inhaltliche, aber nicht der strukturelle Nachfolger
von VehicleModel: gleiche Zuständigkeit (Fahrzeugdynamik), aber andere
Wirkrichtung, weil die Datenlage (echte Messung statt Lastprofil) eine
andere Herangehensweise verlangt.
"""

import math
from pathlib import Path

import yaml


class EBike:
    """
    Physikalisches Modell des E-Bikes (Masse, Luftwiderstand, Raddurchmesser).

    Attribute:
        masse_gesamt_kg (float): Gesamtmasse aus Fahrer + Rad
        cw_a (float):            cW-Wert * Stirnfläche in m^2
        radradius_m (float):     Radradius in Metern
    """

    RHO_LUFT = 1.225   # Luftdichte in kg/m^3 auf Meereshöhe (Konstante)
    G = 9.81            # Erdbeschleunigung in m/s^2

    def __init__(
        self,
        masse_fahrer_kg: float,
        masse_rad_kg: float,
        cw_a_m2: float,
        raddurchmesser_inch: float,
        rollwiderstandkoeffizient: float,
    ):
        self.masse_gesamt_kg = masse_fahrer_kg + masse_rad_kg
        self.cw_a = cw_a_m2
        self.radradius_m = (raddurchmesser_inch * 0.0254) / 2   # Zoll -> Meter, Durchmesser -> Radius
        self.rollwiderstandkoeffizient = rollwiderstandkoeffizient

    @classmethod
    def from_yaml(cls, pfad: str) -> "EBike":
        """Erzeugt ein EBike-Objekt aus einer YAML-Konfigurationsdatei."""
        config_path = Path(pfad)
        with config_path.open("r", encoding="utf-8") as datei:
            daten = yaml.safe_load(datei) or {}

        if not isinstance(daten, dict):
            raise ValueError(f"Ungültiges YAML-Format in {config_path}")

        defaults = {
            "masse_fahrer_kg": 70.0,
            "masse_rad_kg": 10.0,
            "cw_a_m2": 0.5625,
            "raddurchmesser_inch": 27.0,
            "rollwiderstandkoeffizient": 0.005,
        }
        defaults.update(daten)
        return cls(**defaults)

    def luftwiderstand_N(self, v_ms: float, luftdichte_kg_m3: float | None = None) -> float:
        """F_D = 0.5 * rho * cW*A * v^2"""
        rho = luftdichte_kg_m3 if luftdichte_kg_m3 is not None else self.RHO_LUFT
        return 0.5 * rho * self.cw_a * v_ms ** 2

    def hangabtriebskraft_N(self, phi_grad: float) -> float:
        """F_H = m * g * sin(phi)"""
        return self.masse_gesamt_kg * self.G * math.sin(math.radians(phi_grad))

    def beschleunigungskraft_N(self, a_ms2: float) -> float:
        """F_a = m * a"""
        return self.masse_gesamt_kg * a_ms2
    
    def rollwiderstand_N(self, phi_grad: float) -> float:
        """F_R = c_R * m * g * cos(phi)"""
        return self.rollwiderstandkoeffizient * self.masse_gesamt_kg * self.G * math.cos(math.radians(phi_grad))    

    def antriebskraft_N(self, v_ms: float, a_ms2: float, phi_grad: float, luftdichte_kg_m3: float|None = None) -> float:
        """Kräftegleichgewicht: F_Antrieb = F_Luftwiderstand + F_Hangabtrieb + F_Beschleunigung"""
        return (
            self.luftwiderstand_N(v_ms, luftdichte_kg_m3)
            + self.hangabtriebskraft_N(phi_grad)
            + self.beschleunigungskraft_N(a_ms2)
            + self.rollwiderstand_N(phi_grad)
        )

    def leistung_W(self, kraft_N: float, v_ms: float) -> float:
        return kraft_N * v_ms

    def drehmoment_Nm(self, kraft_N: float) -> float:
        """Drehmoment am Antriebsrad = Kraft * Radradius"""
        return kraft_N * self.radradius_m

    def punkt_auswerten(self, v_ms: float, a_ms2: float, phi_grad: float, luftdichte_kg_m3: float | None = None) -> dict:
        """Berechnet für einen gegebenen Fahrzustand (v, a, phi) Kraft,
        Leistung und Drehmoment auf einmal. Wird pro GPS-Punkt aufgerufen."""
        F = self.antriebskraft_N(v_ms, a_ms2, phi_grad, luftdichte_kg_m3)
        F_roll = self.rollwiderstand_N(phi_grad)
        return {
            "kraft_N": F,
            "leistung_W": self.leistung_W(F, v_ms),
            "drehmoment_Nm": self.drehmoment_Nm(F),
        }

    def __str__(self) -> str:
        return (
            f"EBike(m={self.masse_gesamt_kg:.1f} kg, cW*A={self.cw_a:.3f} m², "
            f"r_Rad={self.radradius_m:.3f} m)"
        )
