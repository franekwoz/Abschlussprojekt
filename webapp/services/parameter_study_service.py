"""Ein-Faktor-Parameterstudien auf Basis des gemeinsamen Simulationsdienstes."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .simulation_service import run_simulation
from speed_smoothing import SpeedSmoothingConfig

VALID_PARAMETERS = {"masse_fahrer_kg", "masse_rad_kg", "cw_a_m2", "raddurchmesser_inch", "rollwiderstandkoeffizient"}
def run_parameter_study(track_path, bike_config, smoothing_config: SpeedSmoothingConfig, parameter_name, minimum, maximum, steps, battery_options, output_directory):
    if parameter_name not in VALID_PARAMETERS: raise ValueError("Unbekannte Fahrrad-Eigenschaft.")
    if not 2 <= int(steps) <= 50 or not float(minimum) < float(maximum): raise ValueError("Ungültiger Wertebereich oder Schrittanzahl.")
    rows=[]
    for value in np.linspace(float(minimum), float(maximum), int(steps)):
        config=dict(bike_config); config[parameter_name]=float(value)
        result=run_simulation(track_path, config, smoothing_config, battery_options, output_directory, generate_outputs=False)
        for name, summary in result.summaries.items():
            rows.append({"parameter_name":parameter_name,"parameter_value":value,"battery_type":name,
                         "smoothing_enabled":smoothing_config.enabled,"total_distance_km":result.track.gesamtstrecke_km(),
                         "duration_s":result.track.gesamtzeit_s(),"average_speed_kmh":result.track.durchschnittsgeschwindigkeit_kmh(), **summary})
    return pd.DataFrame(rows)
