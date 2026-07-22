from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeedSmoothingConfig:
    enabled: bool = False
    min_interval_s: float = 0.5
    max_gap_s: float = 30.0
    median_window_s: float = 15.0
    time_constant_s: float = 3.0
    max_reasonable_speed_kmh: float = 60.0

    @property
    def max_reasonable_speed_ms(self) -> float:
        return self.max_reasonable_speed_kmh / 3.6

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SpeedSmoothingConfig":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as datei:
            daten = yaml.safe_load(datei) or {}

        if not isinstance(daten, dict):
            raise ValueError(
                f"Ungueltiges YAML-Format in {config_path}: erwartet wurde ein Dictionary."
            )

        defaults = cls()

        enabled = daten.get("enabled", defaults.enabled)
        min_interval_s = daten.get("min_interval_s", defaults.min_interval_s)
        max_gap_s = daten.get("max_gap_s", defaults.max_gap_s)
        median_window_s = daten.get("median_window_s", defaults.median_window_s)
        time_constant_s = daten.get("time_constant_s", defaults.time_constant_s)
        max_reasonable_speed_kmh = daten.get(
            "max_reasonable_speed_kmh", defaults.max_reasonable_speed_kmh
        )

        if not isinstance(enabled, bool):
            raise ValueError("Konfigurationswert 'enabled' muss bool sein (true/false).")

        min_interval_s = _float_und_validiere(
            "min_interval_s",
            min_interval_s,
            lambda v: v > 0.0,
            "muss groesser als 0 sein.",
        )
        max_gap_s = _float_und_validiere(
            "max_gap_s",
            max_gap_s,
            lambda v: v > 0.0,
            "muss groesser als 0 sein.",
        )
        median_window_s = _float_und_validiere(
            "median_window_s",
            median_window_s,
            lambda v: v > 0.0,
            "muss groesser als 0 sein.",
        )
        time_constant_s = _float_und_validiere(
            "time_constant_s",
            time_constant_s,
            lambda v: v > 0.0,
            "muss groesser als 0 sein.",
        )
        max_reasonable_speed_kmh = _float_und_validiere(
            "max_reasonable_speed_kmh",
            max_reasonable_speed_kmh,
            lambda v: v > 0.0,
            "muss groesser als 0 sein.",
        )

        if max_gap_s <= min_interval_s:
            raise ValueError(
                "Konfigurationswert 'max_gap_s' muss groesser als 'min_interval_s' sein."
            )

        return cls(
            enabled=enabled,
            min_interval_s=min_interval_s,
            max_gap_s=max_gap_s,
            median_window_s=median_window_s,
            time_constant_s=time_constant_s,
            max_reasonable_speed_kmh=max_reasonable_speed_kmh,
        )


@dataclass
class SpeedSmoothingResult:
    geglaettete_geschwindigkeit_ms: pd.Series
    segment_id: pd.Series
    gueltige_stuetzstelle: pd.Series
    kurzes_intervall: pd.Series
    grosse_zeitluecke: pd.Series
    geschwindigkeitsausreisser: pd.Series
    ungueltiges_intervall: pd.Series


def geschwindigkeit_glaetten(
    zeitpunkte: pd.Series,
    zeitintervalle_s: pd.Series,
    rohgeschwindigkeit_ms: pd.Series,
    config: SpeedSmoothingConfig,
) -> SpeedSmoothingResult:
    """Bereinigt und glaettet eine Geschwindigkeitskurve zeitbasiert pro Segment."""
    zeit = pd.to_datetime(zeitpunkte)
    dt = pd.to_numeric(zeitintervalle_s, errors="coerce").fillna(0.0)
    v_roh = pd.to_numeric(rohgeschwindigkeit_ms, errors="coerce")

    n = len(v_roh)
    if len(zeit) != n or len(dt) != n:
        raise ValueError("Zeitpunkte, Zeitintervalle und Rohgeschwindigkeit muessen gleich lang sein.")

    ungueltiges_intervall = dt <= 0.0
    kurzes_intervall = (dt > 0.0) & (dt < config.min_interval_s)
    grosse_zeitluecke = dt > config.max_gap_s
    geschwindigkeitsausreisser = v_roh > config.max_reasonable_speed_ms

    segment_id = _segment_ids_aus_zeitluecken(grosse_zeitluecke)
    gueltige_stuetzstelle = (
        (~ungueltiges_intervall)
        & (~kurzes_intervall)
        & (~geschwindigkeitsausreisser)
        & v_roh.notna()
        & v_roh.map(math.isfinite)
    )

    v_geglaettet = pd.Series(index=v_roh.index, dtype="float64")

    for seg in sorted(segment_id.unique()):
        mask = segment_id == seg
        seg_v_roh = v_roh[mask].copy()
        seg_zeit = zeit[mask]
        seg_gueltig = gueltige_stuetzstelle[mask]

        if seg_gueltig.sum() == 0:
            logger.warning(
                "Segment %d hat keine gueltige Filterstuetzstelle. Rohgeschwindigkeit wird verwendet.",
                int(seg),
            )
            v_geglaettet.loc[mask] = seg_v_roh.values
            continue

        seg_stuetz = seg_v_roh.where(seg_gueltig, other=float("nan"))
        idx = pd.DatetimeIndex(seg_zeit)
        median = _zeitbasierter_median(seg_stuetz, idx, config.median_window_s)

        interp = median.interpolate(method="time", limit_area="inside")
        interp = interp.ffill().bfill()
        if interp.isna().any():
            interp = interp.fillna(seg_v_roh)

        vorwaerts = _exp_glatt_zeitabhaengig(interp, idx, config.time_constant_s, rueckwaerts=False)
        rueckwaerts = _exp_glatt_zeitabhaengig(interp, idx, config.time_constant_s, rueckwaerts=True)
        seg_out = (vorwaerts + rueckwaerts) / 2.0
        seg_out = seg_out.fillna(seg_v_roh)

        v_geglaettet.loc[mask] = seg_out.values

    v_geglaettet = v_geglaettet.fillna(v_roh)

    return SpeedSmoothingResult(
        geglaettete_geschwindigkeit_ms=v_geglaettet,
        segment_id=segment_id.astype("int64"),
        gueltige_stuetzstelle=gueltige_stuetzstelle.astype(bool),
        kurzes_intervall=kurzes_intervall.astype(bool),
        grosse_zeitluecke=grosse_zeitluecke.astype(bool),
        geschwindigkeitsausreisser=geschwindigkeitsausreisser.astype(bool),
        ungueltiges_intervall=ungueltiges_intervall.astype(bool),
    )


