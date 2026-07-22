import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ebike import EBike
from ebike_simulator import EBikeSimulator
from gps_track import GPSTrack
from lipo_battery import LiPoBatteryPack
from motor import Motor
from speed_smoothing import SpeedSmoothingConfig


def _lon_delta_fuer_meter(meter: float, lat_grad: float = 47.58) -> float:
    meter_pro_grad_lon = 111_320.0 * math.cos(math.radians(lat_grad))
    return meter / meter_pro_grad_lon


def _csv_erstellen(path: Path, zeiten: list[datetime], meter_pro_intervall: list[float]) -> None:
    lat = 47.58
    lon = 12.17
    ele = 500.0

    rows = []
    rows.append(
        {
            "lat": lat,
            "lon": lon,
            "ele": ele,
            "time": zeiten[0].isoformat().replace("+00:00", "Z"),
            "temperature": 20.0,
        }
    )

    for i in range(1, len(zeiten)):
        lon += _lon_delta_fuer_meter(meter_pro_intervall[i])
        rows.append(
            {
                "lat": lat,
                "lon": lon,
                "ele": ele,
                "time": zeiten[i].isoformat().replace("+00:00", "Z"),
                "temperature": 20.0,
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(path, sep=";", index=False)


class TestGPSTrackSmoothingIntegration(unittest.TestCase):
    def test_smoothing_disabled_uses_raw_active_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pfad = Path(tmpdir) / "track.csv"
            t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
            zeiten = [t0 + timedelta(seconds=s) for s in (0, 2, 4, 6, 8)]
            meter = [0.0, 10.0, 10.0, 10.0, 10.0]
            _csv_erstellen(pfad, zeiten, meter)

            track = GPSTrack(str(pfad), smoothing_config=SpeedSmoothingConfig(enabled=False))
            self.assertTrue((track.df["geschwindigkeit_ms"] == track.df["geschwindigkeit_roh_ms"]).all())
            self.assertTrue((track.df["beschleunigung_ms2"] == track.df["beschleunigung_roh_ms2"]).all())

    def test_smoothing_enabled_uses_smoothed_active_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pfad = Path(tmpdir) / "track.csv"
            t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
            zeiten = [t0 + timedelta(seconds=s) for s in (0, 2, 4, 6, 8)]
            meter = [0.0, 10.0, 10.0, 30.0, 10.0]
            _csv_erstellen(pfad, zeiten, meter)

            track = GPSTrack(str(pfad), smoothing_config=SpeedSmoothingConfig(enabled=True))
            self.assertTrue((track.df["geschwindigkeit_ms"] == track.df["geschwindigkeit_geglaettet_ms"]).all())
            self.assertTrue((track.df["beschleunigung_ms2"] == track.df["beschleunigung_geglaettet_ms2"]).all())

    def test_short_interval_flags_and_no_extreme_acceleration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pfad = Path(tmpdir) / "track.csv"
            t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
            zeiten = [
                t0,
                t0 + timedelta(seconds=2.0),
                t0 + timedelta(seconds=2.1),
                t0 + timedelta(seconds=5.0),
            ]
            meter = [0.0, 14.0, 1.0, 14.0]
            _csv_erstellen(pfad, zeiten, meter)

            cfg = SpeedSmoothingConfig(enabled=True, min_interval_s=0.5)
            track = GPSTrack(str(pfad), smoothing_config=cfg)

            self.assertTrue(bool(track.df["filter_kurzes_intervall"].iloc[2]))
            self.assertFalse(bool(track.df["filter_gueltige_stuetzstelle"].iloc[2]))
            self.assertLess(abs(float(track.df["beschleunigung_ms2"].iloc[2])), 5.0)

    def test_large_gap_creates_segment_and_zero_accel_at_new_start(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pfad = Path(tmpdir) / "track.csv"
            t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
            zeiten = [
                t0,
                t0 + timedelta(seconds=2),
                t0 + timedelta(seconds=40),
                t0 + timedelta(seconds=42),
            ]
            meter = [0.0, 12.0, 12.0, 12.0]
            _csv_erstellen(pfad, zeiten, meter)

            cfg = SpeedSmoothingConfig(enabled=True, max_gap_s=30.0)
            track = GPSTrack(str(pfad), smoothing_config=cfg)

            self.assertTrue(bool(track.df["filter_grosse_zeitluecke"].iloc[2]))
            self.assertNotEqual(int(track.df["segment_id"].iloc[1]), int(track.df["segment_id"].iloc[2]))
            self.assertAlmostEqual(float(track.df["beschleunigung_ms2"].iloc[2]), 0.0, places=9)

    def test_simulator_compatibility_with_active_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pfad = Path(tmpdir) / "track.csv"
            t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
            zeiten = [t0 + timedelta(seconds=s) for s in (0, 2, 4, 6, 8)]
            meter = [0.0, 10.0, 11.0, 10.0, 9.0]
            _csv_erstellen(pfad, zeiten, meter)

            track = GPSTrack(str(pfad), smoothing_config=SpeedSmoothingConfig(enabled=True))
            bike = EBike.from_yaml("data/bike_config.yaml")
            motor = Motor(motorkonstante_Nm_A=1.5)
            akku = LiPoBatteryPack(capacity_nom_Ah=10.0, initial_soc=1.0, n_parallel=1)

            sim = EBikeSimulator(track=track, bike=bike, motor=motor, battery=akku)
            ergebnis = sim.simulate()

            self.assertIn("geschwindigkeit_ms", ergebnis.columns)
            self.assertIn("beschleunigung_ms2", ergebnis.columns)
            self.assertIn("leistung_W", ergebnis.columns)


if __name__ == "__main__":
    unittest.main()
