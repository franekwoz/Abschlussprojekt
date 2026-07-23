"""Wiederverwendbare Orchestrierung der vorhandenen Simulationsklassen."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import numpy as np
import pandas as pd

from ebike import EBike
from ebike_simulator import EBikeSimulator
from gps_track import GPSTrack
from lipo_battery import LiPoBatteryPack
from motor import Motor
from nmc_battery import NMCBatteryPack
from plot_utils import plots_erstellen
from speed_smoothing import SpeedSmoothingConfig


@dataclass
class SimulationResult:
    run_id: str
    output_dir: Path
    track: GPSTrack
    simulations: dict[str, pd.DataFrame]
    summaries: dict[str, dict]
    smoothing: SpeedSmoothingConfig
    map_paths: dict[str, Path]


def _json_compatible(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return float(value.total_seconds())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    if pd.isna(value):
        return None
    return str(value)


def _summary(df: pd.DataFrame, initial_soc: float, expected_point_count: int) -> dict[str, object]:
    dt = pd.to_numeric(df["dt_s"], errors="coerce").fillna(0.0).clip(lower=0.0)
    power = pd.to_numeric(df["leistung_W"], errors="coerce").fillna(0.0)
    traction = float((power.clip(lower=0.0) * dt).sum() / 3600.0)
    braking = float(((-power.clip(upper=0.0)) * dt).sum() / 3600.0)
    simulated_point_count = int(len(df))
    final_soc = float(pd.to_numeric(df["soc"], errors="coerce").iloc[-1])
    summary = {
        "final_soc_percent": final_soc * 100.0,
        "soc_consumption_percent": (initial_soc - final_soc) * 100.0,
        "max_power_W": float(pd.to_numeric(df["leistung_W"], errors="coerce").max()),
        "max_motor_current_A": float(pd.to_numeric(df["motorstrom_A"], errors="coerce").max()),
        "max_torque_Nm": float(pd.to_numeric(df["drehmoment_Nm"], errors="coerce").max()),
        "minimum_voltage_V": float(pd.to_numeric(df["spannung_V"], errors="coerce").min()),
        "traction_energy_Wh": traction,
        "braking_energy_Wh": braking,
        "completed_route": simulated_point_count == expected_point_count,
        "simulated_point_count": simulated_point_count,
        "expected_point_count": int(expected_point_count),
        "end_point": int(simulated_point_count - 1) if simulated_point_count else None,
    }
    return _json_compatible(summary)  # type: ignore[return-value]


def _route_summary(track: GPSTrack) -> dict[str, object]:
    df = track.df
    smoothing = track.smoothing_kennzahlen()
    summary = {
        "total_distance_km": float(track.gesamtstrecke_km()),
        "duration_s": float(track.gesamtzeit_s()),
        "gps_point_count": int(len(df)),
        "average_speed_kmh": float(track.durchschnittsgeschwindigkeit_kmh()),
        "max_raw_speed_kmh": smoothing.get("max_rohgeschwindigkeit_kmh"),
        "max_active_speed_kmh": smoothing.get("max_aktive_geschwindigkeit_kmh"),
        "elevation_gain_m": float(track.hoehenmeter_anstieg()),
        "short_interval_count": int(df["filter_kurzes_intervall"].sum()) if "filter_kurzes_intervall" in df.columns else None,
        "large_gap_count": int(df["filter_grosse_zeitluecke"].sum()) if "filter_grosse_zeitluecke" in df.columns else None,
        "speed_outlier_count": int(df["filter_geschwindigkeitsausreisser"].sum()) if "filter_geschwindigkeitsausreisser" in df.columns else None,
        "valid_smoothing_support_point_count": int(df["filter_gueltige_stuetzstelle"].sum()) if "filter_gueltige_stuetzstelle" in df.columns else None,
    }
    return _json_compatible(summary)  # type: ignore[return-value]


def _battery_options_metadata(options: dict) -> dict[str, object]:
    return _json_compatible(
        {
            "lipo": bool(options.get("lipo", False)),
            "nmc": bool(options.get("nmc", False)),
            "capacity_ah": float(options.get("capacity_ah", 0.0)),
            "initial_soc": float(options.get("initial_soc", 0.0)),
            "n_parallel": int(options.get("n_parallel", 1)),
        }
    )  # type: ignore[return-value]


def _smoothing_metadata(config: SpeedSmoothingConfig) -> dict[str, object]:
    return _json_compatible(asdict(config))  # type: ignore[return-value]


def _write_metadata(
    output_dir: Path,
    *,
    run_id: str,
    source_file_name: str,
    bike_config: dict,
    battery_options: dict,
    smoothing_config: SpeedSmoothingConfig,
    track: GPSTrack,
    simulations: dict[str, pd.DataFrame],
    summaries: dict[str, dict],
) -> None:
    metadata = {
        "schema_version": 2,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file_name": source_file_name,
        "bike_config": _json_compatible(bike_config),
        "battery_options": _battery_options_metadata(battery_options),
        "smoothing": _smoothing_metadata(smoothing_config),
        "route_summary": _route_summary(track),
        "summaries": _json_compatible(summaries),
        "plot_files": _json_compatible(
            {
                "elevation": "plot/hoehenprofil_fahrt.png",
                "lipo": "plot/zeitverlauf_lipo.png",
                "nmc": "plot/zeitverlauf_nmc.png",
                "soc_comparison": "plot/ladezustand_vergleich.png",
                "speed_comparison": "plot/geschwindigkeit_roh_geglaettet.png",
            }
        ),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    track.df.to_csv(output_dir / "track.csv", index=False)
    for name, df in simulations.items():
        df.to_csv(output_dir / f"simulation_{name.lower()}.csv", index=False)


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
    track_path = Path(track_path)
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
        summaries[name] = _summary(df, float(options["initial_soc"]), len(track.df))
        if generate_outputs:
            path = out / f"karte_soc_{name.lower()}.html"; track.karte_erstellen(df, "soc", str(path)); maps[name] = path
    if not simulations: raise ValueError("Mindestens ein Akkutyp muss ausgewaehlt sein.")
    if generate_outputs:
        route = out / "karte_strecke.html"; track.karte_erstellen(farbwert="geschwindigkeit_ms", ausgabepfad=str(route)); maps["route"] = route
        plots_erstellen(track.df, simulations, str(out / "plot"))
        _write_metadata(
            out,
            run_id=run_id,
            source_file_name=track_path.name,
            bike_config=bike_config,
            battery_options=options,
            smoothing_config=smoothing_config,
            track=track,
            simulations=simulations,
            summaries=summaries,
        )
    return SimulationResult(run_id, out, track, simulations, summaries, smoothing_config, maps)
