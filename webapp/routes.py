from __future__ import annotations

import json
import logging
import math
import re
import uuid
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

from speed_smoothing import SpeedSmoothingConfig

from .services.parameter_study_explanation_service import explain_parameter_study
from .services.parameter_study_service import VALID_PARAMETERS, run_parameter_study
from .services.pdf_report_service import PdfReportDataError, PdfReportError, generate_simulation_pdf
from .services.simulation_service import run_simulation


logger = logging.getLogger(__name__)

bp = Blueprint("web", __name__)

BIKE_KEYS = (
    "masse_fahrer_kg",
    "masse_rad_kg",
    "cw_a_m2",
    "raddurchmesser_inch",
    "rollwiderstandkoeffizient",
)

RUN_ID_PATTERN = re.compile(r"^[0-9A-Fa-f]{32}$")


def defaults() -> tuple[dict, SpeedSmoothingConfig]:
    import yaml

    root = current_app.config["PROJECT_ROOT"]
    bike = yaml.safe_load((root / "data" / "bike_config.yaml").read_text(encoding="utf-8"))
    smoothing = SpeedSmoothingConfig.from_yaml(root / "data" / "speed_smoothing_config.yaml")
    return bike, smoothing


def positive(form, key: str, allow_zero: bool = False) -> float:
    try:
        value = float(form[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{key}: Zahl erforderlich.") from exc
    if not math.isfinite(value) or value < 0 or (not allow_zero and value <= 0):
        raise ValueError(f"{key}: ungueltiger Wert.")
    return value


def form_values(form) -> tuple[dict, SpeedSmoothingConfig, dict]:
    bike = {key: positive(form, key) for key in BIKE_KEYS}
    smoothing = replace(
        defaults()[1],
        enabled=("smoothing_enabled" in form),
        min_interval_s=positive(form, "min_interval_s"),
        max_gap_s=positive(form, "max_gap_s"),
        median_window_s=positive(form, "median_window_s"),
        time_constant_s=positive(form, "time_constant_s"),
        max_reasonable_speed_kmh=positive(form, "max_reasonable_speed_kmh"),
    )
    if smoothing.max_gap_s <= smoothing.min_interval_s:
        raise ValueError("max_gap_s muss groesser als min_interval_s sein.")
    battery = {
        "lipo": "lipo" in form,
        "nmc": "nmc" in form,
        "capacity_ah": positive(form, "capacity_ah"),
        "initial_soc": positive(form, "initial_soc", True),
        "n_parallel": int(positive(form, "n_parallel")),
    }
    if battery["initial_soc"] > 1:
        raise ValueError("Initialer SoC muss zwischen 0 und 1 liegen.")
    if not battery["lipo"] and not battery["nmc"]:
        raise ValueError("Bitte mindestens einen Akku auswaehlen.")
    return bike, smoothing, battery


def track_for_request() -> Path:
    root = current_app.config["PROJECT_ROOT"]
    upload = request.files.get("track")
    if not upload or not upload.filename:
        return root / "data" / "final_project_input_data.csv"
    name = secure_filename(upload.filename)
    if not name.lower().endswith(".csv"):
        raise ValueError("Nur CSV-Dateien sind erlaubt.")
    directory = current_app.config["WEB_OUTPUT"] / "uploads" / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    upload.save(path)
    df = pd.read_csv(path, sep=";")
    missing = {"time", "lat", "lon", "ele"} - set(df.columns)
    if missing:
        raise ValueError("Fehlende CSV-Spalten: " + ", ".join(sorted(missing)))
    if df.empty:
        raise ValueError("Die CSV-Datei ist leer.")
    pd.to_datetime(df.time, errors="raise")
    for column in ("lat", "lon", "ele"):
        if not pd.to_numeric(df[column], errors="coerce").map(math.isfinite).all():
            raise ValueError(f"Spalte {column} enthaelt ungueltige Werte.")
    return path


@bp.route("/")
def index():
    bike, smooth = defaults()
    return render_template("index.html", bike=bike, smooth=smooth)


@bp.route("/simulate", methods=["POST"])
def simulate():
    try:
        bike, smooth, battery = form_values(request.form)
        result = run_simulation(
            track_for_request(),
            bike,
            smooth,
            battery,
            current_app.config["WEB_OUTPUT"] / uuid.uuid4().hex,
        )
        session["run_dir"] = str(result.output_dir)
        return redirect(url_for("web.results", run_id=result.run_id))
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("web.index"))


@bp.route("/results/<run_id>")
def results(run_id: str):
    directory = resolve_session_run_directory(run_id, "run_dir")
    metadata = _load_json(directory / "metadata.json")
    track = _load_csv(directory / "track.csv")
    simulations = _load_simulations(directory)
    plot_files = _available_plot_files(directory, metadata)
    maps = _map_links(directory, run_id)
    return render_template(
        "simulation_results.html",
        run_id=run_id,
        meta=metadata,
        track=track,
        simulations=simulations,
        maps=maps,
        plot_files=plot_files,
    )


@bp.get("/results/<run_id>/pdf")
def result_pdf(run_id: str):
    try:
        directory = resolve_session_run_directory(run_id, "run_dir")
        pdf_path = generate_simulation_pdf(directory)
        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"ebike_simulation_{run_id}.pdf",
        )
    except NotFound:
        raise
    except (PdfReportDataError, PdfReportError) as exc:
        logger.exception("PDF-Bericht konnte nicht erzeugt werden fuer Run %s.", run_id)
        return render_template("error.html", message="Der PDF-Bericht konnte nicht erstellt werden."), 500
    except Exception:
        logger.exception("Unerwarteter Fehler bei der PDF-Erzeugung fuer Run %s.", run_id)
        return render_template("error.html", message="Der PDF-Bericht konnte nicht erstellt werden."), 500


