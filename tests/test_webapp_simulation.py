from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
from flask import Flask

from speed_smoothing import SpeedSmoothingConfig
from webapp import create_app
from webapp.routes import defaults
from webapp.services.simulation_service import _summary, run_simulation


def _create_track_csv(path: Path, point_count: int = 12) -> None:
    start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(point_count):
        rows.append(
            {
                "time": (start_time + timedelta(seconds=index * 2)).isoformat().replace("+00:00", "Z"),
                "lat": 47.58,
                "lon": 12.17 + index * 0.0001,
                "ele": 500.0,
                "temperature": 20.0,
            }
        )
    pd.DataFrame(rows).to_csv(path, sep=";", index=False)


def _default_form_data(app: Flask) -> dict[str, str]:
    with app.app_context():
        bike, smooth = defaults()
    data = {key: str(value) for key, value in bike.items()}
    data.update(
        {
            "capacity_ah": "10",
            "initial_soc": "1",
            "n_parallel": "1",
            "smoothing_enabled": "on",
            "mit_orten_und_wetter": "on",
            "lipo": "on",
            "nmc": "on",
            "min_interval_s": str(smooth.min_interval_s),
            "max_gap_s": str(smooth.max_gap_s),
            "median_window_s": str(smooth.median_window_s),
            "time_constant_s": str(smooth.time_constant_s),
            "max_reasonable_speed_kmh": str(smooth.max_reasonable_speed_kmh),
        }
    )
    return data


def _mock_location_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "index": 0,
                "lat": 47.5800,
                "lon": 12.1700,
                "adresse": "Startplatz 1",
                "wetter_temperatur_c": 20.0,
                "wetter_wind_kmh": 3.0,
                "wetter_niederschlag_mm": 0.0,
                "wetter_luftfeuchte_pct": 60.0,
            },
            {
                "index": 3,
                "lat": 47.5810,
                "lon": 12.1710,
                "adresse": "Mitte 3",
                "wetter_temperatur_c": 21.0,
                "wetter_wind_kmh": 4.0,
                "wetter_niederschlag_mm": 0.2,
                "wetter_luftfeuchte_pct": float("nan"),
            },
            {
                "index": 6,
                "lat": 47.5820,
                "lon": 12.1720,
                "adresse": "Mitte 6",
                "wetter_temperatur_c": 22.0,
                "wetter_wind_kmh": 5.0,
                "wetter_niederschlag_mm": 0.4,
                "wetter_luftfeuchte_pct": 62.0,
            },
            {
                "index": 9,
                "lat": 47.5830,
                "lon": 12.1730,
                "adresse": "Mitte 9",
                "wetter_temperatur_c": 23.0,
                "wetter_wind_kmh": 6.0,
                "wetter_niederschlag_mm": 0.1,
                "wetter_luftfeuchte_pct": 63.0,
            },
            {
                "index": 12,
                "lat": 47.5840,
                "lon": 12.1740,
                "adresse": "Mitte 12",
                "wetter_temperatur_c": 24.0,
                "wetter_wind_kmh": 7.0,
                "wetter_niederschlag_mm": 0.3,
                "wetter_luftfeuchte_pct": 64.0,
            },
            {
                "index": 15,
                "lat": 47.5850,
                "lon": 12.1750,
                "adresse": "Mitte 15",
                "wetter_temperatur_c": 25.0,
                "wetter_wind_kmh": 8.0,
                "wetter_niederschlag_mm": 0.6,
                "wetter_luftfeuchte_pct": 65.0,
            },
            {
                "index": 18,
                "lat": 47.5860,
                "lon": 12.1760,
                "adresse": "Mitte 18",
                "wetter_temperatur_c": 26.0,
                "wetter_wind_kmh": 9.0,
                "wetter_niederschlag_mm": 0.7,
                "wetter_luftfeuchte_pct": 66.0,
            },
            {
                "index": 21,
                "lat": 47.5870,
                "lon": 12.1770,
                "adresse": "Zielplatz 21",
                "wetter_temperatur_c": 27.0,
                "wetter_wind_kmh": 10.0,
                "wetter_niederschlag_mm": 0.9,
                "wetter_luftfeuchte_pct": 67.0,
            },
        ]
    )


