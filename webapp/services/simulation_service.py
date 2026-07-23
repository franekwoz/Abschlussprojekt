"""Wiederverwendbare Orchestrierung der vorhandenen Simulationsklassen."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
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
from wetterdaten import wetterdaten_fuer_orte


@dataclass
class SimulationResult:
    run_id: str
    output_dir: Path
    track: GPSTrack
    simulations: dict[str, pd.DataFrame]
    summaries: dict[str, dict]
    smoothing: SpeedSmoothingConfig
    map_paths: dict[str, Path]
    orte: pd.DataFrame | None = None


def _json_value(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value


def _series_mit_werten(orte: pd.DataFrame | None, spalte: str) -> pd.Series:
    if orte is None or spalte not in orte.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(orte[spalte], errors="coerce").dropna()


def _location_entry(orte: pd.DataFrame, row: pd.Series) -> dict:
    eintrag: dict[str, object | None] = {
        "track_index": None,
        "latitude": None,
        "longitude": None,
        "address": None,
        "temperature_C": None,
        "wind_speed_kmh": None,
        "precipitation_mm": None,
        "humidity_percent": None,
    }
    if "index" in orte.columns:
        eintrag["track_index"] = _json_value(row.get("index"))
    if "lat" in orte.columns:
        eintrag["latitude"] = _json_value(row.get("lat"))
    if "lon" in orte.columns:
        eintrag["longitude"] = _json_value(row.get("lon"))
    if "adresse" in orte.columns:
        eintrag["address"] = _json_value(row.get("adresse"))
    if "wetter_temperatur_c" in orte.columns:
        eintrag["temperature_C"] = _json_value(row.get("wetter_temperatur_c"))
    if "wetter_wind_kmh" in orte.columns:
        eintrag["wind_speed_kmh"] = _json_value(row.get("wetter_wind_kmh"))
    if "wetter_niederschlag_mm" in orte.columns:
        eintrag["precipitation_mm"] = _json_value(row.get("wetter_niederschlag_mm"))
    if "wetter_luftfeuchte_pct" in orte.columns:
        eintrag["humidity_percent"] = _json_value(row.get("wetter_luftfeuchte_pct"))
    return eintrag


def _location_weather_points(orte: pd.DataFrame | None) -> list[dict]:
    if orte is None or len(orte) == 0:
        return []
    return [_location_entry(orte, row) for _, row in orte.iterrows()]


def _weather_summary(orte: pd.DataFrame | None) -> dict:
    zusammenfassung: dict[str, object] = {"available": False, "sampled_points": 0, "source": "Open-Meteo"}
    temperatur = _series_mit_werten(orte, "wetter_temperatur_c")
    wind = _series_mit_werten(orte, "wetter_wind_kmh")
    niederschlag = _series_mit_werten(orte, "wetter_niederschlag_mm")
    luftfeuchte = _series_mit_werten(orte, "wetter_luftfeuchte_pct")

    if temperatur.empty and wind.empty and niederschlag.empty and luftfeuchte.empty:
        return zusammenfassung

    zusammenfassung["available"] = True
    zusammenfassung["sampled_points"] = int(len(orte)) if orte is not None else 0
    if not temperatur.empty:
        zusammenfassung["temperature_min_C"] = float(temperatur.min())
        zusammenfassung["temperature_average_C"] = float(temperatur.mean())
        zusammenfassung["temperature_max_C"] = float(temperatur.max())
    if not wind.empty:
        zusammenfassung["wind_speed_average_kmh"] = float(wind.mean())
        zusammenfassung["wind_speed_max_kmh"] = float(wind.max())
    if not niederschlag.empty:
        zusammenfassung["precipitation_average_mm"] = float(niederschlag.mean())
        zusammenfassung["precipitation_max_mm"] = float(niederschlag.max())
    if not luftfeuchte.empty:
        zusammenfassung["humidity_average_percent"] = float(luftfeuchte.mean())
    return zusammenfassung


def _location_summary(orte: pd.DataFrame | None) -> dict:
    zusammenfassung: dict[str, object] = {
        "available": False,
        "sampled_points": 0,
        "provider": "Nominatim / OpenStreetMap",
    }
    if orte is None or len(orte) == 0:
        return zusammenfassung

    zusammenfassung["available"] = True
    zusammenfassung["sampled_points"] = int(len(orte))
    zusammenfassung["start"] = _location_entry(orte, orte.iloc[0])
    zusammenfassung["end"] = _location_entry(orte, orte.iloc[-1])
    return zusammenfassung


def _feature_status(mit_orten_und_wetter: bool, orte: pd.DataFrame | None) -> dict:
    sampled_points = int(len(orte)) if orte is not None else 0
    hat_adressen = orte is not None and "adresse" in orte.columns and orte["adresse"].notna().any()
    hat_wetter = any(
        not _series_mit_werten(orte, spalte).empty
        for spalte in (
            "wetter_temperatur_c",
            "wetter_wind_kmh",
            "wetter_niederschlag_mm",
            "wetter_luftfeuchte_pct",
        )
    )

    if not mit_orten_und_wetter:
        message = "Wetterdaten und Ortsinformationen wurden für diesen Lauf nicht geladen."
        return {
            "reverse_geocoding": {"state": "inactive", "description": message, "provider": "Nominatim / OpenStreetMap"},
            "weather": {"state": "inactive", "description": message, "provider": "Open-Meteo"},
        }

    reverse_state = "active" if hat_adressen else "available"
    weather_state = "active" if hat_wetter else "available"
    return {
        "reverse_geocoding": {
            "state": reverse_state,
            "description": (
                f"Für {sampled_points} Punkte entlang der Strecke wurden Adressen über Nominatim / OpenStreetMap ermittelt."
                if reverse_state == "active"
                else "Wetter- oder Ortsinformationen konnten nicht geladen werden. Die Simulation wurde trotzdem erfolgreich durchgeführt."
            ),
            "provider": "Nominatim / OpenStreetMap",
        },
        "weather": {
            "state": weather_state,
            "description": (
                f"Für {sampled_points} Punkte entlang der Strecke wurden historische Wetterdaten von Open-Meteo geladen."
                if weather_state == "active"
                else "Wetter- oder Ortsinformationen konnten nicht geladen werden. Die Simulation wurde trotzdem erfolgreich durchgeführt."
            ),
            "provider": "Open-Meteo",
        },
    }


def _summary(df: pd.DataFrame, initial_soc: float, total_track_points: int) -> dict:
    dt = df["dt_s"].clip(lower=0)
    power = df["leistung_W"]
    traction = (power.clip(lower=0) * dt).sum() / 3600
    final_soc = float(df.soc.iloc[-1] * 100)
    processed_points = int(len(df))
    total_track_points = int(total_track_points)
    completed_route = processed_points == total_track_points
    abort_reason = None
    if not completed_route:
        abort_reason = "battery_empty" if final_soc <= 0 else "route_incomplete"
    return {
        "final_soc_percent": final_soc,
        "soc_consumption_percent": float((initial_soc - df.soc.iloc[-1]) * 100),
        "max_power_W": float(power.max()),
        "max_motor_current_A": float(df.motorstrom_A.max()),
        "max_torque_Nm": float(df.drehmoment_Nm.max()),
        "minimum_voltage_V": float(df.spannung_V.min()),
        "traction_energy_Wh": float(traction),
        "braking_energy_Wh": float((-power.clip(upper=0) * dt).sum() / 3600),
        "completed_route": completed_route,
        "processed_points": processed_points,
        "total_track_points": total_track_points,
        "completion_percent": float(max(0.0, min(100.0, (processed_points / total_track_points * 100) if total_track_points else 0.0))),
        "end_point": int(df.index[-1]),
        "abort_reason": abort_reason,
    }


def run_simulation(track_path: str | Path, bike_config: dict, smoothing_config: SpeedSmoothingConfig,
                   battery_options: dict | None = None, output_directory: str | Path | None = None,
                   generate_outputs: bool = True, mit_orten_und_wetter: bool = False,
                   anzahl_wegpunkte: int = 6) -> SimulationResult:
    """Run a fully isolated simulation; every battery object is newly created.

    mit_orten_und_wetter (bool): Fragt zusaetzlich per Reverse Geocoding
        (Nominatim) Adressen sowie passende Wetterdaten (Open-Meteo) fuer
        Start, Ziel und ein paar Zwischenpunkte entlang der Strecke ab.
        Benoetigt Internetzugriff und macht den Lauf durch das Rate-Limit
        von Nominatim (>= 1 Anfrage/Sekunde) spuerbar langsamer, daher per
        Default deaktiviert. Schlaegt die Abfrage fehl, bleibt orte einfach
        None - die eigentliche Simulation laeuft davon unbeeinflusst weiter.
    """
    options = {"lipo": True, "nmc": True, "capacity_ah": 10.0, "initial_soc": 1.0, "n_parallel": 1}
    options.update(battery_options or {})
    run_id = uuid.uuid4().hex
    out = Path(output_directory or Path("output") / "web" / run_id)
    run_id = out.name
    out.mkdir(parents=True, exist_ok=True)
    track = GPSTrack(track_path, smoothing_config=smoothing_config)
    if len(track.df) < 2: raise ValueError("Der GPS-Track braucht mindestens zwei Punkte.")

    orte = None
    if mit_orten_und_wetter:
        try:
            orte = track.orte_ermitteln(anzahl_wegpunkte=anzahl_wegpunkte)
            orte = wetterdaten_fuer_orte(orte, track.df)
        except Exception:
            # Kein Internetzugriff, Nominatim/Open-Meteo nicht erreichbar, ...
            # Die Simulation selbst soll davon nicht abhaengen.
            orte = None
    if orte is not None:
        track.orte = orte

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
        track.df.to_csv(out / "track.csv", index=False)
        for name, df in simulations.items():
            df.to_csv(out / f"simulation_{name.lower()}.csv", index=False)
        if orte is not None:
            orte.to_csv(out / "orte.csv", index=False)
        metadata = {
            "summaries": summaries,
            "smoothing": smoothing_config.__dict__,
            "feature_status": _feature_status(mit_orten_und_wetter, orte),
            "location_weather_points": _location_weather_points(orte),
            "weather_summary": _weather_summary(orte),
            "location_summary": _location_summary(orte),
        }
        (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return SimulationResult(run_id, out, track, simulations, summaries, smoothing_config, maps, orte)
