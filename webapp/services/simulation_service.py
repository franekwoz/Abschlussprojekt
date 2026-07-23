"""Wiederverwendbare Orchestrierung der vorhandenen Simulationsklassen."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import uuid
import pandas as pd
import json
from ebike import EBike
from motor import Motor
from gps_track import GPSTrack
from speed_smoothing import SpeedSmoothingConfig
from lipo_battery import LiPoBatteryPack
from nmc_battery import NMCBatteryPack
from ebike_simulator import EBikeSimulator
from plot_utils import plots_erstellen


@dataclass
class SimulationResult:
    run_id: str
    output_dir: Path
    track: GPSTrack
    simulations: dict[str, pd.DataFrame]
    summaries: dict[str, dict]
    smoothing: SpeedSmoothingConfig
    map_paths: dict[str, Path]


def _summary(df: pd.DataFrame, initial_soc: float) -> dict:
    dt = df["dt_s"].clip(lower=0)
    power = df["leistung_W"]
    traction = (power.clip(lower=0) * dt).sum() / 3600
    return {"final_soc_percent": float(df.soc.iloc[-1] * 100),
            "soc_consumption_percent": float((initial_soc - df.soc.iloc[-1]) * 100),
            "max_power_W": float(power.max()), "max_motor_current_A": float(df.motorstrom_A.max()),
            "max_torque_Nm": float(df.drehmoment_Nm.max()), "minimum_voltage_V": float(df.spannung_V.min()),
            "traction_energy_Wh": float(traction),
            "braking_energy_Wh": float((-power.clip(upper=0) * dt).sum() / 3600),
            "completed_route": bool(len(df) > 0), "end_point": int(len(df) - 1)}


def run_simulation(track_path: str | Path, bike_config: dict, smoothing_config: SpeedSmoothingConfig,
                   battery_options: dict | None = None, output_directory: str | Path | None = None,
                   generate_outputs: bool = True) -> SimulationResult:
    """Run a fully isolated simulation; every battery object is newly created."""
    options = {"lipo": True, "nmc": True, "capacity_ah": 10.0, "initial_soc": 1.0, "n_parallel": 1}
    options.update(battery_options or {})
    run_id = uuid.uuid4().hex
    out = Path(output_directory or Path("output") / "web" / run_id)
    run_id = out.name
    out.mkdir(parents=True, exist_ok=True)
    track = GPSTrack(track_path, smoothing_config=smoothing_config)
    if len(track.df) < 2: raise ValueError("Der GPS-Track braucht mindestens zwei Punkte.")
    bike, motor = EBike(**bike_config), Motor()
    classes = {"LiPo": LiPoBatteryPack, "NMC": NMCBatteryPack}
    selected = {"LiPo": options["lipo"], "NMC": options["nmc"]}
    simulations, summaries, maps = {}, {}, {}
    for name, cls in classes.items():
        if not selected[name]: continue
        battery = cls(float(options["capacity_ah"]), float(options["initial_soc"]), int(options["n_parallel"]))
        df = EBikeSimulator(track, bike, motor, battery).simulate()
        simulations[name] = df
        summaries[name] = _summary(df, float(options["initial_soc"]))
        if generate_outputs:
            path = out / f"karte_soc_{name.lower()}.html"; track.karte_erstellen(df, "soc", str(path)); maps[name] = path
    if not simulations: raise ValueError("Mindestens ein Akkutyp muss ausgewaehlt sein.")
    if generate_outputs:
        route = out / "karte_strecke.html"; track.karte_erstellen(farbwert="geschwindigkeit_ms", ausgabepfad=str(route)); maps["route"] = route
        plots_erstellen(track.df, simulations, str(out / "plot"))
        track.df.to_csv(out / "track.csv", index=False)
        import json
        for name, df in simulations.items(): df.to_csv(out / f"simulation_{name.lower()}.csv", index=False)
        (out / "metadata.json").write_text(json.dumps({"summaries": summaries, "smoothing": smoothing_config.__dict__}), encoding="utf-8")
        track.df.to_csv(out / "track.csv", index=False)
        for name, df in simulations.items():
            df.to_csv(out / f"simulation_{name.lower()}.csv", index=False)
        (out / "metadata.json").write_text(json.dumps({"summaries": summaries, "smoothing": smoothing_config.__dict__}), encoding="utf-8")
    return SimulationResult(run_id, out, track, simulations, summaries, smoothing_config, maps)
