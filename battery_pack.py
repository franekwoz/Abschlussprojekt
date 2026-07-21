"""
battery_pack.py
----------------
Konkrete Basisimplementierung eines Akku-Packs, nach dem Ersatzschaltbild-
Modell aus Kapitel 09.2/09.3 der Vorlesung: eine ideale Spannungsquelle
(Leerlaufspannung U_OC) in Reihe mit einem Innenwiderstand R_int.

Gegenüber der reinen Kurs-Version (09.3/09.4) um zwei Dinge erweitert,
weil das laut Abschlussprojekt-Angabe explizit gefordert ist:
1. Logging statt stiller Begrenzung, wenn der SoC über 100%/unter 0% fallen würde
2. Ein Fehler (Exception), wenn versucht wird, einen bereits leeren Akku
   weiter zu entladen, statt die Simulation einfach unbemerkt weiterlaufen
   zu lassen

Die Attributnamen (C_nom, R_int, soc, Vmin, Vmax) sind bewusst identisch
zur Vorlesung gewählt, damit die Klasse kompatibel zum dort gezeigten
Modell bleibt.
"""

import logging
import math
from battery_base import BatteryBase
from akkutemperatur import (
    temperaturkorrigierter_innenwiderstand_ohm,
    temperaturkorrigierte_kapazitaet_as,
)

logger = logging.getLogger(__name__)


class BatteryPack(BatteryBase):
    """
    Einfaches Akku-Modell mit linearer Leerlaufspannungs-Kennlinie.

    Attribute:
        C_nom (float):  Nennkapazität in Amperesekunden (As)
        R_int (float):  Innenwiderstand in Ohm
        soc (float):    Ladezustand (State of Charge), 0.0 .. 1.0
        Vmin (float):   Spannung bei SoC = 0
        Vmax (float):   Spannung bei SoC = 1
    """

    def __init__(
        self,
        capacity_nom_Ah: float,
        internal_resistance_mOhm: float = 80.0,
        initial_soc: float = 1.0,
        Vmin: float = 32.0,
        Vmax: float = 42.0,
    ):
        if capacity_nom_Ah <= 0:
            raise ValueError("capacity_nom_Ah muss > 0 sein.")
        if not math.isfinite(initial_soc):
            raise ValueError("initial_soc muss eine endliche Zahl sein.")

        self.C_nom = capacity_nom_Ah * (60.0 * 60.0)   # Ah -> As (SI-Einheit)
        if initial_soc < 0.0 or initial_soc > 1.0:
            logger.warning(
                "Initialer Ladezustand %.3f liegt außerhalb von [0, 1] und wird begrenzt.",
                initial_soc,
            )
        self.soc = max(0.0, min(initial_soc, 1.0))       # Anfangs-SoC auf [0,1] begrenzen
        self.R_int = internal_resistance_mOhm * 1e-3      # mOhm -> Ohm

        self.Vmin = Vmin
        self.Vmax = Vmax
        self.temperature_c: float | None = None

    # ------------------------------------------------------------------
    # _ocv() ist KEIN Bestandteil des Kurs-Interfaces, sondern eine
    # zusätzliche private Hilfsmethode: sie kapselt nur die Berechnung der
    # Leerlaufspannung, damit Subklassen (LiPo/NMC) NUR diese eine Stelle
    # überschreiben müssen und nicht die komplette voltage()-Methode
    # duplizieren. Das Verhalten nach außen (voltage()) bleibt exakt
    # gleich wie im Kurs-Vorbild.
    # ------------------------------------------------------------------
    def set_temperatur(self, temperature_c: float | None = None) -> None:
        """Aktualisiert die aktuelle Akkutemperatur, die R_int/C_nom skaliert."""
        self.temperature_c = temperature_c
    
    def _ocv(self, soc: float) -> float:
        """Leerlaufspannung: linear zwischen Vmin (SoC=0) und Vmax (SoC=1)."""
        return self.Vmin + soc * (self.Vmax - self.Vmin)

    def voltage(self, current: float = 0.0) -> float:
        """Klemmenspannung unter Last: U = U_OC(SoC) - R_int * I
        Erweiterung: R_int wird temperaturkorrigiert
        """
        r_int = self.R_int
        if self.temperature_c is not None:
            r_int = temperaturkorrigierter_innenwiderstand_ohm(self.R_int, self.temperature_c)
        return self._ocv(self.soc) - r_int * current

   
    def apply_current(self, current: float, duration: float) -> None:
        """
        Aktualisiert den SoC nach der Formel aus Kapitel 09.2:
        SoC_(k+1) = SoC_k - (I * dt) / C_nom

        Erweiterung ggü. Kurs-Vorbild (siehe Modulkopf): Logging bei
        Grenzfällen + Abbruch bei vollständig entladenem Akku.
        """
        if not math.isfinite(current):
            raise ValueError("current muss eine endliche Zahl sein.")
        if not math.isfinite(duration):
            raise ValueError("duration muss eine endliche Zahl sein.")
        if duration < 0:
            raise ValueError("duration muss >= 0 sein.")

        if self.is_empty() and current > 0:
            logger.error("Akku ist leer (SoC = 0%%) - Entladung nicht mehr möglich.")
            raise RuntimeError("Akku vollständig entladen (SoC = 0).")

        c_nom = self.C_nom
        if self.temperature_c is not None:
            c_nom = temperaturkorrigierte_kapazitaet_as(self.C_nom, self.temperature_c)

        dsoc = -(current * duration) / c_nom
        neuer_soc = self.soc + dsoc

        if neuer_soc > 1.0:
            logger.warning(
                "Ladezustand würde 100%% überschreiten - wird begrenzt "
                "(überschüssige Energie müsste z.B. in einem Bremswiderstand dissipiert werden)."
            )
        elif neuer_soc < 0.0:
            logger.warning("Ladezustand würde unter 0%% fallen - wird auf 0%% begrenzt.")

        self.soc = max(0.0, min(neuer_soc, 1.0))   # SoC hart auf [0, 1] begrenzen

    def is_empty(self) -> bool:
        return self.soc <= 0.0 + 1e-9

    def is_full(self) -> bool:
        return self.soc >= 1.0 - 1e-9

    def __str__(self) -> str:
        return f"{type(self).__name__}(SoC={self.soc * 100:.1f}%, V={self.voltage():.2f} V)"
