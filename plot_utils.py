"""
plot_utils.py
-------------
Erzeugt statische Matplotlib-Plots für Fahr- und Simulationsdaten.
"""

from __future__ import annotations

from pathlib import Path

# Der Webserver hat gewöhnlich kein grafisches Desktop-Backend.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _zeitachse_minuten(df: pd.DataFrame) -> pd.Series:
    startzeit = df["time"].iloc[0]
    return (df["time"] - startzeit).dt.total_seconds() / 60.0


def _strecke_km(df: pd.DataFrame) -> pd.Series:
    return df["distanz_m"].cumsum() / 1000.0


def _save_figure(fig: plt.Figure, pfad: Path) -> None:
    fig.tight_layout()
    fig.savefig(pfad, dpi=200)
    plt.close(fig)


def plots_erstellen(track_df: pd.DataFrame, simulationen: dict[str, pd.DataFrame], output_dir: str = "output/plot") -> None:
    """
    Erstellt Standard-Plots:
    - Höhenprofil über Strecke
    - Zeitsignale pro Akku (u.a. Geschwindigkeit, Leistung, SoC, Strom, Spannung)
    - SoC-Vergleich aller Akkutypen über Zeit
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Höhenprofil der Fahrt
    fig_hp, ax_hp = plt.subplots(figsize=(12, 4))
    ax_hp.plot(_strecke_km(track_df), track_df["ele"], color="tab:brown", linewidth=1.5)
    ax_hp.set_title("Hoehenprofil der Fahrt")
    ax_hp.set_xlabel("Strecke [km]")
    ax_hp.set_ylabel("Hoehe [m]")
    ax_hp.grid(alpha=0.3)
    _save_figure(fig_hp, out / "hoehenprofil_fahrt.png")

    # Zeitplots je Simulation
    for name, df in simulationen.items():
        zeit_min = _zeitachse_minuten(df)
        name_datei = name.lower()

        fig, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True)

        smoothing_aktiv = bool(df.get("speed_smoothing_enabled", pd.Series([False])).iloc[0])
        hat_roh = "geschwindigkeit_roh_ms" in df.columns
        if smoothing_aktiv and hat_roh:
            axes[0].plot(
                zeit_min,
                df["geschwindigkeit_roh_ms"] * 3.6,
                color="tab:gray",
                linewidth=0.8,
                alpha=0.35,
                label="Rohgeschwindigkeit",
            )
            axes[0].plot(
                zeit_min,
                df["geschwindigkeit_ms"] * 3.6,
                color="tab:blue",
                linewidth=1.5,
                label="Verwendete Geschwindigkeit",
            )
            axes[0].legend()
        else:
            axes[0].plot(
                zeit_min,
                df["geschwindigkeit_ms"] * 3.6,
                color="tab:blue",
                linewidth=1.5,
                label="Verwendete Geschwindigkeit",
            )
            axes[0].legend()
        axes[0].set_ylabel("v [km/h]")
        axes[0].set_title(f"Fahr- und Simulationsverlauf ueber Zeit ({name})")
        axes[0].grid(alpha=0.3)

        axes[1].plot(zeit_min, df["leistung_W"], color="tab:orange")
        axes[1].set_ylabel("P [W]")
        axes[1].grid(alpha=0.3)

        axes[2].plot(zeit_min, df["soc"] * 100.0, color="tab:green")
        axes[2].set_ylabel("SoC [%]")
        axes[2].grid(alpha=0.3)

        ax_strom = axes[3]
        ax_spannung = ax_strom.twinx()
        ax_strom.plot(zeit_min, df["motorstrom_A"], color="tab:red", label="Motorstrom")
        ax_spannung.plot(zeit_min, df["spannung_V"], color="tab:purple", label="Spannung")
        ax_strom.set_ylabel("I [A]", color="tab:red")
        ax_spannung.set_ylabel("U [V]", color="tab:purple")
        ax_strom.set_xlabel("Zeit [min]")
        ax_strom.grid(alpha=0.3)

        _save_figure(fig, out / f"zeitverlauf_{name_datei}.png")

    # SoC-Vergleich
    fig_soc, ax_soc = plt.subplots(figsize=(12, 4))
    for name, df in simulationen.items():
        ax_soc.plot(_zeitachse_minuten(df), df["soc"] * 100.0, label=name, linewidth=2)
    ax_soc.set_title("Ladezustand ueber Zeit")
    ax_soc.set_xlabel("Zeit [min]")
    ax_soc.set_ylabel("SoC [%]")
    ax_soc.grid(alpha=0.3)
    ax_soc.legend()
    _save_figure(fig_soc, out / "ladezustand_vergleich.png")

    # Optionales Diagnosebild: Roh- vs. geglaettete Geschwindigkeit des Tracks.
    if (
        "geschwindigkeit_roh_ms" in track_df.columns
        and "geschwindigkeit_geglaettet_ms" in track_df.columns
    ):
        zeit_min_track = _zeitachse_minuten(track_df)
        fig_diag, ax_diag = plt.subplots(figsize=(12, 4))
        ax_diag.plot(
            zeit_min_track,
            track_df["geschwindigkeit_roh_ms"] * 3.6,
            linewidth=0.8,
            alpha=0.35,
            color="tab:gray",
            label="Rohgeschwindigkeit",
        )
        ax_diag.plot(
            zeit_min_track,
            track_df["geschwindigkeit_geglaettet_ms"] * 3.6,
            linewidth=1.5,
            color="tab:blue",
            label="Geglaettete Geschwindigkeit",
        )
        ax_diag.set_title("Vergleich Roh- und geglaettete Geschwindigkeit")
        ax_diag.set_xlabel("Zeit [min]")
        ax_diag.set_ylabel("v [km/h]")
        ax_diag.grid(alpha=0.3)
        ax_diag.legend()
        _save_figure(fig_diag, out / "geschwindigkeit_roh_geglaettet.png")
