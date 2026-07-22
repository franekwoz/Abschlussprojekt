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
from pathlib import Path

from speed_smoothing import (
    SpeedSmoothingConfig,
    beschleunigung_aus_geschwindigkeit,
    geschwindigkeit_glaetten,
)

logger = logging.getLogger(__name__)


class GPSTrack:
    """
    Repräsentiert eine GPS-Aufzeichnung (Track) als Objekt.

    Attribute:
        df (pd.DataFrame): Rohdaten + berechnete Spalten (distanz_m,
                            geschwindigkeit_ms, beschleunigung_ms2, steigung_grad)
    """

    ERDRADIUS_M = 6_371_000   # mittlerer Erdradius in Metern (Haversine-Formel)

    def __init__(
        self,
        pfad: str | Path,
        smoothing_config: SpeedSmoothingConfig | None = None,
    ):
        self.smoothing_config = (
            smoothing_config if smoothing_config is not None else SpeedSmoothingConfig()
        )
        self.df = self._datei_einlesen(pfad)
        self._kinematik_berechnen()

    def _datei_einlesen(self, pfad: str | Path) -> pd.DataFrame:
        logger.info(f"Lese GPS-Daten ein aus: {pfad}")
        df = pd.read_csv(pfad, sep=";")
        df["time"] = pd.to_datetime(df["time"], format="ISO8601", utc=True)
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

    KOPMASSRICHTUNGEN = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]

    def _kurs_grad(self, lat1, lon1, lat2, lon2) -> float:
        """Anfangskurs (0-360 Grad, 0 = Norden) von Punkt 1 zu Punkt 2."""
        lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
        delta_lon = math.radians(lon2 - lon1)
        x = math.sin(delta_lon) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)
        kurs = math.degrees(math.atan2(x, y))
        return (kurs + 360.0) % 360.0
    
    def _kompassrichtung(self, kurs_grad: float) -> str:
        """Ordnet einer Kursrichtung (Grad) eine der 8 Kompassrichtungen zu."""
        index = round(kurs_grad / 45) % 8
        return self.KOPMASSRICHTUNGEN[index]

    def _kinematik_berechnen(self) -> None:
        n = len(self.df)
        if n == 0:
            self.df["dt_s"] = []
            self.df["distanz_m"] = []
            self.df["segment_id"] = []
            self.df["geschwindigkeit_roh_ms"] = []
            self.df["geschwindigkeit_geglaettet_ms"] = []
            self.df["beschleunigung_roh_ms2"] = []
            self.df["beschleunigung_geglaettet_ms2"] = []
            self.df["geschwindigkeit_ms"] = []
            self.df["beschleunigung_ms2"] = []
            self.df["filter_gueltige_stuetzstelle"] = []
            self.df["filter_kurzes_intervall"] = []
            self.df["filter_grosse_zeitluecke"] = []
            self.df["filter_geschwindigkeitsausreisser"] = []
            self.df["filter_ungueltiges_intervall"] = []
            self.df["speed_smoothing_enabled"] = []
            return

        dt_s = [0.0] * n
        distanz = [0.0] * n
        geschwindigkeit_roh = [0.0] * n
        steigung_grad = [0.0] * n
        kurs_grad = [0.0] * n
        kompassrichtung = ["N"] * n

        for i in range(1, n):
            dt = (self.df["time"].iloc[i] - self.df["time"].iloc[i - 1]).total_seconds()
            dt_s[i] = dt

            d = self._distanz_haversine(
                self.df["lat"].iloc[i - 1], self.df["lon"].iloc[i - 1],
                self.df["lat"].iloc[i], self.df["lon"].iloc[i],
            )
            distanz[i] = d
            geschwindigkeit_roh[i] = d / dt if dt > 0 else 0.0

            dh = self.df["ele"].iloc[i] - self.df["ele"].iloc[i - 1]
            steigung_grad[i] = math.degrees(math.atan2(dh, d)) if d > 0 else 0.0
    
            kurs_grad[i] = self._kurs_grad(
                self.df["lat"].iloc[i - 1], self.df["lon"].iloc[i - 1],
                self.df["lat"].iloc[i], self.df["lon"].iloc[i]
            )
            kompassrichtung[i] = self._kompassrichtung(kurs_grad[i])

        self.df["dt_s"] = dt_s
        self.df["distanz_m"] = distanz
        self.df["steigung_grad"] = steigung_grad
        self.df["kurs_grad"] = kurs_grad
        self.df["kompassrichtung"] = kompassrichtung

        self.df["geschwindigkeit_roh_ms"] = geschwindigkeit_roh

        smoothing_result = geschwindigkeit_glaetten(
            zeitpunkte=self.df["time"],
            zeitintervalle_s=self.df["dt_s"],
            rohgeschwindigkeit_ms=self.df["geschwindigkeit_roh_ms"],
            config=self.smoothing_config,
        )

        self.df["segment_id"] = smoothing_result.segment_id
        self.df["geschwindigkeit_geglaettet_ms"] = smoothing_result.geglaettete_geschwindigkeit_ms
        self.df["filter_gueltige_stuetzstelle"] = smoothing_result.gueltige_stuetzstelle
        self.df["filter_kurzes_intervall"] = smoothing_result.kurzes_intervall
        self.df["filter_grosse_zeitluecke"] = smoothing_result.grosse_zeitluecke
        self.df["filter_geschwindigkeitsausreisser"] = smoothing_result.geschwindigkeitsausreisser
        self.df["filter_ungueltiges_intervall"] = smoothing_result.ungueltiges_intervall

        self.df["beschleunigung_roh_ms2"] = beschleunigung_aus_geschwindigkeit(
            zeitpunkte=self.df["time"],
            geschwindigkeit_ms=self.df["geschwindigkeit_roh_ms"],
            segment_id=self.df["segment_id"],
        )
        self.df["beschleunigung_geglaettet_ms2"] = beschleunigung_aus_geschwindigkeit(
            zeitpunkte=self.df["time"],
            geschwindigkeit_ms=self.df["geschwindigkeit_geglaettet_ms"],
            segment_id=self.df["segment_id"],
        )

        if self.smoothing_config.enabled:
            self.df["geschwindigkeit_ms"] = self.df["geschwindigkeit_geglaettet_ms"]
            self.df["beschleunigung_ms2"] = self.df["beschleunigung_geglaettet_ms2"]
        else:
            self.df["geschwindigkeit_ms"] = self.df["geschwindigkeit_roh_ms"]
            self.df["beschleunigung_ms2"] = self.df["beschleunigung_roh_ms2"]

        self.df["speed_smoothing_enabled"] = self.smoothing_config.enabled
        self._smoothing_kennzahlen_loggen()

    def gesamtstrecke_km(self) -> float:
        return self.df["distanz_m"].sum() / 1000

    def durchschnittsgeschwindigkeit_kmh(self) -> float:
        gesamtzeit = self.gesamtzeit_s()
        if gesamtzeit <= 0:
            return 0.0
        return (self.df["distanz_m"].sum() / gesamtzeit) * 3.6

    def gesamtzeit_s(self) -> float:
        return (self.df["time"].iloc[-1] - self.df["time"].iloc[0]).total_seconds()

    def hoehenmeter_anstieg(self) -> float:
        dh = self.df["ele"].diff().fillna(0)
        return dh[dh > 0].sum()

    def hoehenmeter_abstieg(self) -> float:
        dh = self.df["ele"].diff().fillna(0)
        return -dh[dh < 0].sum()
    
    def haufigste_kompassrichtung(self) -> str:
        return self.df["kompassrichtung"].mode().iloc[0]

    def kennzahlen_ausgeben(self) -> None:
        print(f"Gesamtstrecke:                 {self.gesamtstrecke_km():.2f} km")
        print(f"Gesamtzeit:                    {self.gesamtzeit_s() / 60:.1f} min")
        print(f"Durchschnittsgeschwindigkeit:  {self.durchschnittsgeschwindigkeit_kmh():.1f} km/h")
        print(f"Höhenmeter Anstieg:            {self.hoehenmeter_anstieg():.0f} m")
        print(f"Höhenmeter Abstieg:            {self.hoehenmeter_abstieg():.0f} m")
        print(f"Häufigste Fahrtrichtung:        {self.haufigste_kompassrichtung()}")

    def smoothing_kennzahlen(self) -> dict[str, float | int]:
        return {
            "anzahl_gps_punkte": int(len(self.df)),
            "anzahl_ungueltiger_zeitintervalle": int(self.df["filter_ungueltiges_intervall"].sum()),
            "anzahl_kurzer_intervalle": int(self.df["filter_kurzes_intervall"].sum()),
            "anzahl_grosser_zeitluecken": int(self.df["filter_grosse_zeitluecke"].sum()),
            "anzahl_geschwindigkeitsausreisser": int(self.df["filter_geschwindigkeitsausreisser"].sum()),
            "anzahl_messabschnitte": int(self.df["segment_id"].nunique()),
            "max_rohgeschwindigkeit_kmh": float(self.df["geschwindigkeit_roh_ms"].max() * 3.6),
            "max_geglaettete_geschwindigkeit_kmh": float(self.df["geschwindigkeit_geglaettet_ms"].max() * 3.6),
            "max_rohbeschleunigung_ms2": float(self.df["beschleunigung_roh_ms2"].max()),
            "min_rohbeschleunigung_ms2": float(self.df["beschleunigung_roh_ms2"].min()),
            "max_geglaettete_beschleunigung_ms2": float(self.df["beschleunigung_geglaettet_ms2"].max()),
            "min_geglaettete_beschleunigung_ms2": float(self.df["beschleunigung_geglaettet_ms2"].min()),
            "max_aktive_geschwindigkeit_kmh": float(self.df["geschwindigkeit_ms"].max() * 3.6),
            "max_aktive_beschleunigung_ms2": float(self.df["beschleunigung_ms2"].max()),
            "min_aktive_beschleunigung_ms2": float(self.df["beschleunigung_ms2"].min()),
        }

    def _smoothing_kennzahlen_loggen(self) -> None:
        k = self.smoothing_kennzahlen()
        logger.info(
            "Geschwindigkeitsglaettung: %s",
            "aktiviert" if self.smoothing_config.enabled else "deaktiviert",
        )
        logger.info("Anzahl GPS-Punkte: %d", k["anzahl_gps_punkte"])
        logger.info("Anzahl ungueltiger Zeitintervalle: %d", k["anzahl_ungueltiger_zeitintervalle"])
        logger.info("Anzahl Intervalle unter min_interval_s: %d", k["anzahl_kurzer_intervalle"])
        logger.info("Anzahl Zeitluecken ueber max_gap_s: %d", k["anzahl_grosser_zeitluecken"])
        logger.info("Anzahl Geschwindigkeitsausreisser: %d", k["anzahl_geschwindigkeitsausreisser"])
        logger.info("Anzahl zusammenhaengender Messabschnitte: %d", k["anzahl_messabschnitte"])
        logger.info("Maximale Rohgeschwindigkeit: %.2f km/h", k["max_rohgeschwindigkeit_kmh"])
        logger.info(
            "Maximale geglaettete Geschwindigkeit: %.2f km/h",
            k["max_geglaettete_geschwindigkeit_kmh"],
        )
        logger.info("Maximale Rohbeschleunigung: %.2f m/s^2", k["max_rohbeschleunigung_ms2"])
        logger.info(
            "Maximale geglaettete Beschleunigung: %.2f m/s^2",
            k["max_geglaettete_beschleunigung_ms2"],
        )

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
            kartenstil (str): Name des Karten-Hintergrunds (folium-Tile-Name).
                Standard 'cartodbpositron', NICHT 'OpenStreetMap': Der
                offizielle OSM-Tile-Server verlangt inzwischen einen
                Referer-Header, den Browser beim direkten Öffnen einer
                lokalen HTML-Datei (file://...) nicht mitschicken - die
                Kacheln werden dann mit "403 Access blocked" abgelehnt.
                CartoDB-Kacheln funktionieren auch ohne Referer, deshalb als
                Standard gesetzt. 'OpenStreetMap' funktioniert weiterhin,
                wenn die Datei über einen echten Webserver aufgerufen wird
                (z.B. `python -m http.server` im output-Ordner, dann
                http://localhost:8000/... im Browser öffnen).

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
        karte = folium.Map(location=[mitte_lat, mitte_lon], zoom_start=zoom_start, tiles=kartenstil)

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

    # ------------------------------------------------------------------
    # Kartendarstellung (geopandas) - Alternative zu karte_erstellen()
    # ------------------------------------------------------------------
    def karte_erstellen_geopandas(
        self,
        df: pd.DataFrame = None,
        farbwert: str = "geschwindigkeit_ms",
        ausgabepfad: str = "track_karte_geopandas.png",
        mit_basiskarte: bool = True,
        cmap: str = "viridis",
    ):
        """
        Erstellt eine statische Kartendarstellung der Strecke mit GeoPandas
        + Matplotlib - inhaltlich das Gleiche wie karte_erstellen(), nur
        als GIS-taugliches GeoDataFrame statt als interaktive Leaflet-Karte.

        Vorgehen: pro Zeitschritt wird ein Liniensegment (shapely.LineString)
        zwischen zwei aufeinanderfolgenden GPS-Punkten erzeugt und mit dem
        Wert aus `farbwert` verknüpft. Die Segmente werden zu einem
        GeoDataFrame zusammengefasst und farbcodiert geplottet - dadurch
        entsteht optisch die gleiche "Regenbogen-Strecke" wie bei folium,
        aber als Vektordaten (georeferenziert, exportierbar z.B. als
        GeoJSON/Shapefile für QGIS & Co., siehe gdf.to_file(...)).

        Parameter:
            df, farbwert: wie bei karte_erstellen()
            ausgabepfad (str): Pfad der zu speichernden PNG-Datei
            mit_basiskarte (bool): ob ein OpenStreetMap-Hintergrund über
                `contextily` geladen werden soll. Benötigt Internetzugriff;
                schlägt das Laden fehl, wird automatisch ohne Hintergrund
                weitergemacht (nur die Strecke selbst, kein Fehlerabbruch).
            cmap (str): Matplotlib-Farbschema (z.B. 'viridis', 'plasma',
                'coolwarm')

        Rückgabe:
            geopandas.GeoDataFrame: Liniensegmente inkl. Attributwert -
            kann z.B. direkt weiter für GIS-Analysen oder Export genutzt
            werden.
        """
        import geopandas as gpd
        from shapely.geometry import LineString
        import matplotlib.pyplot as plt

        if df is None:
            df = self.df

        if farbwert not in df.columns:
            raise ValueError(
                f"Spalte '{farbwert}' nicht im DataFrame vorhanden. "
                f"Verfügbare Spalten: {list(df.columns)}"
            )

        # Liniensegmente + zugehörigen Wert pro Segment sammeln
        segmente = []
        werte = []
        for i in range(len(df) - 1):
            punkt_a = (df["lon"].iloc[i], df["lat"].iloc[i])
            punkt_b = (df["lon"].iloc[i + 1], df["lat"].iloc[i + 1])
            segmente.append(LineString([punkt_a, punkt_b]))
            werte.append(df[farbwert].iloc[i])

        # GeoDataFrame in WGS84 (Grad, wie GPS-Rohdaten) anlegen ...
        gdf = gpd.GeoDataFrame({farbwert: werte, "geometry": segmente}, crs="EPSG:4326")
        # ... und für die Basiskarten-Kompatibilität nach Web-Mercator umprojizieren
        gdf_web = gdf.to_crs(epsg=3857)

        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_web.plot(
            column=farbwert,
            cmap=cmap,
            linewidth=3,
            legend=True,
            ax=ax,
            legend_kwds={"label": farbwert, "shrink": 0.7},
        )

        if mit_basiskarte:
            try:
                import contextily as cx
                cx.add_basemap(ax, source=cx.providers.OpenStreetMap.Mapnik, crs=gdf_web.crs.to_string())
            except Exception as fehler:
                logger.warning(
                    f"Basiskarte konnte nicht geladen werden ({fehler}) - "
                    "Plot wird ohne Kartenhintergrund gespeichert."
                )

        ax.set_title(f"Streckenverlauf eingefärbt nach: {farbwert}")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(ausgabepfad, dpi=200)
        plt.close(fig)

        logger.info(f"Karte (GeoPandas) gespeichert unter: {ausgabepfad}")
        return gdf

    # ------------------------------------------------------------------
    # Kartendarstellung (geopandas) - einfache Variante OHNE Einfärbung
    # ------------------------------------------------------------------
    def karte_erstellen_geopandas_einfach(
        self,
        df: pd.DataFrame = None,
        ausgabepfad: str = "track_karte_geopandas_einfach.png",
        mit_basiskarte: bool = True,
        linienfarbe: str = "royalblue",
    ):
        """
        Vereinfachte GeoPandas-Kartendarstellung OHNE farbliche Einfärbung
        nach einem Messwert - zeigt nur den reinen Streckenverlauf als
        einheitlich eingefärbte Linie, plus Start- und Zielpunkt.

        Unterschied zu karte_erstellen_geopandas(): dort wird die Strecke in
        einzelne Segmente zerlegt, damit jedes Segment individuell nach einem
        Messwert eingefärbt werden kann. Hier ist das nicht nötig, deshalb
        wird die GESAMTE Strecke als EIN einziges LineString-Objekt behandelt -
        einfacher, schneller und mit kleinerer Ausgabedatei, wenn nur der
        reine Streckenverlauf interessiert (ohne Geschwindigkeit/SoC/etc.).

        Parameter:
            df (pd.DataFrame | None): Zu plottende Daten. Wenn None, wird
                self.df verwendet. Erwartet werden die Spalten 'lat'/'lon'.
            ausgabepfad (str): Pfad der zu speichernden PNG-Datei.
            mit_basiskarte (bool): ob ein OpenStreetMap-Hintergrund über
                `contextily` geladen werden soll (mit automatischem Fallback,
                falls kein Internetzugriff auf die Kartenkacheln möglich ist).
            linienfarbe (str): Matplotlib-Farbname oder Hex-Code für die
                Streckenlinie (z.B. 'royalblue', 'black', '#FF5733').

        Rückgabe:
            geopandas.GeoDataFrame: enthält genau eine Zeile mit der
            gesamten Strecke als LineString-Geometrie - z.B. praktisch für
            den Export als GeoJSON/Shapefile (gdf.to_file(...)).
        """
        import geopandas as gpd
        from shapely.geometry import LineString, Point
        import matplotlib.pyplot as plt

        if df is None:
            df = self.df

        # Gesamte Strecke als EIN LineString (statt einzelner Segmente),
        # da keine Einfärbung pro Abschnitt nötig ist.
        koordinaten = list(zip(df["lon"], df["lat"]))
        strecke = LineString(koordinaten)

        gdf = gpd.GeoDataFrame({"name": ["Strecke"], "geometry": [strecke]}, crs="EPSG:4326")
        gdf_web = gdf.to_crs(epsg=3857)

        # Start-/Zielpunkt als eigenes kleines GeoDataFrame für die Marker
        start_ziel = gpd.GeoDataFrame(
            {"typ": ["Start", "Ziel"]},
            geometry=[Point(koordinaten[0]), Point(koordinaten[-1])],
            crs="EPSG:4326",
        ).to_crs(epsg=3857)

        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_web.plot(ax=ax, color=linienfarbe, linewidth=3)
        start_ziel.plot(ax=ax, color=["green", "red"], markersize=100, zorder=5, edgecolor="black")

        for x, y, label in zip(start_ziel.geometry.x, start_ziel.geometry.y, start_ziel["typ"]):
            ax.annotate(
                label, xy=(x, y), xytext=(6, 6), textcoords="offset points",
                fontsize=10, fontweight="bold",
            )

        if mit_basiskarte:
            try:
                import contextily as cx
                cx.add_basemap(ax, source=cx.providers.OpenStreetMap.Mapnik, crs=gdf_web.crs.to_string())
            except Exception as fehler:
                logger.warning(
                    f"Basiskarte konnte nicht geladen werden ({fehler}) - "
                    "Plot wird ohne Kartenhintergrund gespeichert."
                )

        ax.set_title("Streckenverlauf")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(ausgabepfad, dpi=200)
        plt.close(fig)

        logger.info(f"Karte (GeoPandas, ohne Einfärbung) gespeichert unter: {ausgabepfad}")
        return gdf
