"""
bremswiderstand.py
-------------------
Berechnet die Leistung, die über einen Bremswiderstand als Wärme
dissipiert werden muss, wenn beim Bremsen/Bergabfahren mehr Ladestrom
anfällt, als der Akku noch aufnehmen kann (der Ladezustand würde über
100% steigen). Reine P = U * I - Umrechnung von "überschüssigem" Strom
in Leistung.
"""
import math

def dissipierte_leistung_W(ueberschuss_strom_a: float, spannung_v: float) -> float:
    """Leistung, die über einen Bremswiderstand als Wärme dissipiert wird."""
    if not math.isfinite(ueberschuss_strom_a) or not math.isfinite(spannung_v):
        raise ValueError("ueberschuss_strom_a und spannung_v müssen endliche Werte sein.")
    return spannung_v * ueberschuss_strom_a
