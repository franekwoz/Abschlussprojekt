"""Deterministische Interpretation von Parameterstudien."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .parameter_study_service import VALID_PARAMETERS


SENSITIVITY_LOW_THRESHOLD_PERCENT = 2.0
SENSITIVITY_HIGH_THRESHOLD_PERCENT = 10.0
NUMERICAL_TOLERANCE_SCALE = 1e-6
RELATIVE_CHANGE_EPSILON = 1e-12
BASELINE_ABS_TOLERANCE = 1e-9
BASELINE_REL_TOLERANCE = 1e-9


@dataclass(frozen=True)
class MetricAnalysis:
    metric_name: str
    label: str
    unit: str
    trend: str
    minimum_value: float | None
    minimum_parameter_value: float | None
    maximum_value: float | None
    maximum_parameter_value: float | None
    first_value: float | None
    last_value: float | None
    absolute_change: float | None
    relative_change_percent: float | None
    correlation: float | None
    regression_slope: float | None
    r_squared: float | None
    sensitivity: str
    text: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ParameterStudyExplanation:
    parameter_name: str
    parameter_label: str
    parameter_unit: str
    baseline_value: float
    nearest_study_value: float
    exact_baseline_included: bool
    summary: str
    physical_explanation: str
    battery_analyses: dict[str, tuple[MetricAnalysis, ...]]
    battery_comparison: tuple[str, ...]
    warnings: tuple[str, ...]


PARAMETER_DEFINITIONS: dict[str, dict[str, object]] = {
    "masse_fahrer_kg": {
        "label": "Fahrermasse",
        "unit": "kg",
        "format_decimals": 1,
        "physical_explanation": (
            "Die Fahrermasse trägt zur Gesamtmasse des Systems bei. Eine höhere Masse erhöht"
            " typischerweise die benötigte Steigkraft, den Rollwiderstand und den Energiebedarf"
            " bei Beschleunigungen. Der genaue Effekt hängt stark vom Höhenprofil der Strecke ab."
        ),
    },
    "masse_rad_kg": {
        "label": "Fahrradmasse",
        "unit": "kg",
        "format_decimals": 1,
        "physical_explanation": (
            "Die Fahrradmasse trägt ebenfalls zur Gesamtmasse bei. Ihre translatorische Wirkung"
            " ist im aktuellen Modell ähnlich wie die Fahrermasse. Eine zusätzliche Betrachtung"
            " der Radträgheit wird nicht eingeführt, solange sie im Modell nicht implementiert ist."
        ),
    },
    "cw_a_m2": {
        "label": "cwA-Wert",
        "unit": "m²",
        "format_decimals": 3,
        "physical_explanation": (
            "cwA beschreibt die effektive aerodynamische Stirnfläche. Die Luftwiderstandskraft"
            " wächst näherungsweise mit dem Quadrat der Geschwindigkeit, die dazugehörige Leistung"
            " näherungsweise mit der dritten Potenz. Der Effekt ist normalerweise auf schnelleren"
            " Streckenabschnitten am stärksten."
        ),
    },
    "rollwiderstandkoeffizient": {
        "label": "Rollwiderstandskoeffizient",
        "unit": "-",
        "format_decimals": 4,
        "physical_explanation": (
            "Der Rollwiderstandskoeffizient bestimmt zusammen mit Masse und Schwerkraft die"
            " Rollwiderstandskraft. Ein größerer Wert erhöht normalerweise die benötigte"
            " Traktionskraft und den Energiebedarf. Der tatsächliche Einfluss hängt von Strecke,"
            " Masse und Höhenprofil ab."
        ),
    },
    "raddurchmesser_inch": {
        "label": "Raddurchmesser",
        "unit": "Zoll",
        "format_decimals": 1,
        "physical_explanation": (
            "Der Raddurchmesser beeinflusst das Verhältnis zwischen Fahrzeuggeschwindigkeit,"
            " Raddrehzahl, Motordrehzahl und Drehmoment. Der genaue Effekt hängt davon ab, wie"
            " EBike, Motor und EBikeSimulator den Raddurchmesser aktuell verwenden. Es wird"
            " nicht behauptet, dass ein größeres oder kleineres Rad grundsätzlich effizienter ist;"
            " die Schlussfolgerung basiert auf den berechneten Ergebnissen."
        ),
    },
}

METRIC_DEFINITIONS: dict[str, dict[str, object]] = {
    "final_soc_percent": {"label": "Finaler SoC", "unit": "%", "decimals": 2},
    "soc_consumption_percent": {"label": "SoC-Verbrauch", "unit": "%", "decimals": 2},
    "traction_energy_Wh": {"label": "Traktionsenergie", "unit": "Wh", "decimals": 1},
    "braking_energy_Wh": {"label": "Bremsenergie", "unit": "Wh", "decimals": 1},
    "max_power_W": {"label": "Maximale Leistung", "unit": "W", "decimals": 1},
    "max_motor_current_A": {"label": "Maximaler Motorstrom", "unit": "A", "decimals": 1},
    "max_torque_Nm": {"label": "Maximales Drehmoment", "unit": "Nm", "decimals": 1},
    "minimum_voltage_V": {"label": "Minimale Akkuspannung", "unit": "V", "decimals": 2},
    "completed_route": {"label": "Strecke vollständig abgeschlossen", "unit": "-", "decimals": 0},
}

INTERPRETED_METRICS = (
    "final_soc_percent",
    "soc_consumption_percent",
    "traction_energy_Wh",
    "max_power_W",
    "max_motor_current_A",
    "max_torque_Nm",
    "minimum_voltage_V",
    "braking_energy_Wh",
    "completed_route",
)


def explain_parameter_study(
    results: pd.DataFrame,
    parameter_name: str,
    baseline_value: float,
) -> ParameterStudyExplanation:
    """Erzeugt eine deutsche, datenbasierte Interpretation einer Parameterstudie."""

    if parameter_name not in VALID_PARAMETERS:
        raise ValueError("Unbekannte Fahrrad-Eigenschaft.")
    if parameter_name not in PARAMETER_DEFINITIONS:
        raise ValueError(f"Für '{parameter_name}' liegt keine Parameterbeschreibung vor.")
    if results.empty:
        raise ValueError("Die Parameterstudie enthält keine Ergebnisse.")

    parameter_definition = PARAMETER_DEFINITIONS[parameter_name]
    parameter_label = str(parameter_definition["label"])
    parameter_unit = str(parameter_definition["unit"])

    parameter_values = pd.to_numeric(results["parameter_value"], errors="coerce")
    finite_parameter_values = parameter_values.replace([np.inf, -np.inf], np.nan).dropna()
    if finite_parameter_values.empty:
        raise ValueError("Die Parameterstudie enthält keine gültigen Parameterwerte.")

    exact_baseline_included = _contains_value(
        finite_parameter_values.to_numpy(dtype=float),
        float(baseline_value),
    )
    nearest_study_value = _nearest_value(finite_parameter_values.to_numpy(dtype=float), float(baseline_value))

    battery_analyses: dict[str, tuple[MetricAnalysis, ...]] = {}
    warnings: list[str] = []

    completed_counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    study_values = finite_parameter_values.to_numpy(dtype=float)
    for battery_type, battery_df in results.groupby("battery_type", sort=True):
        battery_analysis: list[MetricAnalysis] = []
        total_counts[battery_type] = int(len(battery_df))
        if "completed_route" in battery_df.columns:
            completed_counts[battery_type] = int(pd.to_numeric(battery_df["completed_route"], errors="coerce").fillna(0).astype(int).sum())
        for metric_name in INTERPRETED_METRICS:
            battery_analysis.append(
                _analyze_metric(
                    battery_df=battery_df,
                    parameter_name=parameter_name,
                    parameter_values=study_values,
                    metric_name=metric_name,
                    baseline_value=float(baseline_value),
                    exact_baseline_included=exact_baseline_included,
                    nearest_study_value=nearest_study_value,
                )
            )
        battery_analyses[str(battery_type)] = tuple(battery_analysis)

    if len(set(total_counts.values())) > 1:
        warnings.append(
            "Die Batterietypen enthalten unterschiedlich viele Studienpunkte. Direkte Vergleiche sind daher nur eingeschränkt belastbar."
        )
    if completed_counts and len(set(completed_counts.values())) > 1:
        warnings.append(
            "Die Batterietypen weisen unterschiedlich viele vollständig abgeschlossene Läufe auf. Nicht abgeschlossene Fahrten sind nicht direkt mit vollständigen Fahrten vergleichbar."
        )

    summary = _build_summary(
        results=results,
        parameter_name=parameter_name,
        parameter_label=parameter_label,
        parameter_unit=parameter_unit,
        baseline_value=float(baseline_value),
        exact_baseline_included=exact_baseline_included,
        nearest_study_value=nearest_study_value,
        battery_analyses=battery_analyses,
    )
    physical_explanation = _build_physical_explanation(
        parameter_name=parameter_name,
        parameter_label=parameter_label,
        parameter_unit=parameter_unit,
        baseline_value=float(baseline_value),
        exact_baseline_included=exact_baseline_included,
        nearest_study_value=nearest_study_value,
    )
    battery_comparison = _build_battery_comparison(results, battery_analyses, parameter_name, parameter_label, parameter_unit)

    return ParameterStudyExplanation(
        parameter_name=parameter_name,
        parameter_label=parameter_label,
        parameter_unit=parameter_unit,
        baseline_value=float(baseline_value),
        nearest_study_value=float(nearest_study_value),
        exact_baseline_included=exact_baseline_included,
        summary=summary,
        physical_explanation=physical_explanation,
        battery_analyses=battery_analyses,
        battery_comparison=tuple(battery_comparison),
        warnings=tuple(warnings + _collect_global_warnings(results, parameter_name)),
    )


def _collect_global_warnings(results: pd.DataFrame, parameter_name: str) -> list[str]:
    warnings: list[str] = []
    for required_column in ("parameter_name", "parameter_value", "battery_type"):
        if required_column not in results.columns:
            warnings.append(f"Die erforderliche Spalte '{required_column}' fehlt in den Ergebnissen.")
    if "parameter_name" in results.columns:
        parameter_names = results["parameter_name"].dropna().astype(str).unique().tolist()
        if parameter_names and any(name != parameter_name for name in parameter_names):
            warnings.append("Die Ergebnisdaten enthalten Parameterwerte für eine andere Fahrrad-Eigenschaft als die ausgewertete Studie.")
    if results["parameter_value"].isna().any():
        warnings.append("Einige Parameterwerte sind ungültig und wurden ignoriert.")
    duplicate_count = int(results["parameter_value"].duplicated().sum())
    if duplicate_count > 0:
        warnings.append("Es gibt doppelte Parameterwerte; diese werden in der Interpretation berücksichtigt, aber gesondert gewarnt.")
    for column in INTERPRETED_METRICS:
        if column not in results.columns:
            warnings.append(f"Die optionale Spalte '{column}' fehlt; die zugehörige Interpretation bleibt daher eingeschränkt.")
    return warnings


def _build_summary(
    results: pd.DataFrame,
    parameter_name: str,
    parameter_label: str,
    parameter_unit: str,
    baseline_value: float,
    exact_baseline_included: bool,
    nearest_study_value: float,
    battery_analyses: dict[str, tuple[MetricAnalysis, ...]],
) -> str:
    valid_values = pd.to_numeric(results["parameter_value"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().sort_values()
    study_range = f"{_format_parameter_value(parameter_name, float(valid_values.iloc[0]))} bis {_format_parameter_value(parameter_name, float(valid_values.iloc[-1]))} {parameter_unit}"
    baseline_text = (
        f"Der Ausgangswert der Fahrradkonfiguration beträgt {_format_parameter_value(parameter_name, baseline_value)} {parameter_unit}."
        if exact_baseline_included
        else f"Der Ausgangswert der Fahrradkonfiguration beträgt {_format_parameter_value(parameter_name, baseline_value)} {parameter_unit}; der nächstgelegene simulierte Stützpunkt liegt bei {_format_parameter_value(parameter_name, nearest_study_value)} {parameter_unit}."
    )

    primary_sentences: list[str] = []
    final_soc_analyses = {
        battery_type: _first_metric(analyses, "final_soc_percent")
        for battery_type, analyses in battery_analyses.items()
        if _first_metric(analyses, "final_soc_percent") is not None
    }
    for battery_type, analysis in final_soc_analyses.items():
        assert analysis is not None
        if analysis.first_value is not None and analysis.last_value is not None:
            primary_sentences.append(
                f"Für {battery_type} verändert sich der finale SoC von {_format_metric_value(analysis.metric_name, analysis.first_value)} {analysis.unit} auf {_format_metric_value(analysis.metric_name, analysis.last_value)} {analysis.unit}."
            )

    if not primary_sentences:
        primary_sentences.append("Für die gewählten Einstellungen liegen keine ausreichend verwertbaren Batterieresultate vor.")

    return (
        f"Die Parameterstudie untersucht {parameter_label} im Bereich {study_range}. "
        f"{baseline_text} "
        f"{_join_sentences(primary_sentences)}"
    )


def _build_physical_explanation(
    parameter_name: str,
    parameter_label: str,
    parameter_unit: str,
    baseline_value: float,
    exact_baseline_included: bool,
    nearest_study_value: float,
) -> str:
    definition = PARAMETER_DEFINITIONS[parameter_name]
    base_sentence = str(definition["physical_explanation"])
    threshold_sentence = (
        "Die Sensitivitätsklassifikation bezieht sich ausschließlich auf die ausgewählte Route, den untersuchten Parameterbereich, die gewählte Fahrradkonfiguration, die gewählte Batteriekonfiguration und das implementierte Modell; die Schwellenwerte sind keine allgemeingültigen physikalischen Gesetze."
    )
    baseline_sentence = (
        f"Der Ausgangswert beträgt {_format_parameter_value(parameter_name, baseline_value)} {parameter_unit}."
        if exact_baseline_included
        else f"Der Ausgangswert beträgt {_format_parameter_value(parameter_name, baseline_value)} {parameter_unit}; der nächstgelegene simulierte Stützpunkt liegt bei {_format_parameter_value(parameter_name, nearest_study_value)} {parameter_unit}."
    )
    return f"{parameter_label}: {base_sentence} {baseline_sentence} {threshold_sentence}"


def _build_battery_comparison(
    results: pd.DataFrame,
    battery_analyses: dict[str, tuple[MetricAnalysis, ...]],
    parameter_name: str,
    parameter_label: str,
    parameter_unit: str,
) -> list[str]:
    if len(battery_analyses) < 2:
        return []

    battery_names = list(sorted(battery_analyses))
    first, second = battery_names[0], battery_names[1]
    first_final = _first_metric(battery_analyses[first], "final_soc_percent")
    second_final = _first_metric(battery_analyses[second], "final_soc_percent")
    first_consumption = _first_metric(battery_analyses[first], "soc_consumption_percent")
    second_consumption = _first_metric(battery_analyses[second], "soc_consumption_percent")
    first_voltage = _first_metric(battery_analyses[first], "minimum_voltage_V")
    second_voltage = _first_metric(battery_analyses[second], "minimum_voltage_V")
    first_energy = _first_metric(battery_analyses[first], "traction_energy_Wh")
    second_energy = _first_metric(battery_analyses[second], "traction_energy_Wh")

    lines: list[str] = []
    if first_final and second_final and first_final.first_value is not None and second_final.first_value is not None:
        better = first if first_final.first_value > second_final.first_value else second
        lines.append(
            f"Beim kleinsten untersuchten Parameterwert weist {better} den höheren finalen SoC auf."
        )
    if first_consumption and second_consumption and first_consumption.first_value is not None and second_consumption.first_value is not None:
        lower = first if first_consumption.first_value < second_consumption.first_value else second
        lines.append(
            f"Beim kleinsten untersuchten Parameterwert hat {lower} den geringeren SoC-Verbrauch."
        )
    if first_voltage and second_voltage and first_voltage.minimum_value is not None and second_voltage.minimum_value is not None:
        lower_voltage = first if first_voltage.minimum_value < second_voltage.minimum_value else second
        lines.append(
            f"Der niedrigste Spannungswert fällt bei {lower_voltage} geringer aus."
        )
    if first_energy and second_energy and first_energy.first_value is not None and second_energy.first_value is not None:
        lines.append(
            f"Die Traktionsenergie liegt im Ausgangspunkt bei {first} bei {_format_metric_value('traction_energy_Wh', first_energy.first_value)} Wh und bei {second} bei {_format_metric_value('traction_energy_Wh', second_energy.first_value)} Wh."
        )

    if lines:
        lines.append(
            f"Die Sensitivität wird nur für die ausgewählte Route, den Parameterbereich {parameter_label} ({parameter_unit}), die gewählte Fahrrad- und Batteriekonfiguration sowie das implementierte Modell interpretiert."
        )

    return lines


def _analyze_metric(
    *,
    battery_df: pd.DataFrame,
    parameter_name: str,
    parameter_values: np.ndarray,
    metric_name: str,
    baseline_value: float,
    exact_baseline_included: bool,
    nearest_study_value: float,
) -> MetricAnalysis:
    definition = METRIC_DEFINITIONS[metric_name]
    label = str(definition["label"])
    unit = str(definition["unit"])

    warnings: list[str] = []
    if metric_name not in battery_df.columns:
        warnings.append(f"Die Spalte '{metric_name}' fehlt für den Akkutyp {battery_df['battery_type'].iloc[0] if 'battery_type' in battery_df.columns and len(battery_df) else 'unbekannt'}.")
        return MetricAnalysis(
            metric_name=metric_name,
            label=label,
            unit=unit,
            trend="nicht bestimmbar",
            minimum_value=None,
            minimum_parameter_value=None,
            maximum_value=None,
            maximum_parameter_value=None,
            first_value=None,
            last_value=None,
            absolute_change=None,
            relative_change_percent=None,
            correlation=None,
            regression_slope=None,
            r_squared=None,
            sensitivity="nicht bestimmbar",
            text=f"Für {label} liegen keine ausreichenden Daten vor.",
            warnings=tuple(warnings),
        )

    subset = pd.DataFrame(
        {
            "parameter_value": pd.to_numeric(battery_df["parameter_value"], errors="coerce"),
            "metric_value": _metric_as_numeric(metric_name, battery_df[metric_name]),
        }
    )
    invalid_count = int((~np.isfinite(subset["metric_value"].to_numpy(dtype=float))).sum())
    if invalid_count > 0:
        warnings.append(f"Für {label} wurden {invalid_count} nicht-endliche Werte ignoriert.")
    subset = subset.replace([np.inf, -np.inf], np.nan).dropna()
    if subset.empty:
        warnings.append(f"Für {label} bleiben nach der Bereinigung keine verwertbaren Werte übrig.")
        return MetricAnalysis(
            metric_name=metric_name,
            label=label,
            unit=unit,
            trend="nicht bestimmbar",
            minimum_value=None,
            minimum_parameter_value=None,
            maximum_value=None,
            maximum_parameter_value=None,
            first_value=None,
            last_value=None,
            absolute_change=None,
            relative_change_percent=None,
            correlation=None,
            regression_slope=None,
            r_squared=None,
            sensitivity="nicht bestimmbar",
            text=f"Für {label} liegen nach der Bereinigung keine verwertbaren Messwerte vor.",
            warnings=tuple(warnings),
        )

    subset = subset.sort_values("parameter_value", kind="mergesort")
    x = subset["parameter_value"].to_numpy(dtype=float)
    y = subset["metric_value"].to_numpy(dtype=float)

    duplicate_count = int(pd.Series(x).duplicated().sum())
    if duplicate_count > 0:
        warnings.append(f"Für {label} wurden {duplicate_count} doppelte Parameterwerte gefunden.")
    if len(x) < 2:
        warnings.append(f"Für {label} sind weniger als zwei verwertbare Stützpunkte vorhanden.")

    trend = _classify_trend(y)
    first_value = float(y[0]) if len(y) else None
    last_value = float(y[-1]) if len(y) else None
    absolute_change = None if first_value is None or last_value is None else last_value - first_value
    relative_change_percent = _relative_change_percent(first_value, last_value)
    minimum_index = int(np.argmin(y)) if len(y) else None
    maximum_index = int(np.argmax(y)) if len(y) else None
    minimum_value = float(y[minimum_index]) if minimum_index is not None else None
    maximum_value = float(y[maximum_index]) if maximum_index is not None else None
    minimum_parameter_value = float(x[minimum_index]) if minimum_index is not None else None
    maximum_parameter_value = float(x[maximum_index]) if maximum_index is not None else None
    reference_value = _reference_value(metric_name, battery_df, parameter_name, baseline_value, exact_baseline_included, nearest_study_value)
    sensitivity = _classify_sensitivity(minimum_value, maximum_value, reference_value)
    correlation = _pearson_correlation(x, y)
    regression_slope, r_squared = _linear_regression(x, y)

    text = _build_metric_text(
        metric_name=metric_name,
        label=label,
        unit=unit,
        x=x,
        y=y,
        trend=trend,
        sensitivity=sensitivity,
        first_value=first_value,
        last_value=last_value,
        absolute_change=absolute_change,
        relative_change_percent=relative_change_percent,
        minimum_value=minimum_value,
        minimum_parameter_value=minimum_parameter_value,
        maximum_value=maximum_value,
        maximum_parameter_value=maximum_parameter_value,
        correlation=correlation,
        regression_slope=regression_slope,
        r_squared=r_squared,
    )

    metric_warnings = list(warnings)
    if not np.isfinite(y).all():
        metric_warnings.append(f"{label} enthält nicht-endliche Werte und wurde bereinigt.")

    return MetricAnalysis(
        metric_name=metric_name,
        label=label,
        unit=unit,
        trend=trend,
        minimum_value=minimum_value,
        minimum_parameter_value=minimum_parameter_value,
        maximum_value=maximum_value,
        maximum_parameter_value=maximum_parameter_value,
        first_value=first_value,
        last_value=last_value,
        absolute_change=absolute_change,
        relative_change_percent=relative_change_percent,
        correlation=correlation,
        regression_slope=regression_slope,
        r_squared=r_squared,
        sensitivity=sensitivity,
        text=text,
        warnings=tuple(metric_warnings),
    )


def _metric_as_numeric(metric_name: str, series: pd.Series) -> pd.Series:
    if metric_name == "completed_route":
        return pd.Series(series).map(lambda value: 1.0 if bool(value) else 0.0)
    return pd.to_numeric(series, errors="coerce")


def _reference_value(
    metric_name: str,
    battery_df: pd.DataFrame,
    parameter_name: str,
    baseline_value: float,
    exact_baseline_included: bool,
    nearest_study_value: float,
) -> float | None:
    if metric_name not in battery_df.columns:
        return None
    parameter_series = pd.to_numeric(battery_df["parameter_value"], errors="coerce")
    metric_series = _metric_as_numeric(metric_name, battery_df[metric_name])
    df = pd.DataFrame({"parameter_value": parameter_series, "metric_value": metric_series}).replace([np.inf, -np.inf], np.nan).dropna()
    if df.empty:
        return None
    if exact_baseline_included:
        idx = (df["parameter_value"] - baseline_value).abs().idxmin()
        return float(df.loc[idx, "metric_value"])
    idx = (df["parameter_value"] - nearest_study_value).abs().idxmin()
    return float(df.loc[idx, "metric_value"])


def _classify_trend(values: np.ndarray) -> str:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size < 2:
        return "nicht bestimmbar"

    scale = max(float(np.max(np.abs(clean))), 1.0)
    tolerance = scale * NUMERICAL_TOLERANCE_SCALE
    differences = np.diff(clean)
    significant = differences[np.abs(differences) > tolerance]
    if significant.size == 0:
        return "annähernd konstant"
    if np.all(significant > 0):
        return "monoton steigend"
    if np.all(significant < 0):
        return "monoton fallend"
    return "nicht monoton"


def _relative_change_percent(first_value: float | None, last_value: float | None) -> float | None:
    if first_value is None or last_value is None:
        return None
    if abs(first_value) <= RELATIVE_CHANGE_EPSILON:
        return None
    return (last_value - first_value) / abs(first_value) * 100.0


def _classify_sensitivity(
    minimum_value: float | None,
    maximum_value: float | None,
    reference_value: float | None,
) -> str:
    if minimum_value is None or maximum_value is None or reference_value is None:
        return "nicht bestimmbar"
    span = abs(maximum_value - minimum_value)
    denominator = max(abs(reference_value), RELATIVE_CHANGE_EPSILON)
    relative_span_percent = span / denominator * 100.0
    if relative_span_percent < SENSITIVITY_LOW_THRESHOLD_PERCENT:
        return "geringer Einfluss"
    if relative_span_percent <= SENSITIVITY_HIGH_THRESHOLD_PERCENT:
        return "mittlerer Einfluss"
    return "starker Einfluss"


def _pearson_correlation(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return None
    corr = float(np.corrcoef(x, y)[0, 1])
    return corr if math.isfinite(corr) else None


def _linear_regression(x: np.ndarray, y: np.ndarray) -> tuple[float | None, float | None]:
    unique_x = np.unique(x)
    if len(unique_x) < 3 or len(np.unique(y)) < 2:
        return None, None
    scale = max(float(np.max(np.abs(y))), 1.0)
    if float(np.ptp(y)) <= scale * NUMERICAL_TOLERANCE_SCALE:
        return None, None
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot <= RELATIVE_CHANGE_EPSILON:
        r_squared = None
    else:
        r_squared = 1.0 - ss_res / ss_tot
    return float(slope), (float(r_squared) if r_squared is not None and math.isfinite(r_squared) else None)


def _build_metric_text(
    *,
    metric_name: str,
    label: str,
    unit: str,
    x: np.ndarray,
    y: np.ndarray,
    trend: str,
    sensitivity: str,
    first_value: float | None,
    last_value: float | None,
    absolute_change: float | None,
    relative_change_percent: float | None,
    minimum_value: float | None,
    minimum_parameter_value: float | None,
    maximum_value: float | None,
    maximum_parameter_value: float | None,
    correlation: float | None,
    regression_slope: float | None,
    r_squared: float | None,
) -> str:
    if first_value is None or last_value is None:
        return f"Für {label} liegen nach der Bereinigung nicht genügend verwertbare Werte vor."

    first_text = _format_metric_value(metric_name, first_value)
    last_text = _format_metric_value(metric_name, last_value)
    min_text = _format_metric_value(metric_name, minimum_value) if minimum_value is not None else "n. a."
    max_text = _format_metric_value(metric_name, maximum_value) if maximum_value is not None else "n. a."
    min_param_text = _format_parameter_value_from_array(x, minimum_parameter_value)
    max_param_text = _format_parameter_value_from_array(x, maximum_parameter_value)
    parts = [
        f"{label} verändert sich im untersuchten Bereich von {first_text} auf {last_text} {unit}."
    ]
    if absolute_change is not None:
        if metric_name == "completed_route":
            parts.append(
                f"Das entspricht einer Änderung von {_format_completion_value(first_value)} auf {_format_completion_value(last_value)}."
            )
        else:
            change_unit = "Prozentpunkte" if metric_name in {"final_soc_percent", "soc_consumption_percent"} else unit
            parts.append(
                f"Die absolute Änderung beträgt {_format_signed_metric_change(metric_name, absolute_change)} {change_unit}."
            )
    if relative_change_percent is None:
        parts.append("Eine relative Änderung kann wegen des Ausgangswerts nahe null nicht sinnvoll angegeben werden.")
    else:
        parts.append(f"Die relative Änderung beträgt {_format_signed_percent(relative_change_percent)} %.")
    parts.append(f"Der Verlauf ist {trend} und zeigt für die gewählte Konfiguration {sensitivity}.")
    if minimum_value is not None and maximum_value is not None:
        parts.append(
            f"Das Minimum liegt bei {min_text} {unit} am Parameterwert {min_param_text}, das Maximum bei {max_text} {unit} am Parameterwert {max_param_text}."
        )
    if correlation is not None:
        parts.append(f"Der Pearson-Korrelationskoeffizient beträgt {correlation:.3f}.")
    if regression_slope is not None and r_squared is not None:
        parts.append(
            f"Eine lineare Regression ergibt eine Steigung von {regression_slope:.4g} pro Parameter-Einheit mit R² = {r_squared:.3f}; annähernd linear wird nur bei R² ≥ 0,95 formuliert."
        )
    if metric_name == "completed_route":
        completed_count = int(np.sum(y >= 0.5))
        parts.append(f"In {completed_count} von {len(y)} ausgewerteten Punkten wurde die Route vollständig abgeschlossen.")
    return " ".join(parts)


def _contains_value(values: np.ndarray, target: float) -> bool:
    return bool(np.any(np.isclose(values, target, rtol=BASELINE_REL_TOLERANCE, atol=BASELINE_ABS_TOLERANCE)))


def _nearest_value(values: np.ndarray, target: float) -> float:
    index = int(np.argmin(np.abs(values - target)))
    return float(values[index])


def _first_metric(analyses: tuple[MetricAnalysis, ...], metric_name: str) -> MetricAnalysis | None:
    for analysis in analyses:
        if analysis.metric_name == metric_name:
            return analysis
    return None


def _format_parameter_value(parameter_name: str, value: float) -> str:
    decimals = int(PARAMETER_DEFINITIONS[parameter_name]["format_decimals"])
    return f"{value:.{decimals}f}".replace("-0.0", "0.0")


def _format_parameter_value_from_array(values: np.ndarray, value: float | None) -> str:
    if value is None or len(values) == 0:
        return "n. a."
    return f"{value:.2f}".replace("-0.0", "0.0")


def _format_metric_value(metric_name: str, value: float | None) -> str:
    if value is None:
        return "n. a."
    if metric_name == "completed_route":
        return _format_completion_value(value)
    if metric_name in {"final_soc_percent", "soc_consumption_percent"}:
        return f"{value:.2f}"
    if metric_name in {"traction_energy_Wh", "braking_energy_Wh", "max_power_W", "max_motor_current_A", "max_torque_Nm"}:
        return f"{value:.1f}"
    if metric_name == "minimum_voltage_V":
        return f"{value:.2f}"
    return f"{value:.3f}"


def _format_signed_metric_change(metric_name: str, value: float) -> str:
    if metric_name in {"final_soc_percent", "soc_consumption_percent"}:
        return f"{value:.2f}"
    if metric_name == "completed_route":
        return _format_completion_value(value)
    if metric_name in {"traction_energy_Wh", "braking_energy_Wh", "max_power_W", "max_motor_current_A", "max_torque_Nm"}:
        return f"{value:.1f}"
    if metric_name == "minimum_voltage_V":
        return f"{value:.2f}"
    return f"{value:.3f}"


def _format_signed_percent(value: float) -> str:
    return f"{value:.1f}"


def _format_completion_value(value: float) -> str:
    return "Ja" if value >= 0.5 else "Nein"


def _join_sentences(sentences: list[str]) -> str:
    return " ".join(sentence.strip() for sentence in sentences if sentence.strip())