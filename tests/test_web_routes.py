from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from speed_smoothing import SpeedSmoothingConfig
from webapp import create_app
from webapp import routes as routes_module
from webapp.services.parameter_study_explanation_service import explain_parameter_study
from webapp.services.parameter_study_service import run_parameter_study
from webapp.services.simulation_service import run_simulation


def _write_png(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(2.5, 1.5))
    ax.plot([0, 1, 2], [0, 1, 0], color="tab:blue")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def _build_result_directory(run_dir: Path, *, include_lipo: bool = True, include_nmc: bool = True) -> dict[str, dict[str, object]]:
    run_dir.mkdir(parents=True)
    (run_dir / "plot").mkdir()

    track = pd.DataFrame(
        {
            "time": ["2024-01-01T00:00:00Z", "2024-01-01T00:00:10Z", "2024-01-01T00:00:20Z"],
            "distanz_m": [0.0, 120.0, 110.0],
            "ele": [100.0, 104.0, 108.0],
            "geschwindigkeit_roh_ms": [0.0, 12.0, 11.0],
            "geschwindigkeit_ms": [0.0, 11.5, 10.9],
            "filter_kurzes_intervall": [False, False, False],
            "filter_grosse_zeitluecke": [False, False, False],
            "filter_geschwindigkeitsausreisser": [False, False, False],
            "filter_gueltige_stuetzstelle": [True, True, True],
        }
    )
    track.to_csv(run_dir / "track.csv", index=False)
    for name in ("hoehenprofil_fahrt.png", "geschwindigkeit_roh_geglaettet.png", "zeitverlauf_lipo.png", "zeitverlauf_nmc.png", "ladezustand_vergleich.png"):
        _write_png(run_dir / "plot" / name)

    def _simulation_frame(final_soc: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "time": ["2024-01-01T00:00:00Z", "2024-01-01T00:00:10Z", "2024-01-01T00:00:20Z"],
                "dt_s": [0.0, 10.0, 10.0],
                "leistung_W": [0.0, 100.0, 120.0],
                "drehmoment_Nm": [0.0, 12.0, 14.0],
                "motorstrom_A": [0.0, 8.0, 9.0],
                "spannung_V": [42.0, 40.5, 39.8],
                "soc": [1.0, 0.9, final_soc],
            }
        )

    summaries: dict[str, dict[str, object]] = {}
    if include_lipo:
        _simulation_frame(0.78).to_csv(run_dir / "simulation_lipo.csv", index=False)
        summaries["LiPo"] = {
            "final_soc_percent": 78.0,
            "soc_consumption_percent": 22.0,
            "traction_energy_Wh": 0.6,
            "braking_energy_Wh": 0.0,
            "max_power_W": 120.0,
            "max_motor_current_A": 9.0,
            "max_torque_Nm": 14.0,
            "minimum_voltage_V": 39.8,
            "simulated_point_count": 3,
            "expected_point_count": 3,
            "completed_route": True,
            "end_point": 2,
        }
    if include_nmc:
        _simulation_frame(0.81).to_csv(run_dir / "simulation_nmc.csv", index=False)
        summaries["NMC"] = {
            "final_soc_percent": 81.0,
            "soc_consumption_percent": 19.0,
            "traction_energy_Wh": 0.6,
            "braking_energy_Wh": 0.0,
            "max_power_W": 120.0,
            "max_motor_current_A": 9.0,
            "max_torque_Nm": 14.0,
            "minimum_voltage_V": 40.1,
            "simulated_point_count": 3,
            "expected_point_count": 3,
            "completed_route": True,
            "end_point": 2,
        }

    metadata = {
        "schema_version": 2,
        "run_id": run_dir.name,
        "created_at_utc": "2024-01-01T12:00:00+00:00",
        "source_file_name": "route.csv",
        "bike_config": {
            "masse_fahrer_kg": 70.0,
            "masse_rad_kg": 10.0,
            "cw_a_m2": 0.56,
            "raddurchmesser_inch": 27.0,
            "rollwiderstandkoeffizient": 0.005,
        },
        "battery_options": {
            "lipo": include_lipo,
            "nmc": include_nmc,
            "capacity_ah": 10.0,
            "initial_soc": 1.0,
            "n_parallel": 1,
        },
        "smoothing": {
            "enabled": True,
            "min_interval_s": 0.5,
            "max_gap_s": 30.0,
            "median_window_s": 15.0,
            "time_constant_s": 3.0,
            "max_reasonable_speed_kmh": 60.0,
        },
        "route_summary": {
            "total_distance_km": 0.23,
            "duration_s": 20.0,
            "gps_point_count": 3,
            "average_speed_kmh": 41.4,
            "max_raw_speed_kmh": 43.2,
            "max_active_speed_kmh": 41.4,
            "elevation_gain_m": 8.0,
            "short_interval_count": 0,
            "large_gap_count": 0,
            "speed_outlier_count": 0,
            "valid_smoothing_support_point_count": 3,
        },
        "summaries": summaries,
        "plot_files": {
            "elevation": "plot/hoehenprofil_fahrt.png",
            "speed_comparison": "plot/geschwindigkeit_roh_geglaettet.png",
            "lipo": "plot/zeitverlauf_lipo.png",
            "nmc": "plot/zeitverlauf_nmc.png",
            "soc_comparison": "plot/ladezustand_vergleich.png",
        },
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return summaries


@pytest.fixture()
def app(tmp_path: Path):
    return create_app({"TESTING": True, "WEB_OUTPUT": tmp_path})


@pytest.fixture()
def client(app):
    return app.test_client()


def _simulation_form_data() -> dict[str, str]:
    return {
        "masse_fahrer_kg": "70",
        "masse_rad_kg": "10",
        "cw_a_m2": "0.56",
        "raddurchmesser_inch": "27",
        "rollwiderstandkoeffizient": "0.005",
        "smoothing_enabled": "on",
        "min_interval_s": "0.5",
        "max_gap_s": "30",
        "median_window_s": "15",
        "time_constant_s": "3",
        "max_reasonable_speed_kmh": "60",
        "capacity_ah": "10",
        "initial_soc": "1",
        "n_parallel": "1",
        "lipo": "on",
        "nmc": "on",
    }


def test_result_page_displays_pdf_button_after_simulation(monkeypatch: pytest.MonkeyPatch, client, app) -> None:
    run_dir = app.config["WEB_OUTPUT"] / "0123456789abcdef0123456789abcdef"

    def fake_run_simulation(*args, **kwargs):
        summaries = _build_result_directory(run_dir)
        return SimpleNamespace(
            run_id=run_dir.name,
            output_dir=run_dir,
            track=SimpleNamespace(df=pd.DataFrame()),
            simulations={name: pd.DataFrame() for name in summaries},
            summaries=summaries,
            smoothing=SpeedSmoothingConfig(enabled=True),
            map_paths={},
        )

    monkeypatch.setattr(routes_module, "run_simulation", fake_run_simulation)

    response = client.post("/simulate", data=_simulation_form_data(), follow_redirects=True)

    assert response.status_code == 200
    assert b"PDF-Bericht herunterladen" in response.data


def test_pdf_is_downloadable_after_simulation(monkeypatch: pytest.MonkeyPatch, client, app) -> None:
    run_dir = app.config["WEB_OUTPUT"] / "0123456789abcdef0123456789abcdef"

    def fake_run_simulation(*args, **kwargs):
        summaries = _build_result_directory(run_dir)
        return SimpleNamespace(
            run_id=run_dir.name,
            output_dir=run_dir,
            track=SimpleNamespace(df=pd.DataFrame()),
            simulations={name: pd.DataFrame() for name in summaries},
            summaries=summaries,
            smoothing=SpeedSmoothingConfig(enabled=True),
            map_paths={},
        )

    monkeypatch.setattr(routes_module, "run_simulation", fake_run_simulation)

    client.post("/simulate", data=_simulation_form_data(), follow_redirects=True)
    response = client.get(f"/results/{run_dir.name}/pdf")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/pdf")
    assert "attachment" in response.headers["Content-Disposition"]
    assert run_dir.name in response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF")


def test_parameter_study_page_displays_generated_interpretation(monkeypatch: pytest.MonkeyPatch, client, app) -> None:
    df = pd.DataFrame(
        {
            "parameter_name": ["cw_a_m2"] * 3,
            "parameter_value": [0.4, 0.5, 0.6],
            "battery_type": ["LiPo", "LiPo", "LiPo"],
            "smoothing_enabled": [True, True, True],
            "total_distance_km": [10.0, 10.0, 10.0],
            "duration_s": [1200.0, 1200.0, 1200.0],
            "average_speed_kmh": [30.0, 30.0, 30.0],
            "final_soc_percent": [80.0, 78.0, 76.0],
            "soc_consumption_percent": [20.0, 22.0, 24.0],
            "max_power_W": [200.0, 210.0, 220.0],
            "max_motor_current_A": [5.0, 5.2, 5.4],
            "max_torque_Nm": [10.0, 10.2, 10.4],
            "minimum_voltage_V": [38.0, 37.5, 37.0],
            "traction_energy_Wh": [100.0, 110.0, 120.0],
            "braking_energy_Wh": [2.0, 2.2, 2.4],
            "completed_route": [True, True, True],
            "end_point": [2, 2, 2],
            "simulated_point_count": [3, 3, 3],
            "expected_point_count": [3, 3, 3],
        }
    )

    def fake_run_parameter_study(*args, **kwargs):
        return df

    monkeypatch.setattr(routes_module, "run_parameter_study", fake_run_parameter_study)

    response = client.post(
        "/parameterstudie",
        data={
            **_simulation_form_data(),
            "parameter_name": "cw_a_m2",
            "minimum": "0.4",
            "maximum": "0.6",
            "steps": "3",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Interpretation der Parameterstudie" in response.data
    assert b"Kurzfazit" in response.data
    assert b"LiPo" in response.data

    study_dirs = list(app.config["WEB_OUTPUT"].glob("*/parameterstudie.csv"))
    assert study_dirs


def test_secure_pdf_route_rejects_unknown_and_unsafe_runs(client, app) -> None:
    run_dir = app.config["WEB_OUTPUT"] / "0123456789abcdef0123456789abcdef"
    _build_result_directory(run_dir)

    with client.session_transaction() as session:
        session["run_dir"] = str(run_dir)

    assert client.get("/results/not-a-valid-run-id/pdf").status_code == 404
    assert client.get("/results/../pdf").status_code == 404
    assert client.get("/results/ffffffffffffffffffffffffffffffff/pdf").status_code == 404


def test_secure_pdf_route_rejects_outside_and_foreign_sessions(client, app) -> None:
    run_dir = app.config["WEB_OUTPUT"] / "0123456789abcdef0123456789abcdef"
    _build_result_directory(run_dir)

    outside_dir = app.config["WEB_OUTPUT"].parent / "outside" / "fedcba9876543210fedcba9876543210"
    _build_result_directory(outside_dir)

    with client.session_transaction() as session:
        session["run_dir"] = str(outside_dir)

    assert client.get(f"/results/{outside_dir.name}/pdf").status_code == 404

    with client.session_transaction() as session:
        session["run_dir"] = str(run_dir)

    assert client.get(f"/results/{outside_dir.name}/pdf").status_code == 404


def test_pdf_generation_errors_are_user_friendly(monkeypatch: pytest.MonkeyPatch, client, app) -> None:
    run_dir = app.config["WEB_OUTPUT"] / "0123456789abcdef0123456789abcdef"
    _build_result_directory(run_dir)

    with client.session_transaction() as session:
        session["run_dir"] = str(run_dir)

    monkeypatch.setattr(routes_module, "generate_simulation_pdf", lambda directory: (_ for _ in ()).throw(PdfReportDataError("kaputt")))

    response = client.get(f"/results/{run_dir.name}/pdf")

    assert response.status_code == 500
    assert b"PDF-Bericht konnte nicht erstellt werden" in response.data


def test_existing_command_line_simulation_service_still_works(tmp_path: Path) -> None:
    track = pd.DataFrame(
        {
            "time": ["2024-01-01T00:00:00Z", "2024-01-01T00:00:10Z", "2024-01-01T00:00:20Z"],
            "lat": [48.0, 48.0001, 48.0002],
            "lon": [11.0, 11.0001, 11.0002],
            "ele": [500.0, 501.0, 502.0],
        }
    )
    track_path = tmp_path / "track.csv"
    track.to_csv(track_path, sep=";", index=False)

    bike_config = {
        "masse_fahrer_kg": 70.0,
        "masse_rad_kg": 10.0,
        "cw_a_m2": 0.56,
        "raddurchmesser_inch": 27.0,
        "rollwiderstandkoeffizient": 0.005,
    }
    smoothing = SpeedSmoothingConfig(enabled=False)

    result = run_simulation(track_path, bike_config, smoothing, output_directory=tmp_path / "simulation_output", generate_outputs=False)

    assert result.run_id == "simulation_output"
    assert result.output_dir.exists()
    assert result.summaries
