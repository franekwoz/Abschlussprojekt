"""
battery_base.py
----------------
Abstract Base Class (ABC) für alle Akku-Modelle.

Entspricht dem Vorbild aus Vorlesungskapitel 09.4 (Anwendung der OOP,
Abschnitt "Abstract Base Classes"): Eine ABC kann nicht direkt instanziiert
werden, sondern legt nur fest, WELCHE Methoden jede konkrete Akku-Klasse
haben MUSS (das "Interface"). Das garantiert, dass z.B. der EBikeSimulator
mit jedem beliebigen Akkutyp arbeiten kann, ohne zu wissen, um welchen
konkreten Typ es sich handelt (Polymorphismus).
"""

from abc import ABC, abstractmethod


class BatteryBase(ABC):
    """
    Gemeinsames Interface aller Akku-Modelle.

    Jede konkrete Akku-Klasse (z.B. BatteryPack, LiPoBatteryPack, ...)
    MUSS diese drei Methoden implementieren:
    - __init__:       Akku mit seinen Kenngrößen initialisieren
    - apply_current:  Ladezustand nach einem Zeitschritt aktualisieren
    - voltage:        aktuelle Klemmenspannung zurückgeben
    """

    @abstractmethod
    def __init__(self, capacity_nom_Ah: float, initial_soc: float = 1.0):
        """Muss von jeder Subklasse implementiert werden, u.a. mit den
        Attributen C_nom (Kapazität in As), soc, R_int, Vmin, Vmax."""
        raise NotImplementedError

    @abstractmethod
    def apply_current(self, current: float, duration: float) -> None:
        """Aktualisiert den Ladezustand (SoC) nach einem Zeitschritt."""
        raise NotImplementedError

    @abstractmethod
    def voltage(self, current: float = 0.0) -> float:
        """Gibt die Klemmenspannung des Akkus unter Last zurück."""
        raise NotImplementedError
