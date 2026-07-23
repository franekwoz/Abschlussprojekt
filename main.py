"""Kommandozeilen-Einstiegspunkt der E-Bike-Routensimulation."""
import logging
from pathlib import Path
import yaml
from speed_smoothing import SpeedSmoothingConfig
from webapp.services.simulation_service import run_simulation


def main() -> None:
    """Führt dieselbe Service-Schicht wie die Flask-Anwendung aus."""
    root = Path(__file__).resolve().parent
    output = root / "output"
    output.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.StreamHandler(), logging.FileHandler(output / "ebike_simulation.log", mode="w", encoding="utf-8")])
    bike = yaml.safe_load((root / "data" / "bike_config.yaml").read_text(encoding="utf-8"))
    smoothing = SpeedSmoothingConfig.from_yaml(root / "data" / "speed_smoothing_config.yaml")
    result = run_simulation(root / "data" / "final_project_input_data.csv", bike, smoothing,
                            output_directory=output, generate_outputs=True)
    print("=== Streckendaten ===")
    print(result.track.df[["time", "dt_s", "distanz_m", "geschwindigkeit_ms", "beschleunigung_ms2"]].head(10))
    result.track.kennzahlen_ausgeben()
    for name, summary in result.summaries.items():
        print(f"=== Simulation mit {name}-Akku ===")
        for key, value in summary.items(): print(f"{key}: {value}")


if __name__ == "__main__":
    main()