@bp.route("/output/<run_id>/<path:filename>")
def output_file(run_id: str, filename: str):
    directory = resolve_session_run_directory(run_id, "run_dir")
    path = (directory / filename).resolve()
    if directory.resolve() not in path.parents and path != directory.resolve():
        raise NotFound()
    if not path.is_file():
        raise NotFound()
    return send_file(path)


@bp.route("/parameterstudie", methods=["GET", "POST"])
def parameter_study():
    bike, smooth = defaults()
    if request.method == "GET":
        return render_template("parameter_study.html", bike=bike, smooth=smooth, parameters=VALID_PARAMETERS)

    try:
        b, s, bat = form_values(request.form)
        par = request.form["parameter_name"]
        minimum = positive(request.form, "minimum")
        maximum = positive(request.form, "maximum")
        steps = int(positive(request.form, "steps"))
        out = current_app.config["WEB_OUTPUT"] / uuid.uuid4().hex
        out.mkdir(parents=True, exist_ok=True)
        df = run_parameter_study(track_for_request(), b, s, par, minimum, maximum, steps, bat, out)
        df.to_csv(out / "parameterstudie.csv", index=False)
        explanation = explain_parameter_study(df, parameter_name=par, baseline_value=b[par])
        parameter_values = pd.to_numeric(df["parameter_value"], errors="coerce").dropna()
        parameter_range_text = (
            f"{float(parameter_values.min()):.3f} bis {float(parameter_values.max()):.3f} {explanation.parameter_unit}"
            if not parameter_values.empty
            else "n. a."
        )
        (out / "parameterstudie_erklaerung.json").write_text(
            json.dumps(asdict(explanation), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        session["study_dir"] = str(out)
        highlight_value = explanation.baseline_value if explanation.exact_baseline_included else explanation.nearest_study_value
        return render_template(
            "parameter_study_results.html",
            explanation=explanation,
            rows=df.to_dict("records"),
            columns=list(df.columns),
            run_id=out.name,
            parameter=par,
            highlight_value=highlight_value,
            parameter_range_text=parameter_range_text,
        )
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("web.parameter_study"))


@bp.route("/parameterstudie/<run_id>/csv")
def study_csv(run_id: str):
    directory = resolve_session_run_directory(run_id, "study_dir", require_metadata=False)
    path = directory / "parameterstudie.csv"
    if not path.is_file():
        raise NotFound()
    return send_file(path, as_attachment=True, download_name="parameterstudie.csv")


def resolve_session_run_directory(run_id: str, session_key: str, require_metadata: bool = True) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise NotFound()
    session_value = session.get(session_key)
    if not session_value:
        raise NotFound()
    base_output = current_app.config["WEB_OUTPUT"].resolve()
    directory = Path(session_value)
    try:
        resolved = directory.resolve(strict=True)
    except FileNotFoundError as exc:
        raise NotFound() from exc
    if not resolved.is_dir() or resolved.name != run_id:
        raise NotFound()
    if base_output != resolved and base_output not in resolved.parents:
        raise NotFound()
    if require_metadata and not (resolved / "metadata.json").is_file():
        raise NotFound()
    return resolved


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise NotFound()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise NotFound()
    return data


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise NotFound()
    return pd.read_csv(path)


def _load_simulations(directory: Path) -> dict[str, pd.DataFrame]:
    simulations: dict[str, pd.DataFrame] = {}
    for name in ("LiPo", "NMC"):
        path = directory / f"simulation_{name.lower()}.csv"
        if path.is_file():
            simulations[name] = pd.read_csv(path)
    return simulations


def _map_links(directory: Path, run_id: str) -> dict[str, str]:
    links: dict[str, str] = {}
    filenames = {
        "route": "karte_strecke.html",
        "LiPo": "karte_soc_lipo.html",
        "NMC": "karte_soc_nmc.html",
    }
    for key, filename in filenames.items():
        if (directory / filename).is_file():
            links[key] = url_for("web.output_file", run_id=run_id, filename=filename)
    return links


def _available_plot_files(directory: Path, metadata: dict) -> dict[str, str]:
    plot_files = metadata.get("plot_files", {}) if isinstance(metadata.get("plot_files"), dict) else {}
    available: dict[str, str] = {}
    for key, rel_path in plot_files.items():
        path = directory / str(rel_path)
        if path.is_file():
            available[str(key)] = str(rel_path)
    return available
