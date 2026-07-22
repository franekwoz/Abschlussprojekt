import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from speed_smoothing import (
    SpeedSmoothingConfig,
    _exp_glatt_zeitabhaengig,
    beschleunigung_aus_geschwindigkeit,
    geschwindigkeit_glaetten,
)


class TestSpeedSmoothingConfig(unittest.TestCase):
    def test_yaml_enabled_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cfg.yaml"
            path.write_text("enabled: true\n", encoding="utf-8")
            cfg = SpeedSmoothingConfig.from_yaml(path)
            self.assertTrue(cfg.enabled)

    def test_yaml_enabled_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cfg.yaml"
            path.write_text("enabled: false\n", encoding="utf-8")
            cfg = SpeedSmoothingConfig.from_yaml(path)
            self.assertFalse(cfg.enabled)

    def test_yaml_uses_defaults_for_missing_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cfg.yaml"
            path.write_text("enabled: true\n", encoding="utf-8")
            cfg = SpeedSmoothingConfig.from_yaml(path)
            self.assertAlmostEqual(cfg.min_interval_s, 0.5)
            self.assertAlmostEqual(cfg.max_gap_s, 30.0)
            self.assertAlmostEqual(cfg.median_window_s, 15.0)
            self.assertAlmostEqual(cfg.time_constant_s, 3.0)
            self.assertAlmostEqual(cfg.max_reasonable_speed_kmh, 60.0)

    def test_yaml_invalid_values_raise_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cfg.yaml"
            path.write_text("enabled: true\nmin_interval_s: 0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "min_interval_s"):
                SpeedSmoothingConfig.from_yaml(path)


class TestSpeedSmoothingAlgorithm(unittest.TestCase):
    def test_constant_speed_keeps_acceleration_near_zero(self):
        zeit = pd.to_datetime(
            [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:02Z",
                "2024-01-01T00:00:04Z",
                "2024-01-01T00:00:06Z",
                "2024-01-01T00:00:08Z",
            ]
        )
        dt = pd.Series([0.0, 2.0, 2.0, 2.0, 2.0])
        v = pd.Series([0.0, 6.9444, 6.9444, 6.9444, 6.9444])

        cfg = SpeedSmoothingConfig(enabled=True)
        result = geschwindigkeit_glaetten(zeit, dt, v, cfg)
        a = beschleunigung_aus_geschwindigkeit(zeit, result.geglaettete_geschwindigkeit_ms, result.segment_id)

        self.assertTrue((a.abs() < 0.2).all())

    def test_single_outlier_is_smoothed_but_raw_stays(self):
        zeit = pd.to_datetime(
            [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:02Z",
                "2024-01-01T00:00:04Z",
                "2024-01-01T00:00:06Z",
                "2024-01-01T00:00:08Z",
            ]
        )
        dt = pd.Series([0.0, 2.0, 2.0, 2.0, 2.0])
        v = pd.Series([0.0, 25 / 3.6, 25 / 3.6, 70 / 3.6, 25 / 3.6])

        cfg = SpeedSmoothingConfig(enabled=True, max_reasonable_speed_kmh=60.0)
        result = geschwindigkeit_glaetten(zeit, dt, v, cfg)

        self.assertTrue(bool(result.geschwindigkeitsausreisser.iloc[3]))
        self.assertAlmostEqual(v.iloc[3] * 3.6, 70.0, places=6)
        self.assertLess(abs(result.geglaettete_geschwindigkeit_ms.iloc[3] * 3.6 - 25.0), 10.0)

    def test_short_interval_not_used_as_support(self):
        zeit = pd.to_datetime(
            [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:01Z",
                "2024-01-01T00:00:01.100Z",
                "2024-01-01T00:00:03Z",
            ],
            format="ISO8601",
        )
        dt = pd.Series([0.0, 1.0, 0.1, 1.9])
        v = pd.Series([0.0, 6.9, 7.4, 6.9])

        cfg = SpeedSmoothingConfig(enabled=True, min_interval_s=0.5)
        result = geschwindigkeit_glaetten(zeit, dt, v, cfg)

        self.assertTrue(bool(result.kurzes_intervall.iloc[2]))
        self.assertFalse(bool(result.gueltige_stuetzstelle.iloc[2]))

    def test_large_gap_creates_new_segment_and_no_bridge_acceleration(self):
        zeit = pd.to_datetime(
            [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:02Z",
                "2024-01-01T00:00:40Z",
                "2024-01-01T00:00:42Z",
            ]
        )
        dt = pd.Series([0.0, 2.0, 38.0, 2.0])
        v = pd.Series([0.0, 6.0, 6.5, 6.4])

        cfg = SpeedSmoothingConfig(enabled=True, max_gap_s=30.0)
        result = geschwindigkeit_glaetten(zeit, dt, v, cfg)
        a = beschleunigung_aus_geschwindigkeit(zeit, result.geglaettete_geschwindigkeit_ms, result.segment_id)

        self.assertTrue(bool(result.grosse_zeitluecke.iloc[2]))
        self.assertNotEqual(int(result.segment_id.iloc[1]), int(result.segment_id.iloc[2]))
        self.assertAlmostEqual(float(a.iloc[2]), 0.0, places=9)

    def test_irregular_intervals_affect_exponential_alpha(self):
        idx = pd.to_datetime(
            [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:01Z",
                "2024-01-01T00:00:10Z",
            ]
        )
        serie = pd.Series([0.0, 10.0, 10.0], index=idx)

        out = _exp_glatt_zeitabhaengig(
            serie=serie,
            zeitindex=idx,
            time_constant_s=3.0,
            rueckwaerts=False,
        )

        alpha_kurz = 1.0 - math.exp(-1.0 / 3.0)
        alpha_lang = 1.0 - math.exp(-9.0 / 3.0)
        erwartung_1 = 0.0 + alpha_kurz * (10.0 - 0.0)
        erwartung_2 = erwartung_1 + alpha_lang * (10.0 - erwartung_1)

        self.assertAlmostEqual(float(out.iloc[1]), erwartung_1, places=8)
        self.assertAlmostEqual(float(out.iloc[2]), erwartung_2, places=8)


if __name__ == "__main__":
    unittest.main()
