"""
wetterdaten.py
--------------
Fragt echte Wetterdaten bei der kostenlosen Open-Meteo API ab
(https://open-meteo.com/, kein API-Key nötig) - und zwar genau für die
Orte, die bereits per Reverse Geocoding bestimmt wurden (siehe
GPSTrack.orte_ermitteln() in gps_track.py: Start, Ziel und ein paar
gleichmäßig verteilte Zwischenpunkte).

Das hat zwei Vorteile gegenüber einer Abfrage für die komplette Strecke:
- Es sind ohnehin schon Koordinaten UND Adressen für genau diese Punkte
  vorhanden - Wetter und Adresse lassen sich direkt nebeneinander ausgeben.
- Es bleibt bei einer Handvoll Anfragen (z.B. 8 statt >2000 Punkten),
  ganz im Sinne der kostenlosen, fairen API-Nutzung.

Vorgehen:
1. Für jeden Ort aus `orte` (DataFrame mit Spalten index/lat/lon/adresse)
   wird über den zugehörigen `index` der Aufzeichnungszeitpunkt aus dem
   Track-DataFrame nachgeschlagen.
2. Alle Orte werden in EINER einzigen HTTP-Anfrage abgefragt (Open-Meteo
   erlaubt mehrere Koordinaten pro Aufruf als kommagetrennte Liste).
3. Liegt der Zeitraum der Aufzeichnung weiter als ein paar Tage in der
   Vergangenheit, wird automatisch die Archiv-API verwendet, sonst die
   normale Forecast-API (deckt auch nahe Vergangenheit/Zukunft ab).
4. Für jeden Ort wird aus dem stündlichen Verlauf der Wert genommen, der
   der tatsächlichen Aufzeichnungszeit am nächsten liegt.

Öffentliche Funktionen:
- wetterdaten_fuer_orte(orte, track_df): fragt die Wetterdaten ab und
  gibt ein DataFrame zurück (orte + neue Wetterspalten)
- wetterdaten_ausgeben(orte, track_df): fragt die Wetterdaten ab UND
  gibt sie direkt formatiert auf der Konsole aus - das ist die Funktion,
  die aus main.py aufgerufen wird.
"""

import logging              # für Logging statt einfacher print()-Ausgaben (Warnungen/Infos)

import numpy as np           # für NaN-Werte und schnelle Array-Operationen (np.abs, np.argmin)
import pandas as pd          # für die Tabellen-Verarbeitung (DataFrame) und Zeitstempel
import requests               # für die HTTP-Anfragen an die Open-Meteo API (siehe unten)

# Ein eigener Logger pro Modul ist Standard, damit man in den Log-Meldungen
# später sieht, aus welcher Datei/Klasse die Meldung kommt.
logger = logging.getLogger(__name__)

# Zwei verschiedene Open-Meteo-Endpunkte, je nachdem wie weit der gesuchte
# Zeitpunkt in der Vergangenheit liegt (siehe _ist_vergangenheit() weiter unten):
ARCHIV_API_URL = "https://archive-api.open-meteo.com/v1/archive"     # länger zurückliegende Daten
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"          # aktuelle/nahe Zukunft & Vergangenheit

# Open-Meteo-Variablenname (so heißt er in der API-Antwort) -> Spaltenname,
# unter dem der Wert im zurückgegebenen DataFrame landet. Eine zentrale
# Zuordnung an einer Stelle, damit Funktionsnamen unten nicht wild wechseln.
STANDARD_VARIABLEN = {
    "temperature_2m": "wetter_temperatur_c",
    "wind_speed_10m": "wetter_wind_kmh",
    "precipitation": "wetter_niederschlag_mm",
    "relative_humidity_2m": "wetter_luftfeuchte_pct",
}


