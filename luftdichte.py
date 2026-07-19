"""luftdichte.py




"""

import math 

LUFTDRUCK_MEERESHOEHE_PA = 101_325.0
SPEZIFISCHE_GASKONSTANTE_LUFT = 287.05 # J/(kg·K)
G = 9.81 #Erdbeschleunigung in m/s²
KELVIN_OFFSET = 273.15 # Umrechnung von Celsius in Kelvin

def luftdichte_kg_m3(hoehe_m: float, temperatur_c: float) -> float:
    """Schätzt die Luftdichte (kg/m^3) aus Höhe über dem Meeresspiegel und Temperatur."""
    if not math.isfinite(hoehe_m) or not math.isfinite(temperatur_c):
        raise ValueError("hoehe_m und temperatur_c müssen endliche Zahlen sein.") 
    
    temperatur_k = temperatur_c + KELVIN_OFFSET
    if temperatur_k <= 0:
        raise ValueError("Die temperatur_k muss größer als 0 sein.")
    
    #Es wurden Fehlermeldungen eingebaut, die sicherstellen, 
    #dass die Eingabewerte für Höhe und Temperatur gültig sind.
    
    """
    barometrische Höhenformel: p(h) = p · e^(-g·h / (R·T)), 
    sie beschreibt den Zusammenhang zwischen Luftdruck p(h) in Höhe h und
    dem Luftdruck p auf Meereshöhe bei gegebener Temperatur T. 
    Sie beschreibt, wie der Luftdruck mit zunehmender Höhe abnimmt.
    """
    luftdruck_pa = LUFTDRUCK_MEERESHOEHE_PA * math.exp(-G * hoehe_m / (SPEZIFISCHE_GASKONSTANTE_LUFT * temperatur_k))
    return luftdruck_pa / (SPEZIFISCHE_GASKONSTANTE_LUFT * temperatur_k)


