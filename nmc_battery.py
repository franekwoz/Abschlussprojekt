"""
nmc_battery.py
--------------
Analog zu lipo_battery.py: erbt von BatteryPack, überschreibt nur die
Leerlaufspannungs-Kennlinie mit den NMC-spezifischen Messwerten.
"""

import numpy as np
from battery_pack import BatteryPack


class NMCBatteryPack(BatteryPack):
    """NMC-Akku (10 Zellen seriell, Innenwiderstand 7 mOhm pro Zelle)."""

    _SOC_STUETZSTELLEN = np.array(
        [0.00, 0.04, 0.09, 0.13, 0.17, 0.21, 0.26, 0.30, 0.40, 0.52, 0.64, 0.76, 0.88, 1.00]
    )
    _UOC_STUETZSTELLEN = np.array(
        [32.00, 32.61, 33.17, 33.85, 34.24, 34.66, 35.39, 35.65, 36.65, 37.64, 38.91, 40.14, 41.08, 42.00]
    )

    def __init__(self, capacity_nom_Ah: float, initial_soc: float = 1.0, n_parallel: int = 1):
        super().__init__(
            capacity_nom_Ah=capacity_nom_Ah * n_parallel,
            internal_resistance_mOhm=(7.0 * 10) / n_parallel,
            initial_soc=initial_soc,
            Vmin=32.0,
            Vmax=42.0,
        )

    def _ocv(self, soc: float) -> float:
        return float(np.interp(soc, self._SOC_STUETZSTELLEN, self._UOC_STUETZSTELLEN))
