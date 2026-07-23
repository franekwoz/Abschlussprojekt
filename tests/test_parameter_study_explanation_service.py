from __future__ import annotations

import pandas as pd

from webapp.services.parameter_study_explanation_service import (
    explain_parameter_study,
)


def _study_frame(
    parameter_values: list[float],
    battery_type: str = "LiPo",
    metric_values: dict[str, list[float]] | None = None,
) -> pd.DataFrame:
    metric_values = metric_values or {}
    rows = []
    for index, parameter_value in enumerate(parameter_values):
        row = {
            "parameter_name": "cw_a_m2",
            "parameter_value": parameter_value,
            "battery_type": battery_type,
            "smoothing_enabled": True,
            "total_distance_km": 10.0,
            "duration_s": 1200.0,
            "average_speed_kmh": 30.0,
            "final_soc_percent": 80.0,
            "soc_consumption_percent": 20.0,
            "max_power_W": 200.0,
            "max_motor_current_A": 5.0,
            "max_torque_Nm": 10.0,
            "minimum_voltage_V": 38.0,
            "traction_energy_Wh": 100.0,
            "braking_energy_Wh": 2.0,
            "completed_route": True,
            "end_point": 9,
            "simulated_point_count": 10,
            "expected_point_count": 10,
        }
        for key, values in metric_values.items():
            row[key] = values[index]
        rows.append(row)
    return pd.DataFrame(rows)


def test_monotonically_increasing_metric_is_classified_correctly() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"final_soc_percent": [70.0, 72.0, 74.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][0]

    assert analysis.trend == "monoton steigend"
    assert analysis.first_value == 70.0
    assert analysis.last_value == 74.0
    assert analysis.absolute_change == 4.0
    assert analysis.relative_change_percent == 5.714285714285714


def test_monotonically_decreasing_metric_is_classified_correctly() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"soc_consumption_percent": [23.0, 22.95, 22.9]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][1]

    assert analysis.trend == "monoton fallend"
    assert abs(analysis.absolute_change + 0.1) < 1e-9
    assert analysis.sensitivity == "geringer Einfluss"


def test_approximately_constant_metric_is_classified_correctly() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"traction_energy_Wh": [100.0, 100.0000001, 100.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][2]

    assert analysis.trend == "annähernd konstant"
    assert analysis.regression_slope is None
    assert analysis.r_squared is None


def test_non_monotonic_metric_is_detected() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"max_power_W": [200.0, 220.0, 210.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][3]

    assert analysis.trend == "nicht monoton"


def test_nearly_linear_metric_reports_high_r_squared() -> None:
    df = _study_frame([0.4, 0.5, 0.6, 0.7], metric_values={"max_motor_current_A": [4.0, 5.0, 6.0, 7.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][4]

    assert analysis.regression_slope is not None
    assert analysis.r_squared is not None
    assert analysis.r_squared >= 0.95


def test_clearly_nonlinear_metric_has_lower_r_squared() -> None:
    df = _study_frame([0.4, 0.5, 0.6, 0.7], metric_values={"max_torque_Nm": [1.0, 4.0, 16.0, 64.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][5]

    assert analysis.r_squared is not None
    assert analysis.r_squared < 0.95


def test_exact_baseline_is_detected() -> None:
    df = _study_frame([0.4, 0.5, 0.6])

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)

    assert explanation.exact_baseline_included is True
    assert explanation.nearest_study_value == 0.5


def test_nearest_baseline_is_used_when_exact_value_missing() -> None:
    df = _study_frame([0.4, 0.55, 0.7])

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)

    assert explanation.exact_baseline_included is False
    assert explanation.nearest_study_value == 0.55
    assert "nächstgelegene simulierte Stützpunkt" in explanation.summary


def test_zero_first_value_suppresses_relative_change() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"final_soc_percent": [0.0, 5.0, 10.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][0]

    assert analysis.relative_change_percent is None
    assert "nahe null" in analysis.text


def test_invalid_values_are_ignored_with_warning() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"final_soc_percent": [70.0, float("nan"), float("inf")]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][0]

    assert analysis.first_value == 70.0
    assert analysis.last_value == 70.0
    assert any("nicht-endliche" in warning or "verwertbaren" in warning for warning in analysis.warnings)


def test_missing_optional_metric_is_handled_gracefully() -> None:
    df = _study_frame([0.4, 0.5, 0.6]).drop(columns=["minimum_voltage_V"])

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][6]

    assert analysis.first_value is None
    assert analysis.trend == "nicht bestimmbar"
    assert any("fehlt" in warning for warning in analysis.warnings)


def test_incomplete_route_is_reflected_in_completion_metric() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"completed_route": [True, False, False]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][8]

    assert analysis.metric_name == "completed_route"
    assert analysis.first_value == 1.0
    assert analysis.last_value == 0.0
    assert "nicht vollständig" in analysis.text or "vollständig abgeschlossen" in analysis.text


def test_both_battery_types_are_reported_and_compared() -> None:
    lipo = _study_frame([0.4, 0.5, 0.6], "LiPo", {"final_soc_percent": [80.0, 78.0, 76.0]})
    nmc = _study_frame([0.4, 0.5, 0.6], "NMC", {"final_soc_percent": [82.0, 80.0, 78.0]})
    df = pd.concat([lipo, nmc], ignore_index=True)

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)

    assert set(explanation.battery_analyses) == {"LiPo", "NMC"}
    assert explanation.battery_comparison


def test_only_two_parameter_points_skip_regression() -> None:
    df = _study_frame([0.4, 0.6], metric_values={"final_soc_percent": [80.0, 78.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    analysis = explanation.battery_analyses["LiPo"][0]

    assert analysis.regression_slope is None
    assert analysis.r_squared is None


def test_correct_labels_and_units_are_used() -> None:
    df = _study_frame([0.4, 0.5, 0.6])

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)

    assert explanation.parameter_label == "cwA-Wert"
    assert explanation.parameter_unit == "m²"
    assert explanation.battery_analyses["LiPo"][0].label == "Finaler SoC"
    assert explanation.battery_analyses["LiPo"][0].unit == "%"


def test_percent_and_percentage_point_wording_is_distinct() -> None:
    df = _study_frame([0.4, 0.5, 0.6], metric_values={"final_soc_percent": [70.0, 72.0, 75.0]})

    explanation = explain_parameter_study(df, "cw_a_m2", 0.5)
    final_soc = explanation.battery_analyses["LiPo"][0]

    assert "Prozentpunkte" in final_soc.text
    assert "relative Änderung" in final_soc.text


def test_sensitivity_thresholds_are_classified_correctly() -> None:
    low = _study_frame([0.4, 0.5, 0.6], metric_values={"final_soc_percent": [100.0, 100.5, 101.0]})
    medium = _study_frame([0.4, 0.5, 0.6], metric_values={"final_soc_percent": [100.0, 103.0, 104.0]})
    high = _study_frame([0.4, 0.5, 0.6], metric_values={"final_soc_percent": [100.0, 110.0, 120.0]})

    low_analysis = explain_parameter_study(low, "cw_a_m2", 0.5).battery_analyses["LiPo"][0]
    medium_analysis = explain_parameter_study(medium, "cw_a_m2", 0.5).battery_analyses["LiPo"][0]
    high_analysis = explain_parameter_study(high, "cw_a_m2", 0.5).battery_analyses["LiPo"][0]

    assert low_analysis.sensitivity == "geringer Einfluss"
    assert medium_analysis.sensitivity == "mittlerer Einfluss"
    assert high_analysis.sensitivity == "starker Einfluss"