"""Erzeugung eines PDF-Berichts aus gespeicherten Simulationsartefakten."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


REPORT_TITLE = "E-Bike-Simulationsbericht"
FOOTER_TEXT = "E-Bike Route Simulation"
PDF_FILENAME = "simulation_report.pdf"
TEMP_PDF_FILENAME = "simulation_report.tmp.pdf"
PLOT_ORDER = (
    "plot/hoehenprofil_fahrt.png",
    "plot/geschwindigkeit_roh_geglaettet.png",
    "plot/zeitverlauf_lipo.png",
    "plot/zeitverlauf_nmc.png",
    "plot/ladezustand_vergleich.png",
)


class PdfReportError(RuntimeError):
    """Basisfehler für die PDF-Erzeugung."""


class PdfReportDataError(PdfReportError):
    """Fehlerhafte oder unvollständige Eingabedaten für den Bericht."""


def generate_simulation_pdf(run_directory: Path) -> Path:
    """Generate or return the cached PDF report for one simulation run."""

    run_directory = Path(run_directory)
    metadata = _load_metadata(run_directory)
    track_df = _load_csv(run_directory / "track.csv", "Track")
    simulation_frames = _load_simulation_frames(run_directory)
    if not simulation_frames:
        raise PdfReportDataError("Keine Simulations-CSV-Dateien gefunden.")

    final_pdf = run_directory / PDF_FILENAME
    temp_pdf = run_directory / TEMP_PDF_FILENAME
    inputs = [run_directory / "metadata.json", run_directory / "track.csv"]
    inputs.extend(run_directory / f"simulation_{name.lower()}.csv" for name in simulation_frames)
    inputs.extend(_existing_plot_paths(run_directory, metadata))
    if final_pdf.exists() and _is_cache_valid(final_pdf, inputs):
        return final_pdf

    story = _build_story(run_directory, metadata, track_df, simulation_frames)
    doc = SimpleDocTemplate(
        str(temp_pdf),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=REPORT_TITLE,
        author="Copilot",
    )

    try:
        doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
        temp_pdf.replace(final_pdf)
    except Exception:
        if temp_pdf.exists():
            temp_pdf.unlink(missing_ok=True)
        raise
    return final_pdf


def _build_story(
    run_directory: Path,
    metadata: dict,
    track_df: pd.DataFrame,
    simulation_frames: dict[str, pd.DataFrame],
) -> list:
    styles = _styles()
    route_summary = _route_summary(metadata, track_df)
    bike_config = metadata.get("bike_config", {}) if isinstance(metadata.get("bike_config"), dict) else {}
    battery_options = metadata.get("battery_options", {}) if isinstance(metadata.get("battery_options"), dict) else {}
    smoothing = metadata.get("smoothing", {}) if isinstance(metadata.get("smoothing"), dict) else {}
    summaries = metadata.get("summaries", {}) if isinstance(metadata.get("summaries"), dict) else {}

    story: list = []
    story.append(Paragraph(REPORT_TITLE, styles["TitleCenter"]))
    story.append(Spacer(1, 6 * mm))
    story.extend(
        _key_value_table(
            [
                ("Projektname", "Abschlussprojekt E-Bike Route Simulation"),
                ("Bericht erstellt am", _format_datetime(metadata.get("created_at_utc"))),
                ("Simulations-Run-ID", str(metadata.get("run_id", run_directory.name))),
                ("GPS-Eingabedatei", str(metadata.get("source_file_name", "n. a."))),
                ("Ausgewählte Akkutypen", _selected_batteries_text(battery_options, simulation_frames)),
                ("Geschwindigkeitsglättung", _smoothing_status_text(smoothing)),
            ],
            styles,
        )
    )

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Fahrradkonfiguration", styles["Heading2"]))
    story.extend(
        _key_value_table(
            [
                ("Fahrermasse [kg]", _de_number(bike_config.get("masse_fahrer_kg"), 1)),
                ("Fahrradmasse [kg]", _de_number(bike_config.get("masse_rad_kg"), 1)),
                ("Gesamtmasse [kg]", _de_number(_bike_mass_total(bike_config), 1)),
                ("cwA-Wert [m²]", _de_number(bike_config.get("cw_a_m2"), 3)),
                ("Raddurchmesser [Zoll]", _de_number(bike_config.get("raddurchmesser_inch"), 1)),
                ("Rollwiderstandskoeffizient [-]", _de_number(bike_config.get("rollwiderstandkoeffizient"), 4)),
            ],
            styles,
        )
    )

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Akkukonfiguration", styles["Heading2"]))
    story.extend(
        _key_value_table(
            [
                ("Ausgewählte Batterietypen", _selected_batteries_text(battery_options, simulation_frames)),
                ("Nennkapazität [Ah]", _de_number(battery_options.get("capacity_ah"), 2)),
                ("Initialer SoC [%]", _de_percent(battery_options.get("initial_soc"), 2)),
                ("Parallele Packs/Zellen", _de_number(battery_options.get("n_parallel"), 0)),
            ],
            styles,
        )
    )

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Geschwindigkeitsglättung", styles["Heading2"]))
    smoothing_rows = [
        ("Status", "Aktiviert" if smoothing.get("enabled") else "Deaktiviert"),
        ("min_interval_s", _de_number(smoothing.get("min_interval_s"), 2)),
        ("max_gap_s", _de_number(smoothing.get("max_gap_s"), 2)),
        ("median_window_s", _de_number(smoothing.get("median_window_s"), 2)),
        ("time_constant_s", _de_number(smoothing.get("time_constant_s"), 2)),
        ("max_reasonable_speed_kmh", _de_number(smoothing.get("max_reasonable_speed_kmh"), 1)),
    ]
    story.extend(_key_value_table(smoothing_rows, styles))
    if not smoothing.get("enabled", False):
        story.append(Paragraph("Die Geschwindigkeit wurde für die Simulation direkt aus der Rohkurve verwendet.", styles["BodyText"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Streckenübersicht", styles["Heading2"]))
    route_rows = [
        ("Gesamtdistanz [km]", _de_number(route_summary.get("total_distance_km"), 2)),
        ("Gesamtdauer", _format_duration(route_summary.get("duration_s"))),
        ("Anzahl GPS-Punkte", _de_number(route_summary.get("gps_point_count"), 0)),
        ("Durchschnittsgeschwindigkeit [km/h]", _de_number(route_summary.get("average_speed_kmh"), 2)),
        ("Maximale Rohgeschwindigkeit [km/h]", _de_number(route_summary.get("max_raw_speed_kmh"), 2)),
        ("Maximale aktive Geschwindigkeit [km/h]", _de_number(route_summary.get("max_active_speed_kmh"), 2)),
        ("Höhengewinn [m]", _de_number(route_summary.get("elevation_gain_m"), 1)),
        ("Kurze Messintervalle", _de_number(route_summary.get("short_interval_count"), 0)),
        ("Große Zeitlücken", _de_number(route_summary.get("large_gap_count"), 0)),
        ("Erkannte Geschwindigkeitsausreißer", _de_number(route_summary.get("speed_outlier_count"), 0)),
        ("Gültige Filterstützstellen", _de_number(route_summary.get("valid_smoothing_support_point_count"), 0)),
    ]
    story.extend(_key_value_table([(label, value) for label, value in route_rows if value != "n. a."], styles))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Akkuergebnisse", styles["Heading2"]))
    for battery_name, frame in simulation_frames.items():
        summary = _battery_summary(metadata, summaries, battery_name, frame, route_summary)
        table_flowables = _battery_result_block(battery_name, summary, styles)
        story.extend(table_flowables)
        story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Existierende Diagramme", styles["Heading2"]))
    images = _plot_images(run_directory, metadata, styles)
    if images:
        story.extend(images)
    else:
        story.append(Paragraph("Keine statischen Diagramme verfügbar.", styles["BodyText"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Modellhinweis", styles["Heading2"]))
    story.append(
        Paragraph(
            "Die dargestellten Ergebnisse basieren auf den eingelesenen GPS-Daten, der gewählten Konfiguration und dem implementierten mathematischen Modell. Sie stellen keine garantierten Messwerte eines realen Fahrzeugs dar.",
            styles["BodyText"],
        )
    )
    return story


def _battery_result_block(battery_name: str, summary: dict, styles: dict) -> list:
    warning = None
    if not summary.get("completed_route", True):
        warning = Paragraph(
            f"<font color='#b00020'><b>Warnung:</b> Die {battery_name}-Simulation hat die Strecke nicht vollständig abgeschlossen.</font>",
            styles["Warning"],
        )

    rows = [
        ("Finaler SoC [%]", _de_percent(summary.get("final_soc_percent"), 2)),
        ("SoC-Verbrauch [%]", _de_percent(summary.get("soc_consumption_percent"), 2)),
        ("Traktionsenergie [Wh]", _de_number(summary.get("traction_energy_Wh"), 1)),
        ("Bremsenergie [Wh]", _de_number(summary.get("braking_energy_Wh"), 1)),
        ("Maximale Leistung [W]", _de_number(summary.get("max_power_W"), 1)),
        ("Maximaler Motorstrom [A]", _de_number(summary.get("max_motor_current_A"), 1)),
        ("Maximales Drehmoment [Nm]", _de_number(summary.get("max_torque_Nm"), 1)),
        ("Minimale Akkuspannung [V]", _de_number(summary.get("minimum_voltage_V"), 2)),
        ("Simulierte GPS-Punkte", _de_number(summary.get("simulated_point_count"), 0)),
        ("Erwartete GPS-Punkte", _de_number(summary.get("expected_point_count"), 0)),
        ("Strecke vollständig abgeschlossen", "Ja" if summary.get("completed_route") else "Nein"),
        ("Letzter simulierter Punkt", _end_point_text(summary.get("end_point"))),
    ]
    table = _create_table(rows, styles, highlight_warning=not bool(summary.get("completed_route", True)))
    block = [Paragraph(battery_name, styles["Heading3"])]
    if warning is not None:
        block.append(warning)
    block.append(table)
    return [KeepTogether(block)]


def _battery_summary(
    metadata: dict,
    summaries: dict,
    battery_name: str,
    simulation_df: pd.DataFrame,
    route_summary: dict,
) -> dict:
    summary = dict(summaries.get(battery_name, {})) if isinstance(summaries.get(battery_name, {}), dict) else {}
    expected_count = summary.get("expected_point_count")
    if expected_count is None:
        expected_count = route_summary.get("gps_point_count")
    if expected_count is None:
        expected_count = int(len(simulation_df))
    battery_options = metadata.get("battery_options", {}) if isinstance(metadata.get("battery_options"), dict) else {}
    initial_soc = _coerce_float(battery_options.get("initial_soc"))
    if initial_soc is None and not simulation_df.empty and "soc" in simulation_df.columns:
        initial_soc = float(simulation_df["soc"].iloc[0])
    if not summary:
        summary = _summary_from_dataframe(simulation_df, initial_soc, int(expected_count))
    else:
        summary.setdefault("simulated_point_count", int(len(simulation_df)))
        summary.setdefault("expected_point_count", int(expected_count))
        summary.setdefault("end_point", int(len(simulation_df) - 1) if len(simulation_df) else None)
        if "completed_route" not in summary:
            summary["completed_route"] = int(summary["simulated_point_count"]) == int(summary["expected_point_count"])
    return summary


def _summary_from_dataframe(simulation_df: pd.DataFrame, initial_soc: float | None, expected_point_count: int) -> dict:
    if simulation_df.empty:
        raise PdfReportDataError("Eine Simulations-CSV enthält keine Daten.")
    dt = pd.to_numeric(simulation_df.get("dt_s", pd.Series(dtype=float)), errors="coerce").fillna(0.0).clip(lower=0.0)
    power = pd.to_numeric(simulation_df.get("leistung_W", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    final_soc = float(pd.to_numeric(simulation_df["soc"], errors="coerce").iloc[-1])
    initial_soc = float(initial_soc if initial_soc is not None else simulation_df["soc"].iloc[0])
    traction = float((power.clip(lower=0.0) * dt).sum() / 3600.0)
    braking = float(((-power.clip(upper=0.0)) * dt).sum() / 3600.0)
    return {
        "final_soc_percent": final_soc * 100.0,
        "soc_consumption_percent": (initial_soc - final_soc) * 100.0,
        "traction_energy_Wh": traction,
        "braking_energy_Wh": braking,
        "max_power_W": float(pd.to_numeric(simulation_df["leistung_W"], errors="coerce").max()),
        "max_motor_current_A": float(pd.to_numeric(simulation_df["motorstrom_A"], errors="coerce").max()),
        "max_torque_Nm": float(pd.to_numeric(simulation_df["drehmoment_Nm"], errors="coerce").max()),
        "minimum_voltage_V": float(pd.to_numeric(simulation_df["spannung_V"], errors="coerce").min()),
        "simulated_point_count": int(len(simulation_df)),
        "expected_point_count": int(expected_point_count),
        "completed_route": int(len(simulation_df)) == int(expected_point_count),
        "end_point": int(len(simulation_df) - 1),
    }


def _route_summary(metadata: dict, track_df: pd.DataFrame) -> dict:
    route_summary = metadata.get("route_summary", {}) if isinstance(metadata.get("route_summary", {}), dict) else {}
    if route_summary:
        return route_summary
    df = track_df.copy()
    return {
        "total_distance_km": float(pd.to_numeric(df.get("distanz_m", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum() / 1000.0),
        "duration_s": float(_route_duration(df)),
        "gps_point_count": int(len(df)),
        "average_speed_kmh": float(_safe_mean_speed(df)),
        "max_raw_speed_kmh": float(pd.to_numeric(df.get("geschwindigkeit_roh_ms", pd.Series(dtype=float)), errors="coerce").max() * 3.6) if "geschwindigkeit_roh_ms" in df.columns else None,
        "max_active_speed_kmh": float(pd.to_numeric(df.get("geschwindigkeit_ms", pd.Series(dtype=float)), errors="coerce").max() * 3.6) if "geschwindigkeit_ms" in df.columns else None,
        "elevation_gain_m": float(pd.to_numeric(df.get("ele", pd.Series(dtype=float)), errors="coerce").diff().fillna(0.0).clip(lower=0.0).sum()),
        "short_interval_count": int(pd.to_numeric(df.get("filter_kurzes_intervall", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if "filter_kurzes_intervall" in df.columns else None,
        "large_gap_count": int(pd.to_numeric(df.get("filter_grosse_zeitluecke", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if "filter_grosse_zeitluecke" in df.columns else None,
        "speed_outlier_count": int(pd.to_numeric(df.get("filter_geschwindigkeitsausreisser", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if "filter_geschwindigkeitsausreisser" in df.columns else None,
        "valid_smoothing_support_point_count": int(pd.to_numeric(df.get("filter_gueltige_stuetzstelle", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if "filter_gueltige_stuetzstelle" in df.columns else None,
    }


def _load_metadata(run_directory: Path) -> dict:
    metadata_path = run_directory / "metadata.json"
    if not metadata_path.is_file():
        raise PdfReportDataError("metadata.json fehlt im Ergebnisverzeichnis.")
    with metadata_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise PdfReportDataError("metadata.json enthält kein JSON-Objekt.")
    return data


def _load_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise PdfReportDataError(f"{label}-CSV fehlt: {path.name}.")
    return pd.read_csv(path)


def _load_simulation_frames(run_directory: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for name in ("LiPo", "NMC"):
        path = run_directory / f"simulation_{name.lower()}.csv"
        if path.is_file():
            frames[name] = pd.read_csv(path)
    return frames


def _existing_plot_paths(run_directory: Path, metadata: dict) -> list[Path]:
    plot_files = metadata.get("plot_files", {}) if isinstance(metadata.get("plot_files", {}), dict) else {}
    candidates = [plot_files.get(key) for key in ("elevation", "speed_comparison", "lipo", "nmc", "soc_comparison")]
    paths: list[Path] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = run_directory / Path(str(candidate))
        if path.is_file():
            paths.append(path)
    if not paths:
        for relative in PLOT_ORDER:
            path = run_directory / relative
            if path.is_file():
                paths.append(path)
    return paths


def _plot_images(run_directory: Path, metadata: dict, styles: dict) -> list:
    images: list = []
    plot_paths = _existing_plot_paths(run_directory, metadata)
    for path in plot_paths:
        images.append(_scaled_image(path, max_width=172 * mm, max_height=90 * mm))
        images.append(Spacer(1, 3 * mm))
    return images


def _scaled_image(path: Path, max_width: float, max_height: float) -> Image:
    image = Image(str(path))
    width = float(image.imageWidth)
    height = float(image.imageHeight)
    scale = min(max_width / width, max_height / height, 1.0)
    image.drawWidth = width * scale
    image.drawHeight = height * scale
    return image


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles = {
        "TitleCenter": ParagraphStyle(
            "TitleCenter",
            parent=base["Title"],
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "Heading2": ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            spaceBefore=8,
            spaceAfter=4,
        ),
        "Heading3": ParagraphStyle(
            "Heading3",
            parent=base["Heading3"],
            spaceBefore=6,
            spaceAfter=4,
        ),
        "BodyText": ParagraphStyle(
            "BodyText",
            parent=base["BodyText"],
            leading=13,
        ),
        "Warning": ParagraphStyle(
            "Warning",
            parent=base["BodyText"],
            textColor=colors.HexColor("#b00020"),
            leading=13,
        ),
    }
    return styles


def _key_value_table(rows: list[tuple[str, object]], styles: dict) -> list:
    table = _create_table(rows, styles)
    return [table]


def _create_table(rows: list[tuple[str, object]], styles: dict, highlight_warning: bool = False) -> Table:
    data = [[Paragraph(f"<b>{label}</b>", styles["BodyText"]), Paragraph(str(value), styles["BodyText"])] for label, value in rows]
    table = Table(data, colWidths=[65 * mm, 105 * mm], hAlign="LEFT")
    style_commands = [
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#6c757d")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#adb5bd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if highlight_warning:
        style_commands.append(("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff3cd")))
    table.setStyle(TableStyle(style_commands))
    return table


def _format_datetime(value: object) -> str:
    if not value:
        return "n. a."
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%d.%m.%Y %H:%M Uhr")


def _selected_batteries_text(battery_options: dict, simulation_frames: dict[str, pd.DataFrame]) -> str:
    selected = []
    for name in ("LiPo", "NMC"):
        if name in simulation_frames:
            selected.append(name)
    if not selected and isinstance(battery_options, dict):
        if battery_options.get("lipo"):
            selected.append("LiPo")
        if battery_options.get("nmc"):
            selected.append("NMC")
    return ", ".join(selected) if selected else "n. a."


def _smoothing_status_text(smoothing: dict) -> str:
    if not isinstance(smoothing, dict):
        return "n. a."
    status = "Aktiv" if smoothing.get("enabled") else "Deaktiviert"
    return f"{status}"


def _bike_mass_total(bike_config: dict) -> object:
    rider = _coerce_float(bike_config.get("masse_fahrer_kg"))
    bike = _coerce_float(bike_config.get("masse_rad_kg"))
    if rider is None or bike is None:
        return "n. a."
    return rider + bike


def _route_duration(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_mean_speed(df: pd.DataFrame) -> float:
    if "distanz_m" not in df.columns or "time" not in df.columns or df.empty:
        return 0.0
    distance = pd.to_numeric(df["distanz_m"], errors="coerce").fillna(0.0).sum()
    duration = _route_duration((pd.to_datetime(df["time"]).iloc[-1] - pd.to_datetime(df["time"]).iloc[0]).total_seconds())
    if duration <= 0:
        return 0.0
    return float(distance / duration * 3.6)


def _end_point_text(value: object) -> str:
    endpoint = _coerce_float(value)
    if endpoint is None:
        return "n. a."
    return f"Punkt {int(endpoint) + 1}"


def _de_number(value: object, decimals: int) -> str:
    number = _coerce_float(value)
    if number is None:
        return "n. a."
    return f"{number:.{decimals}f}".replace(".", ",")


def _de_percent(value: object, decimals: int) -> str:
    return _de_number(value, decimals)


def _format_duration(value: object) -> str:
    seconds = _coerce_float(value)
    if seconds is None:
        return "n. a."
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d} h"


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(number):
        return None
    return number


def _is_cache_valid(pdf_path: Path, inputs: Iterable[Path]) -> bool:
    try:
        pdf_mtime = pdf_path.stat().st_mtime
    except FileNotFoundError:
        return False
    newest_input = 0.0
    for path in inputs:
        if not path.is_file():
            continue
        newest_input = max(newest_input, path.stat().st_mtime)
    return pdf_mtime >= newest_input


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(doc.leftMargin, 10 * mm, FOOTER_TEXT)
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Seite {doc.page}")
    canvas.restoreState()