class TestWebSimulationRouting(unittest.TestCase):
    def test_checkbox_state_is_passed_to_run_simulation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app({"TESTING": True, "WEB_OUTPUT": Path(tmpdir) / "web"})
            client = app.test_client()
            track_path = Path(tmpdir) / "track.csv"
            _create_track_csv(track_path)

            form_data = _default_form_data(app)
            with patch("webapp.routes.run_simulation") as mocked_run:
                mocked_result = Mock()
                mocked_result.output_dir = Path(tmpdir) / "run"
                mocked_result.run_id = "run"
                mocked_run.return_value = mocked_result

                response = client.post(
                    "/simulate",
                    data={**form_data, "track": (io.BytesIO(track_path.read_bytes()), "track.csv")},
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 302)
            _, kwargs = mocked_run.call_args
            self.assertTrue(kwargs["mit_orten_und_wetter"])
            self.assertEqual(kwargs["anzahl_wegpunkte"], 6)

    def test_deactivated_option_skips_geocoding_and_weather(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            track_path = Path(tmpdir) / "track.csv"
            output_dir = Path(tmpdir) / "output"
            _create_track_csv(track_path)

            bike, smooth = defaults() if False else (None, None)
            with create_app({"TESTING": True, "WEB_OUTPUT": output_dir}).app_context():
                bike, smooth = defaults()

            with patch("webapp.services.simulation_service.GPSTrack.orte_ermitteln") as mocked_orte, patch(
                "webapp.services.simulation_service.wetterdaten_fuer_orte"
            ) as mocked_wetter:
                result = run_simulation(
                    track_path,
                    bike,
                    smooth,
                    {"lipo": True, "nmc": False, "capacity_ah": 10.0, "initial_soc": 1.0, "n_parallel": 1},
                    output_directory=output_dir,
                    generate_outputs=False,
                    mit_orten_und_wetter=False,
                )

            mocked_orte.assert_not_called()
            mocked_wetter.assert_not_called()
            self.assertIsNone(result.orte)

    def test_location_and_weather_metadata_is_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            track_path = Path(tmpdir) / "track.csv"
            output_dir = Path(tmpdir) / "output"
            _create_track_csv(track_path, point_count=20)
            app = create_app({"TESTING": True, "WEB_OUTPUT": output_dir})
            with app.app_context():
                bike, smooth = defaults()

            mock_orte = _mock_location_data()
            with patch("webapp.services.simulation_service.GPSTrack.orte_ermitteln", return_value=mock_orte), patch(
                "webapp.services.simulation_service.wetterdaten_fuer_orte",
                side_effect=lambda orte, track_df: orte,
            ):
                result = run_simulation(
                    track_path,
                    bike,
                    smooth,
                    {"lipo": True, "nmc": True, "capacity_ah": 10.0, "initial_soc": 1.0, "n_parallel": 1},
                    output_directory=output_dir,
                    generate_outputs=True,
                    mit_orten_und_wetter=True,
                    anzahl_wegpunkte=6,
                )

            meta = json.loads((result.output_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertIn("weather_summary", meta)
            self.assertIn("location_summary", meta)
            self.assertIn("location_weather_points", meta)
            self.assertEqual(len(meta["location_weather_points"]), 8)
            self.assertEqual(meta["location_weather_points"][0]["address"], "Startplatz 1")
            self.assertEqual(meta["location_weather_points"][1]["humidity_percent"], None)
            self.assertTrue(meta["weather_summary"]["available"])
            self.assertEqual(meta["weather_summary"]["sampled_points"], 8)
            self.assertEqual(meta["location_summary"]["provider"], "Nominatim / OpenStreetMap")
            self.assertEqual(meta["location_summary"]["start"]["address"], "Startplatz 1")
            self.assertEqual(meta["location_summary"]["end"]["address"], "Zielplatz 21")
            self.assertEqual(meta["feature_status"]["reverse_geocoding"]["state"], "active")
            self.assertEqual(meta["feature_status"]["weather"]["state"], "active")

    def test_results_page_renders_start_middle_and_end_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            track_path = Path(tmpdir) / "track.csv"
            output_dir = Path(tmpdir) / "output"
            _create_track_csv(track_path, point_count=20)
            app = create_app({"TESTING": True, "WEB_OUTPUT": output_dir})
            with app.app_context():
                bike, smooth = defaults()

            mock_orte = _mock_location_data()
            with patch("webapp.services.simulation_service.GPSTrack.orte_ermitteln", return_value=mock_orte), patch(
                "webapp.services.simulation_service.wetterdaten_fuer_orte",
                side_effect=lambda orte, track_df: orte,
            ):
                result = run_simulation(
                    track_path,
                    bike,
                    smooth,
                    {"lipo": True, "nmc": True, "capacity_ah": 10.0, "initial_soc": 1.0, "n_parallel": 1},
                    output_directory=output_dir,
                    generate_outputs=True,
                    mit_orten_und_wetter=True,
                    anzahl_wegpunkte=6,
                )

            client = app.test_client()
            with client.session_transaction() as session:
                session["run_dir"] = str(result.output_dir)

            response = client.get(f"/results/{result.run_id}")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Start", body)
            self.assertIn("Zwischenpunkt", body)
            self.assertIn("Ziel", body)

    def test_failed_geocoding_keeps_results_page_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            track_path = Path(tmpdir) / "track.csv"
            output_dir = Path(tmpdir) / "output"
            _create_track_csv(track_path, point_count=20)
            app = create_app({"TESTING": True, "WEB_OUTPUT": output_dir})
            with app.app_context():
                bike, smooth = defaults()

            with patch("webapp.services.simulation_service.GPSTrack.orte_ermitteln", side_effect=RuntimeError("offline")), patch(
                "webapp.services.simulation_service.wetterdaten_fuer_orte"
            ) as mocked_wetter:
                result = run_simulation(
                    track_path,
                    bike,
                    smooth,
                    {"lipo": True, "nmc": True, "capacity_ah": 10.0, "initial_soc": 1.0, "n_parallel": 1},
                    output_directory=output_dir,
                    generate_outputs=True,
                    mit_orten_und_wetter=True,
                    anzahl_wegpunkte=6,
                )

            mocked_wetter.assert_not_called()
            client = app.test_client()
            with client.session_transaction() as session:
                session["run_dir"] = str(result.output_dir)

            response = client.get(f"/results/{result.run_id}")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Wetter- oder Ortsinformationen konnten nicht geladen werden", body)
            self.assertIn("Die Simulation wurde trotzdem erfolgreich durchgeführt", body)


class TestSimulationSummary(unittest.TestCase):
    def _summary_frame(self, rows: int, final_soc: float) -> pd.DataFrame:
        index = range(rows)
        return pd.DataFrame(
            {
                "dt_s": [1.0] * rows,
                "leistung_W": [100.0] * rows,
                "soc": [final_soc] * rows,
                "motorstrom_A": [10.0] * rows,
                "drehmoment_Nm": [5.0] * rows,
                "spannung_V": [42.0] * rows,
            },
            index=index,
        )

    def test_incomplete_route_is_detected(self):
        frame = self._summary_frame(310, 0.0)
        summary = _summary(frame, 1.0, 2284)
        self.assertFalse(summary["completed_route"])
        self.assertEqual(summary["processed_points"], 310)
        self.assertEqual(summary["total_track_points"], 2284)
        self.assertAlmostEqual(summary["completion_percent"], 310 / 2284 * 100, places=6)
        self.assertEqual(summary["end_point"], 309)
        self.assertEqual(summary["abort_reason"], "battery_empty")

    def test_complete_route_is_detected(self):
        frame = self._summary_frame(2284, 0.4)
        summary = _summary(frame, 1.0, 2284)
        self.assertTrue(summary["completed_route"])
        self.assertEqual(summary["processed_points"], 2284)
        self.assertEqual(summary["total_track_points"], 2284)
        self.assertEqual(summary["abort_reason"], None)
        self.assertAlmostEqual(summary["completion_percent"], 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
