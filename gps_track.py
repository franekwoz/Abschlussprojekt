"""
gps_track.py
------------
Kapselt die GPS-Rohdaten und die daraus abgeleitete Kinematik.

Hat KEIN direktes Gegenstück im Kurs-Grundmodell (Kapitel 09): Dort wird
der Bewegungsverlauf entweder direkt als Lastprofil (Liste von Strömen/
Leistungen) vorgegeben, oder von VehicleModel aus einer Leistung simuliert.
Im Abschlussprojekt übernimmt GPSTrack strukturell diese Rolle als
"Datenquelle" für den EBikeSimulator - aber datengetrieben aus einer realen
Aufzeichnung statt synthetisch erzeugt (siehe Kommentar in ebike.py).

Erweiterung: karte_erstellen()
-------------------------------
Zusätzlich zur reinen Kinematik-Berechnung kann GPSTrack die Strecke jetzt
auch auf einer interaktiven Karte darstellen (Leaflet-Karte via `folium`).
Das ist rein visualisierend und hat keinen Einfluss auf die Simulation -
deshalb als eigene, optionale Methode angehängt statt die bestehende Logik
zu verändern. Die Methode nimmt optional ein beliebiges DataFrame entgegen
(Standard: die eigenen Trackdaten `self.df`), damit sich damit auch das
Ergebnis-DataFrame aus EBikeSimulator.simulate() (inkl. SoC, Spannung,
Motorstrom, ...) einfärben und plotten lässt.
"""