def beschleunigung_aus_geschwindigkeit(
    zeitpunkte: pd.Series,
    geschwindigkeit_ms: pd.Series,
    segment_id: pd.Series,
) -> pd.Series:
    """Berechnet Beschleunigung pro Segment mit zentraler Differenz und robusten Randbedingungen."""
    v = pd.to_numeric(geschwindigkeit_ms, errors="coerce").fillna(0.0)
    zeit = pd.Series(pd.to_datetime(zeitpunkte), index=v.index)
    seg_id = pd.to_numeric(segment_id, errors="coerce").fillna(0).astype(int)

    n = len(v)
    if len(zeit) != n or len(seg_id) != n:
        raise ValueError("Zeitpunkte, Geschwindigkeit und segment_id muessen gleich lang sein.")

    a = pd.Series(0.0, index=v.index, dtype="float64")

    for seg in sorted(seg_id.unique()):
        mask = seg_id == seg
        idx = v.index[mask]
        if len(idx) == 0:
            continue

        a.loc[idx[0]] = 0.0
        if len(idx) == 1:
            continue

        t_mid = []
        for j, row_idx in enumerate(idx):
            if j == 0:
                t_mid.append(zeit.loc[row_idx])
            else:
                t_mid.append(zeit.loc[idx[j - 1]] + (zeit.loc[row_idx] - zeit.loc[idx[j - 1]]) / 2)

        for j in range(1, len(idx) - 1):
            i_prev = idx[j - 1]
            i_cur = idx[j]
            i_next = idx[j + 1]

            dt = (t_mid[j + 1] - t_mid[j - 1]).total_seconds()
            if dt > 0.0 and math.isfinite(dt):
                a.loc[i_cur] = (v.loc[i_next] - v.loc[i_prev]) / dt
            else:
                a.loc[i_cur] = 0.0

        last = idx[-1]
        prev = idx[-2]
        dt_last = (t_mid[-1] - t_mid[-2]).total_seconds()
        if dt_last > 0.0 and math.isfinite(dt_last):
            a.loc[last] = (v.loc[last] - v.loc[prev]) / dt_last
        else:
            a.loc[last] = 0.0

    return a.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)


def _float_und_validiere(
    name: str,
    value: object,
    validator,
    fehlertext: str,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Konfigurationswert '{name}' muss eine Zahl sein.")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Konfigurationswert '{name}' muss eine Zahl sein.") from exc

    if not math.isfinite(out):
        raise ValueError(f"Konfigurationswert '{name}' muss endlich sein.")
    if not validator(out):
        raise ValueError(f"Konfigurationswert '{name}' {fehlertext}")
    return out


def _segment_ids_aus_zeitluecken(grosse_zeitluecke: pd.Series) -> pd.Series:
    segment = []
    current = 0
    for i, ist_luecke in enumerate(grosse_zeitluecke):
        if i > 0 and bool(ist_luecke):
            current += 1
        segment.append(current)
    return pd.Series(segment, index=grosse_zeitluecke.index)


def _zeitbasierter_median(werte: pd.Series, zeitindex: pd.DatetimeIndex, fenster_s: float) -> pd.Series:
    serie = pd.Series(werte.values, index=zeitindex, dtype="float64")

    fenster_ms = max(1, int(round(fenster_s * 1000.0)))
    medianwerte = serie.rolling(
        window=f"{fenster_ms}ms",
        center=True,
        min_periods=1,
    ).median()
    return medianwerte


def _exp_glatt_zeitabhaengig(
    serie: pd.Series,
    zeitindex: pd.DatetimeIndex,
    time_constant_s: float,
    rueckwaerts: bool,
) -> pd.Series:
    if len(serie) == 0:
        return serie.copy()

    if rueckwaerts:
        s = serie.iloc[::-1]
        t = zeitindex[::-1]
    else:
        s = serie
        t = zeitindex

    out = [float(s.iloc[0])]
    for i in range(1, len(s)):
        dt = abs((t[i - 1] - t[i]).total_seconds())
        if not math.isfinite(dt) or dt <= 0.0:
            alpha = 1.0
        else:
            alpha = 1.0 - math.exp(-dt / time_constant_s)

        prev = out[-1]
        cur = float(s.iloc[i])
        out.append(prev + alpha * (cur - prev))

    result = pd.Series(out, index=s.index, dtype="float64")
    if rueckwaerts:
        return result.iloc[::-1]
    return result
