from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import math, uuid, json
import pandas as pd
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename
from speed_smoothing import SpeedSmoothingConfig
from .services.simulation_service import run_simulation
from .services.parameter_study_service import run_parameter_study, VALID_PARAMETERS

bp = Blueprint("web", __name__)
BIKE_KEYS = ("masse_fahrer_kg", "masse_rad_kg", "cw_a_m2", "raddurchmesser_inch", "rollwiderstandkoeffizient")

def defaults():
    import yaml
    root=current_app.config["PROJECT_ROOT"]
    return yaml.safe_load((root/"data"/"bike_config.yaml").read_text(encoding="utf-8")), SpeedSmoothingConfig.from_yaml(root/"data"/"speed_smoothing_config.yaml")
def positive(form, key, allow_zero=False):
    try: value=float(form[key])
    except (KeyError, ValueError): raise ValueError(f"{key}: Zahl erforderlich.")
    if not math.isfinite(value) or value < 0 or (not allow_zero and value <= 0): raise ValueError(f"{key}: ungueltiger Wert.")
    return value
def form_values(form):
    bike={k:positive(form,k) for k in BIKE_KEYS}
    smoothing=replace(defaults()[1], enabled=("smoothing_enabled" in form),
      min_interval_s=positive(form,"min_interval_s"), max_gap_s=positive(form,"max_gap_s"),
      median_window_s=positive(form,"median_window_s"), time_constant_s=positive(form,"time_constant_s"),
      max_reasonable_speed_kmh=positive(form,"max_reasonable_speed_kmh"))
    if smoothing.max_gap_s <= smoothing.min_interval_s: raise ValueError("max_gap_s muss groesser als min_interval_s sein.")
    battery={"lipo":"lipo" in form,"nmc":"nmc" in form,"capacity_ah":positive(form,"capacity_ah"), "initial_soc":positive(form,"initial_soc",True),"n_parallel":int(positive(form,"n_parallel"))}
    if battery["initial_soc"] > 1: raise ValueError("Initialer SoC muss zwischen 0 und 1 liegen.")
    if not battery["lipo"] and not battery["nmc"]: raise ValueError("Bitte mindestens einen Akku auswaehlen.")
    return bike,smoothing,battery
def track_for_request():
    root=current_app.config["PROJECT_ROOT"]
    upload=request.files.get("track")
    if not upload or not upload.filename: return root/"data"/"final_project_input_data.csv"
    name=secure_filename(upload.filename)
    if not name.lower().endswith(".csv"): raise ValueError("Nur CSV-Dateien sind erlaubt.")
    directory=current_app.config["WEB_OUTPUT"]/"uploads"/uuid.uuid4().hex; directory.mkdir(parents=True)
    path=directory/name; upload.save(path)
    df=pd.read_csv(path,sep=";")
    missing={"time","lat","lon","ele"}-set(df.columns)
    if missing: raise ValueError("Fehlende CSV-Spalten: "+", ".join(sorted(missing)))
    if df.empty: raise ValueError("Die CSV-Datei ist leer.")
    pd.to_datetime(df.time, errors="raise")
    for col in ("lat","lon","ele"):
      if not pd.to_numeric(df[col],errors="coerce").map(math.isfinite).all(): raise ValueError(f"Spalte {col} enthaelt ungueltige Werte.")
    return path

@bp.route("/")
def index():
    bike,smooth=defaults(); return render_template("index.html", bike=bike, smooth=smooth)

@bp.route("/favicon.ico")
def favicon():
    return "", 204

@bp.route("/simulate",methods=["POST"])
def simulate():
    try:
        bike, smooth, battery = form_values(request.form)
        mit_orten_und_wetter = "mit_orten_und_wetter" in request.form
        result = run_simulation(
            track_for_request(),
            bike,
            smooth,
            battery,
            current_app.config["WEB_OUTPUT"] / uuid.uuid4().hex,
            mit_orten_und_wetter=mit_orten_und_wetter,
            anzahl_wegpunkte=6,
        )
        session["run_dir"] = str(result.output_dir)
        return redirect(url_for("web.results", run_id=result.run_id))
    except Exception as exc: flash(str(exc),"danger"); return redirect(url_for("web.index"))
@bp.route("/results/<run_id>")
def results(run_id):
    directory=Path(session.get("run_dir",""));
    if not directory.is_dir() or directory.name != run_id: return render_template("error.html",message="Unbekanntes Ergebnis."),404
    track=pd.read_csv(directory/"track.csv"); meta=json.loads((directory/"metadata.json").read_text())
    sims={n:pd.read_csv(directory/f"simulation_{n.lower()}.csv") for n in meta["summaries"]}
    return render_template("simulation_results.html",track=track,meta=meta,simulations=sims,maps={n:f"/output/{run_id}/karte_soc_{n.lower()}.html" for n in sims}|{"route":f"/output/{run_id}/karte_strecke.html"})

@bp.route("/output/<run_id>/<path:filename>")
def output_file(run_id,filename):
    directory=Path(session.get("run_dir", "")); path=(directory/filename).resolve()
    if directory.name != run_id or not path.is_file() or directory.resolve() not in path.parents: return "Nicht gefunden",404
    return send_file(path)

@bp.route("/parameterstudie",methods=["GET","POST"])
def parameter_study():
    bike,smooth=defaults()
    if request.method=="GET": return render_template("parameter_study.html",bike=bike,smooth=smooth,parameters=VALID_PARAMETERS)
    try:
      b,s,bat=form_values(request.form); par=request.form["parameter_name"]; minimum=positive(request.form,"minimum"); maximum=positive(request.form,"maximum"); steps=int(positive(request.form,"steps"))
      out=current_app.config["WEB_OUTPUT"]/uuid.uuid4().hex; df=run_parameter_study(track_for_request(),b,s,par,minimum,maximum,steps,bat,out); df.to_csv(out/"parameterstudie.csv",index=False); session["study_dir"]=str(out)
      return render_template("parameter_study_results.html",rows=df.to_dict("records"),columns=list(df.columns),run_id=out.name,parameter=par)
    except Exception as exc: flash(str(exc),"danger"); return redirect(url_for("web.parameter_study"))
@bp.route("/parameterstudie/<run_id>/csv")
def study_csv(run_id):
    directory=Path(session.get("study_dir","")); path=directory/"parameterstudie.csv"
    if directory.name != run_id or not path.is_file() or current_app.config["WEB_OUTPUT"] not in directory.parents: return "Nicht gefunden",404
    return send_file(path,as_attachment=True,download_name="parameterstudie.csv")
