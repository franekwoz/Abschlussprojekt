"""Kommandozeilen-Einstiegspunkt der E-Bike-Routensimulation."""
import logging
from pathlib import Path
import pandas as pd
import yaml
from speed_smoothing import SpeedSmoothingConfig
from webapp.services.simulation_service import run_simulation


def _wert_formatieren(wert: float, einheit: str) -> str:
    """Formatiert einen Messwert mit Einheit, oder 'k.A.' falls die Abfrage fehlschlug."""
    return f"{wert:.1f} {einheit}" if pd.notna(wert) else "k.A."


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
                            output_directory=output, generate_outputs=True,
                            mit_orten_und_wetter=True)
    print("=== Streckendaten ===")
    print(result.track.df[["time", "dt_s", "distanz_m", "geschwindigkeit_ms", "beschleunigung_ms2"]].head(10))
    result.track.kennzahlen_ausgeben()

    if result.orte is not None:
        print()
        print("=== Adressen entlang der Strecke (Reverse Geocoding) ===")
        for _, zeile in result.orte.iterrows():
            print(f"  [{zeile['index']:>4}] {zeile['adresse']}")

        print()
        print("=== Wetterdaten an den Streckenpunkten ===")
        for _, zeile in result.orte.iterrows():
            print(
                f"  [{zeile['index']:>4}] "
                f"Temperatur: {_wert_formatieren(zeile.get('wetter_temperatur_c'), '°C')}, "
                f"Wind: {_wert_formatieren(zeile.get('wetter_wind_kmh'), 'km/h')}, "
                f"Niederschlag: {_wert_formatieren(zeile.get('wetter_niederschlag_mm'), 'mm')}"
            )

    for name, summary in result.summaries.items():
        print(f"=== Simulation mit {name}-Akku ===")
        for key, value in summary.items(): print(f"{key}: {value}")


if __name__ == "__main__":
    main()
