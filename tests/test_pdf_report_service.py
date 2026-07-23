from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from webapp.services import pdf_report_service as pdf_service
from webapp.services.pdf_report_service import PdfReportDataError, generate_simulation_pdf


def _write_png(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(2.5, 1.5))
    ax.plot([0, 1, 2], [0, 1, 0], color="tab:blue")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def _build_run_directory(
    tmp_path: Path,
    *,
    include_lipo: bool = True,
    include_nmc: bool = True,
    smoothing_enabled: bool = True,
    include_optional_plots: bool = True,
    source_file_name: str = "route.csv",
) -> Path:
    run_dir = tmp_path / "0123456789abcdef0123456789abcdef"
    run_dir.mkdir()
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

    summaries: dict[str, dict[str, object]] = {}
    plot_files: dict[str, str] = {}

    if include_optional_plots:
        _write_png(run_dir / "plot" / "hoehenprofil_fahrt.png")
        _write_png(run_dir / "plot" / "geschwindigkeit_roh_geglaettet.png")
        _write_png(run_dir / "plot" / "zeitverlauf_lipo.png")
        _write_png(run_dir / "plot" / "zeitverlauf_nmc.png")
        _write_png(run_dir / "plot" / "ladezustand_vergleich.png")
        plot_files = {
            "elevation": "plot/hoehenprofil_fahrt.png",
            "speed_comparison": "plot/geschwindigkeit_roh_geglaettet.png",
            "lipo": "plot/zeitverlauf_lipo.png",
            "nmc": "plot/zeitverlauf_nmc.png",
            "soc_comparison": "plot/ladezustand_vergleich.png",
        }
    else:
        _write_png(run_dir / "plot" / "hoehenprofil_fahrt.png")
        plot_files = {"elevation": "plot/hoehenprofil_fahrt.png"}

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

    battery_options = {
        "lipo": include_lipo,
        "nmc": include_nmc,
        "capacity_ah": 10.0,
        "initial_soc": 1.0,
        "n_parallel": 1,
    }

    if include_lipo:
        frame = _simulation_frame(0.78)
        frame.to_csv(run_dir / "simulation_lipo.csv", index=False)
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
        frame = _simulation_frame(0.81)
        frame.to_csv(run_dir / "simulation_nmc.csv", index=False)
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
        "source_file_name": source_file_name,
        "bike_config": {
            "masse_fahrer_kg": 70.0,
            "masse_rad_kg": 10.0,
            "cw_a_m2": 0.56,
            "raddurchmesser_inch": 27.0,
            "rollwiderstandkoeffizient": 0.005,
        },
        "battery_options": battery_options,
        "smoothing": {
            "enabled": smoothing_enabled,
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
        "plot_files": plot_files,
    }
    import json

    (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


@pytest.mark.parametrize(
    "include_lipo, include_nmc, smoothing_enabled",
    [
        (True, False, True),
        (False, True, True),
        (True, True, True),
        (True, True, False),
    ],
)
def test_pdf_generation_creates_pdf_for_supported_variants(
    tmp_path: Path,
    include_lipo: bool,
    include_nmc: bool,
    smoothing_enabled: bool,
) -> None:
    run_dir = _build_run_directory(
        tmp_path,
        include_lipo=include_lipo,
        include_nmc=include_nmc,
        smoothing_enabled=smoothing_enabled,
    )

    pdf_path = generate_simulation_pdf(run_dir)

    assert pdf_path.parent == run_dir
    assert pdf_path.name == "simulation_report.pdf"
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert pdf_path.stat().st_size > 1500


def test_pdf_generation_ignores_missing_optional_plot(tmp_path: Path) -> None:
    run_dir = _build_run_directory(tmp_path, include_optional_plots=False)

    pdf_path = generate_simulation_pdf(run_dir)

    assert pdf_path.is_file()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_pdf_generation_handles_german_characters(tmp_path: Path) -> None:
    run_dir = _build_run_directory(tmp_path, source_file_name="straße_äöü.csv")

    pdf_path = generate_simulation_pdf(run_dir)

    assert pdf_path.is_file()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_missing_metadata_raises_controlled_exception(tmp_path: Path) -> None:
    run_dir = _build_run_directory(tmp_path)
    (run_dir / "metadata.json").unlink()

    with pytest.raises(PdfReportDataError):
        generate_simulation_pdf(run_dir)


def test_missing_required_csv_raises_controlled_exception(tmp_path: Path) -> None:
    run_dir = _build_run_directory(tmp_path)
    (run_dir / "track.csv").unlink()

    with pytest.raises(PdfReportDataError):
        generate_simulation_pdf(run_dir)


def test_cached_pdf_is_reused_when_inputs_are_older(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _build_run_directory(tmp_path)
    pdf_path = generate_simulation_pdf(run_dir)
    before = pdf_path.read_bytes()

    def fail_build(*args, **kwargs):
        raise AssertionError("Cache should prevent rebuild.")

    monkeypatch.setattr(pdf_service, "_build_story", fail_build)

    cached = generate_simulation_pdf(run_dir)

    assert cached == pdf_path
    assert cached.read_bytes() == before


def test_temp_pdf_is_removed_after_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _build_run_directory(tmp_path)
    temp_pdf = run_dir / "simulation_report.tmp.pdf"
    temp_pdf.write_bytes(b"temporary")

    def boom(self, *args, **kwargs):
        raise RuntimeError("build failed")

    monkeypatch.setattr(pdf_service.SimpleDocTemplate, "build", boom)

    with pytest.raises(RuntimeError):
        generate_simulation_pdf(run_dir)

    assert not temp_pdf.exists()