def _ist_vergangenheit(zeitpunkt: pd.Timestamp, schwelle_tage: int = 5) -> bool:
    """
    Die Forecast-API von Open-Meteo deckt nur wenige Tage Vergangenheit ab.
    Liegt der Zeitpunkt weiter zurück, wird die Archiv-API benötigt.
    """
    jetzt = pd.Timestamp.now(tz="UTC")
    # Zeitpunkt auf UTC bringen, egal ob er schon eine Zeitzone hat oder nicht
    # (sonst wirft die Subtraktion unten einen Fehler oder rechnet falsch)
    zeitpunkt = zeitpunkt.tz_convert("UTC") if zeitpunkt.tzinfo else zeitpunkt.tz_localize("UTC")
    return (jetzt - zeitpunkt).days > schwelle_tage


def _wetter_abfragen(
    latitudes: list[float],
    longitudes: list[float],
    datum_start: str,
    datum_ende: str,
    vergangenheit: bool,
    variablen: list[str],
) -> list[dict]:
    """
    Fragt für alle übergebenen Koordinaten in EINER Anfrage den stündlichen
    Wetterverlauf zwischen datum_start und datum_ende ab.

    Rückgabe: Liste von Antwort-Objekten (ein Eintrag pro Koordinate, in
    derselben Reihenfolge wie latitudes/longitudes).
    """
    url = ARCHIV_API_URL if vergangenheit else FORECAST_API_URL

    # Open-Meteo akzeptiert mehrere Koordinaten in EINER Anfrage, wenn man
    # sie kommagetrennt übergibt (latitude="47.5,47.6", longitude="12.1,12.2").
    # So reicht ein einziger HTTP-Request für alle Orte statt einer pro Ort.
    params = {
        "latitude": ",".join(f"{lat:.6f}" for lat in latitudes),
        "longitude": ",".join(f"{lon:.6f}" for lon in longitudes),
        "start_date": datum_start,
        "end_date": datum_ende,
        "hourly": ",".join(variablen),   # z.B. "temperature_2m,wind_speed_10m,precipitation"
        "timezone": "UTC",
    }
    logger.info(
        "Frage Wetterdaten bei Open-Meteo ab (%s, %d Orte, %s bis %s)...",
        "Archiv-API" if vergangenheit else "Forecast-API",
        len(latitudes),
        datum_start,
        datum_ende,
    )
    # requests.get() schickt die eigentliche HTTP-Anfrage. timeout=20 verhindert,
    # dass das Programm ewig hängen bleibt, falls der Server nicht antwortet.
    antwort = requests.get(url, params=params, timeout=20)
    antwort.raise_for_status()   # wirft eine Exception bei HTTP-Fehlern (z.B. 404, 500)
    daten = antwort.json()       # JSON-Antwort -> Python dict/list zum Weiterverarbeiten

    # Bei genau einer Koordinate liefert Open-Meteo ein einzelnes Objekt
    # statt einer Liste - hier vereinheitlichen wir das.
    if isinstance(daten, dict):
        daten = [daten]
    return daten


def _naechster_stundenwert(hourly_zeiten: list[str], hourly_werte: list, zeitpunkt: pd.Timestamp):
    """Gibt den Wert der Stunde zurück, die zeitlich am nächsten am gesuchten Zeitpunkt liegt."""
    if not hourly_zeiten or not hourly_werte:
        # Open-Meteo hat für diesen Ort keine Daten geliefert (z.B. Ort außerhalb
        # des abgedeckten Gebiets) - dann gibt es auch keinen Stundenwert
        return float("nan")

    # Zeitzone entfernen (Open-Meteo liefert "naive" Zeiten ohne tz-Info zurück,
    # daher muss der gesuchte Zeitpunkt zum Vergleich ebenfalls "naiv" gemacht werden)
    zeitpunkt_naiv = pd.Timestamp(zeitpunkt)
    if zeitpunkt_naiv.tzinfo is not None:
        zeitpunkt_naiv = zeitpunkt_naiv.tz_convert("UTC").tz_localize(None)

    # Für jede der 24 Stunden des Tages den zeitlichen Abstand zum gesuchten
    # Zeitpunkt berechnen und die Stunde mit dem kleinsten Abstand nehmen
    zeiten = pd.to_datetime(hourly_zeiten)
    differenzen = np.abs((zeiten - zeitpunkt_naiv).total_seconds())
    idx = int(np.argmin(differenzen))

    wert = hourly_werte[idx]
    return float(wert) if wert is not None else float("nan")


