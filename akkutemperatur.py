"""
akkutemperatur.py
-----------------
Modelliert den Einfluss der Akkutemperatur auf Innenwiderstand und
nutzbare Kapazität: kältere Temperaturen erhöhen den Innenwiderstand und
verringern die nutzbare Kapazität, jeweils relativ zu einer Referenz-
temperatur von 25°C. eide Effekte
sind auf einen Mindestfaktor begrenzt, damit bei extremen Temperaturen
keine unrealistische Extrapolation entsteht.
"""

REFERENZ_TEMPERATUR_C = 25.0  # °C
WIDERSTAND_TEMP_KOEFFIZIENT_PRO_GRAD = 0.02   # +2% Widerstand pro Grad kälter als Referenz
KAPAZITAET_TEMP_KOEFFIZIENT_PRO_GRAD = 0.008  # -0.8% Kapazität pro Grad kälter als Referenz
MIN_WIDERSTAND_FAKTOR = 0.5
MIN_KAPAZITAET_FAKTOR = 0.5

def temperaturkorrigierter_innenwiderstand_ohm( referenz_innenwiderstand_ohm: float, temperatur_c: float) -> float:
    """Skaliert einen Referenz-Innenwiderstand  für die gegebene Temperatur."""
    temperaturdifferenz = REFERENZ_TEMPERATUR_C - temperatur_c
    faktor = 1.0 + temperaturdifferenz * WIDERSTAND_TEMP_KOEFFIZIENT_PRO_GRAD
    faktor = max(faktor, MIN_WIDERSTAND_FAKTOR)
    return referenz_innenwiderstand_ohm * faktor

def temperaturkorrigierte_kapazitaet_as( referenz_kapazitaet_ah: float, temperatur_c: float) -> float:
    """Skaliert eine Referenz-Kapazität (bei 25°C) für die gegebene Temperatur."""
    temperaturdifferenz = max(REFERENZ_TEMPERATUR_C - temperatur_c, 0.0) # nur Kälte wirkt sich negativ aus
    faktor = 1.0 - temperaturdifferenz * KAPAZITAET_TEMP_KOEFFIZIENT_PRO_GRAD
    faktor = max(faktor, MIN_KAPAZITAET_FAKTOR)
    return referenz_kapazitaet_ah * faktor