import math
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class GPSTrack:
    """
    Repräsentiert eine GPS-Aufzeichnung (Track) als Objekt.

    Attribute:
        df (pd.DataFrame): Rohdaten + berechnete Spalten (distanz_m,
                            geschwindigkeit_ms, beschleunigung_ms2, steigung_grad)
    """

    ERDRADIUS_M = 6_371_000   # mittlerer Erdradius in Metern (Haversine-Formel)

    def __init__(self, pfad: str):
        self.df = self._datei_einlesen(pfad)
        self._kinematik_berechnen()

    def _datei_einlesen(self, pfad: str) -> pd.DataFrame:
        logger.info(f"Lese GPS-Daten ein aus: {pfad}")
        df = pd.read_csv(pfad, sep=";")
        df["time"] = pd.to_datetime(df["time"])
        return df

    def _distanz_haversine(self, lat1, lon1, lat2, lon2) -> float:
        lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
        delta_lat = lat2_rad - lat1_rad
        delta_lon = math.radians(lon2) - math.radians(lon1)
        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        return self.ERDRADIUS_M * 2 * math.asin(math.sqrt(a))

    def _kinematik_berechnen(self) -> None:
        n = len(self.df)
        distanz = [0.0] * n
        geschwindigkeit = [0.0] * n
        beschleunigung = [0.0] * n
        steigung_grad = [0.0] * n

        for i in range(1, n):
            dt = (self.df["time"].iloc[i] - self.df["time"].iloc[i - 1]).total_seconds()

            d = self._distanz_haversine(
                self.df["lat"].iloc[i - 1], self.df["lon"].iloc[i - 1],
                self.df["lat"].iloc[i], self.df["lon"].iloc[i],
            )
            distanz[i] = d
            geschwindigkeit[i] = d / dt if dt > 0 else 0.0
            beschleunigung[i] = (geschwindigkeit[i] - geschwindigkeit[i - 1]) / dt if dt > 0 else 0.0

            dh = self.df["ele"].iloc[i] - self.df["ele"].iloc[i - 1]
            steigung_grad[i] = math.degrees(math.atan2(dh, d)) if d > 0 else 0.0

        self.df["distanz_m"] = distanz
        self.df["geschwindigkeit_ms"] = geschwindigkeit
        self.df["beschleunigung_ms2"] = beschleunigung
        self.df["steigung_grad"] = steigung_grad

    def gesamtstrecke_km(self) -> float:
        return self.df["distanz_m"].sum() / 1000

    def durchschnittsgeschwindigkeit_kmh(self) -> float:
        return self.df["geschwindigkeit_ms"].mean() * 3.6

    def gesamtzeit_s(self) -> float:
        return (self.df["time"].iloc[-1] - self.df["time"].iloc[0]).total_seconds()

    def hoehenmeter_anstieg(self) -> float:
        dh = self.df["ele"].diff().fillna(0)
        return dh[dh > 0].sum()

    def hoehenmeter_abstieg(self) -> float:
        dh = self.df["ele"].diff().fillna(0)
        return -dh[dh < 0].sum()

    def kennzahlen_ausgeben(self) -> None:
        print(f"Gesamtstrecke:                 {self.gesamtstrecke_km():.2f} km")
        print(f"Gesamtzeit:                    {self.gesamtzeit_s() / 60:.1f} min")
        print(f"Durchschnittsgeschwindigkeit:  {self.durchschnittsgeschwindigkeit_kmh():.1f} km/h")
        print(f"Höhenmeter Anstieg:            {self.hoehenmeter_anstieg():.0f} m")
        print(f"Höhenmeter Abstieg:            {self.hoehenmeter_abstieg():.0f} m")

    def __str__(self) -> str:
        return f"GPSTrack({len(self.df)} Punkte, {self.gesamtstrecke_km():.2f} km)"

    # ------------------------------------------------------------------
    # Kartendarstellung (folium)
    # ------------------------------------------------------------------
    def karte_erstellen(
        self,
        df: pd.DataFrame = None,
        farbwert: str = "geschwindigkeit_ms",
        ausgabepfad: str = "track_karte.html",
        zoom_start: int = 14,
        kartenstil: str = "cartodbpositron",

    ):
        """
        Erstellt eine interaktive HTML-Karte (Leaflet über `folium`) mit der
        gefahrenen Strecke als farbcodierter Linie.

        Parameter:
            df (pd.DataFrame | None): Zu plottende Daten. Wenn None, wird
                self.df verwendet. Erwartet werden mind. die Spalten
                'lat' und 'lon' sowie die in `farbwert` angegebene Spalte
                (z.B. auch das Ergebnis-DataFrame von
                EBikeSimulator.simulate(), das zusätzlich 'soc',
                'spannung_V', 'motorstrom_A' etc. enthält).
            farbwert (str): Name der Spalte, nach der die Streckenfarbe
                eingefärbt wird (z.B. 'geschwindigkeit_ms', 'steigung_grad',
                'soc', 'spannung_V', 'motorstrom_A').
            ausgabepfad (str): Pfad der zu speichernden HTML-Datei.
            zoom_start (int): Anfangs-Zoomstufe der Karte.

        Rückgabe:
            folium.Map: das erzeugte Karten-Objekt (zusätzlich zum Speichern
            auf der Festplatte, z.B. praktisch für die Einbettung in Jupyter).
        """
        import folium
        import branca.colormap as cm

        if df is None:
            df = self.df

        if farbwert not in df.columns:
            raise ValueError(
                f"Spalte '{farbwert}' nicht im DataFrame vorhanden. "
                f"Verfügbare Spalten: {list(df.columns)}"
            )

        mitte_lat = df["lat"].mean()
        mitte_lon = df["lon"].mean()
        karte = folium.Map(location=[mitte_lat, mitte_lon], zoom_start=zoom_start, tiles="OpenStreetMap")

        werte = df[farbwert]
        farbskala = cm.LinearColormap(
            colors=["blue", "green", "yellow", "red"],
            vmin=float(werte.min()),
            vmax=float(werte.max()),
            caption=farbwert,
        )

        koordinaten = list(zip(df["lat"], df["lon"]))
        for i in range(len(koordinaten) - 1):
            segment = [koordinaten[i], koordinaten[i + 1]]
            farbe = farbskala(werte.iloc[i])
            folium.PolyLine(
                segment,
                color=farbe,
                weight=5,
                opacity=0.85,
                tooltip=f"{farbwert}: {werte.iloc[i]:.2f}",
            ).add_to(karte)

        folium.Marker(
            koordinaten[0], popup="Start", icon=folium.Icon(color="green", icon="play")
        ).add_to(karte)
        folium.Marker(
            koordinaten[-1], popup="Ziel", icon=folium.Icon(color="red", icon="stop")
        ).add_to(karte)

        farbskala.add_to(karte)
        karte.save(ausgabepfad)
        logger.info(f"Karte gespeichert unter: {ausgabepfad}")
        return karte