def wetterdaten_fuer_orte(
    orte: pd.DataFrame,
    track_df: pd.DataFrame,
    variablen: tuple[str, ...] = ("temperature_2m", "wind_speed_10m", "precipitation"),
) -> pd.DataFrame:
    """
    Ergänzt das von GPSTrack.orte_ermitteln() gelieferte DataFrame
    (Spalten: index, lat, lon, adresse) um Wetterspalten für genau diese
    Orte, zum Zeitpunkt der jeweiligen Aufzeichnung.

    Parameter:
        orte (pd.DataFrame): Rückgabe von GPSTrack.orte_ermitteln();
            erwartet werden die Spalten 'index', 'lat', 'lon'
        track_df (pd.DataFrame): das zugehörige Track-DataFrame (self.df),
            wird genutzt, um über 'index' den Aufzeichnungszeitpunkt
            ('time') jedes Ortes nachzuschlagen
        variablen (tuple[str]): Open-Meteo-Variablennamen, siehe
            STANDARD_VARIABLEN für die Zuordnung zu Spaltennamen

    Rückgabe:
        pd.DataFrame: Kopie von `orte`, ergänzt um neue Spalten (z.B.
        'wetter_temperatur_c', 'wetter_wind_kmh', 'wetter_niederschlag_mm').
        Schlägt die Abfrage fehl (z.B. kein Internetzugriff), werden die
        neuen Spalten mit NaN gefüllt und eine Warnung geloggt - das
        Programm bricht nicht ab.
    """
    # Kopie statt Original verändern (Standard-Praxis bei pandas-Funktionen:
    # die aufrufende Stelle soll sich auf ihr `orte`-DataFrame verlassen können)
    ergebnis = orte.copy()
    neue_spalten = [STANDARD_VARIABLEN.get(v, f"wetter_{v}") for v in variablen]

    # Spalten schon mal mit NaN vorbelegen, damit die Rückgabe in JEDEM
    # Fall (auch bei Fehlern weiter unten) dieselbe Struktur hat
    for spalte in neue_spalten:
        ergebnis[spalte] = np.nan

    if len(ergebnis) == 0:
        logger.warning("Keine Orte übergeben - keine Wetterdaten abgefragt.")
        return ergebnis

    # Ohne diese drei Spalten kann weder nach Koordinaten noch nach
    # Zeitpunkt gefragt werden - lieber früh und kontrolliert abbrechen
    for pflichtspalte in ("index", "lat", "lon"):
        if pflichtspalte not in ergebnis.columns:
            logger.warning(
                "Spalte '%s' fehlt im Orte-DataFrame - Wetterabfrage übersprungen.",
                pflichtspalte,
            )
            return ergebnis

    # Jeder Ort kennt über 'index' seine Position im ursprünglichen Track
    # (self.df) - darüber wird der genaue Aufzeichnungszeitpunkt (Spalte
    # 'time') nachgeschlagen, zu dem an diesem Ort das Wetter galt.
    zeitpunkte = pd.to_datetime(track_df["time"]).iloc[ergebnis["index"].tolist()].tolist()

    latitudes = ergebnis["lat"].tolist()
    longitudes = ergebnis["lon"].tolist()
    vergangenheit = _ist_vergangenheit(max(zeitpunkte))
    # Ein Datumsbereich für ALLE Orte gemeinsam, da Open-Meteo bei mehreren
    # Koordinaten in einer Anfrage nur einen gemeinsamen start_date/end_date
    # akzeptiert - min/max deckt auch mehrtägige Touren korrekt ab
    datum_start = min(zeitpunkte).strftime("%Y-%m-%d")
    datum_ende = max(zeitpunkte).strftime("%Y-%m-%d")

    try:
        antworten = _wetter_abfragen(
            latitudes, longitudes, datum_start, datum_ende, vergangenheit, list(variablen)
        )
    except Exception as fehler:
        # Kein Internetzugriff, API down, Timeout, ... - das Programm soll
        # trotzdem weiterlaufen, nur eben ohne Wetterdaten (Spalten bleiben NaN)
        logger.warning(
            "Wetterdaten konnten nicht abgefragt werden (%s) - "
            "Wetter-Spalten bleiben leer (NaN).",
            fehler,
        )
        return ergebnis

    if len(antworten) != len(ergebnis):
        # Sicherheitsnetz: sollte Open-Meteo aus irgendeinem Grund nicht
        # genau eine Antwort pro angefragtem Ort liefern, würde das
        # untenstehende zip() sonst Werte den falschen Orten zuordnen
        logger.warning(
            "Open-Meteo hat eine unerwartete Anzahl Ergebnisse geliefert "
            "(%d statt %d) - Wetter-Spalten bleiben leer (NaN).",
            len(antworten),
            len(ergebnis),
        )
        return ergebnis

    # Für jede gewünschte Variable (Temperatur, Wind, ...) und jeden Ort den
    # passenden Stundenwert herausziehen und als neue Spalte eintragen
    for variable, spalte in zip(variablen, neue_spalten):
        werte = []
        for antwort, zeitpunkt in zip(antworten, zeitpunkte):
            hourly = antwort.get("hourly", {})
            werte.append(
                _naechster_stundenwert(hourly.get("time", []), hourly.get(variable), zeitpunkt)
            )
        ergebnis[spalte] = werte

    logger.info(
        "Wetterdaten für %d Orte entlang der Strecke abgefragt (%s).",
        len(ergebnis),
        ", ".join(neue_spalten),
    )
    return ergebnis


