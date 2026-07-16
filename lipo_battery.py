"""
lipo_battery.py
----------------
Erbt von BatteryPack (wie lifepo4_battery.py in Kapitel 09.3 von der Kurs-
BatteryPack erbt) und überschreibt NUR die Leerlaufspannungs-Kennlinie.

Unterschied zum Kurs-Vorbild: Dort wird eine einfache Polynomfunktion
(SoC^0.3) verwendet. Für das Abschlussprojekt ist stattdessen eine reale,
tabellarische SoC->U_OC-Kennlinie aus dem Datenblatt vorgegeben, die per
linearer Interpolation zwischen den Stützstellen ausgewertet wird
(numpy.interp) - deshalb wird hier _ocv() überschrieben statt voltage()
direkt zu duplizieren.
"""

import numpy as np
from battery_pack import BatteryPack


class LiPoBatteryPack(BatteryPack):
    """LiPo-Akku (10 Zellen seriell, Innenwiderstand 8 mOhm pro Zelle)."""

    # Stützstellen der Kennlinie aus dem Datenblatt: SoC (0..1) -> U_OC (V)
    _SOC_STUETZSTELLEN = np.array(
        [0.00, 0.04, 0.09, 0.13, 0.17, 0.21, 0.26, 0.30, 0.40, 0.52, 0.64, 0.76, 0.88, 1.00]
    )
    _UOC_STUETZSTELLEN = np.array(
        [32.00, 35.87, 36.85, 37.56, 37.87, 38.28, 38.81, 39.05, 39.55, 40.27, 40.70, 41.16, 41.65, 42.00]
    )

    def __init__(self, capacity_nom_Ah: float, initial_soc: float = 1.0, n_parallel: int = 1):
        # n_parallel: Anzahl paralleler Zellstränge (Pack ist "10SxP")
        # -> erhöht die Gesamtkapazität, verringert den Innenwiderstand
        super().__init__(
            capacity_nom_Ah=capacity_nom_Ah * n_parallel,
            internal_resistance_mOhm=(8.0 * 10) / n_parallel,   # 10 Zellen seriell, n parallel
            initial_soc=initial_soc,
            Vmin=32.0,
            Vmax=42.0,
        )

    def _ocv(self, soc: float) -> float:
        """Überschreibt die lineare Kennlinie der Basisklasse durch lineare
        Interpolation der realen LiPo-Messwerte."""
        return float(np.interp(soc, self._SOC_STUETZSTELLEN, self._UOC_STUETZSTELLEN))