def _wert_formatieren(wert: float, einheit: str) -> str:
    """Formatiert einen Messwert mit Einheit, oder 'k.A.' falls die Abfrage für diesen Punkt fehlschlug."""
    return f"{wert:.1f} {einheit}" if pd.notna(wert) else "k.A."


def wetterdaten_ausgeben(
    orte: pd.DataFrame,
    track_df: pd.DataFrame,
    variablen: tuple[str, ...] = ("temperature_2m", "wind_speed_10m", "precipitation"),
) -> pd.DataFrame:
    """
    Fragt die Wetterdaten für die per Reverse Geocoding bestimmten Orte ab
    (siehe wetterdaten_fuer_orte()) und gibt sie direkt formatiert auf der
    Konsole aus - eine Zeile pro Ort, referenziert über denselben `index`
    wie bei der Adressausgabe.

    Diese Funktion ist der einzige Aufruf, den main.py braucht:

        from wetterdaten import wetterdaten_ausgeben
        orte = track.orte_ermitteln()          # bereits vorhandene Orte, keine extra Punkte
        orte = wetterdaten_ausgeben(orte, track.df)

    Parameter: siehe wetterdaten_fuer_orte()

    Rückgabe:
        pd.DataFrame: wie wetterdaten_fuer_orte() - orte inkl. neuer
        Wetterspalten, falls die Werte für eine spätere Weiterverwendung
        (z.B. im LaTeX-Bericht oder auf der Karte) gebraucht werden.
    """
    # Erst abfragen, danach ausgeben - Trennung von Datenbeschaffung und
    # Darstellung, damit orte_mit_wetter bei Bedarf auch anderswo weiterverwendet
    # werden kann (z.B. im LaTeX-Bericht), ohne die Konsolen-Ausgabe zu wiederholen.
    orte_mit_wetter = wetterdaten_fuer_orte(orte, track_df, variablen=variablen)

    print("=== Wetterdaten an den Streckenpunkten ===")
    if len(orte_mit_wetter) == 0:
        print("  (keine Orte vorhanden)")
    else:
        # Eine Zeile pro Ort, referenziert über denselben 'index' wie bei
        # der Adressausgabe in main.py, damit beide Blöcke zueinander passen
        for _, zeile in orte_mit_wetter.iterrows():
            print(
                f"  [{zeile['index']:>4}] "
                f"Temperatur: {_wert_formatieren(zeile.get('wetter_temperatur_c'), '°C')}, "
                f"Wind: {_wert_formatieren(zeile.get('wetter_wind_kmh'), 'km/h')}, "
                f"Niederschlag: {_wert_formatieren(zeile.get('wetter_niederschlag_mm'), 'mm')}"
            )
    print()

    return orte_mit_wetter
