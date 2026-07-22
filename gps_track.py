"""
gps_track.py
------------
Enthält die Klasse GPSTrack. Sie kapselt alles, was mit den rohen
GPS-Aufzeichnungen zu tun hat:
- Einlesen der CSV-Datei
- Berechnung von Distanz, Geschwindigkeit, Beschleunigung und Steigung
  zwischen aufeinanderfolgenden Punkten
- Kenngrößen für die gesamte Fahrt (Strecke, Ø-Geschwindigkeit, Höhenmeter, ...)
- Reverse Geocoding (GPS-Koordinaten -> lesbare Adressen)
- Kartendarstellung der Strecke (interaktiv via folium, statisch via Matplotlib)

Die Klasse enthält bewusst NUR die Auswertung der reinen Positionsdaten.
Alles, was mit dem Fahrzeug (Kräfte, Leistung, Motor) oder dem Akku zu tun
hat, gehört NICHT hierher, sondern in eigene Klassen (siehe ebike.py,
battery.py). Das entspricht dem Prinzip "eine Klasse = eine Zuständigkeit".
"""

<<<<<<< HEAD
import math                # für trigonometrische Funktionen (sin, cos, atan2, radians)
import logging             # für Logging statt einfacher print()-Ausgaben
import pandas as pd        # für die Tabellen-Verarbeitung (DataFrame)
=======
import math
import logging
import pandas as pd
from pathlib import Path

from speed_smoothing import (
    SpeedSmoothingConfig,
    beschleunigung_aus_geschwindigkeit,
    geschwindigkeit_glaetten,
)
>>>>>>> b492d1f496c722c96632ba499740007064923d97

# Ein eigener Logger pro Modul ist Standard, damit man in den Log-Meldungen
# später sieht, aus welcher Datei/Klasse die Meldung kommt.
logger = logging.getLogger(__name__)


class GPSTrack:
    """
    Repräsentiert eine einzelne GPS-Aufzeichnung (Track) als Objekt.

    Attribute:
        df (pd.DataFrame): Tabelle mit den Rohdaten + berechneten Spalten
                            (distanz_m, geschwindigkeit_ms, beschleunigung_ms2,
                            steigung_grad)
        orte (pd.DataFrame): erst vorhanden, nachdem orte_ermitteln() einmal
                            aufgerufen wurde (Adressen entlang der Strecke)
    """

    # Klassenattribut: gilt für alle Objekte gleich, deshalb hier oben
    # definiert und nicht in __init__ (spart Speicher, ist inhaltlich eine Konstante)
    ERDRADIUS_M = 6_371_000     # mittlerer Erdradius in Metern (für Haversine-Formel)

<<<<<<< HEAD
    def __init__(self, pfad: str):
        """
        Konstruktor: liest die Datei ein und berechnet direkt die Kinematik,
        damit ein GPSTrack-Objekt nach dem Erzeugen sofort vollständig
        einsatzbereit ist (keine weiteren Vorbereitungsschritte nötig).
        """
        self.df = self._datei_einlesen(pfad)     # Rohdaten laden
        self._kinematik_berechnen()               # df um berechnete Spalten erweitern

    # ------------------------------------------------------------------
    # Private Hilfsmethoden (Konvention: führender Unterstrich "_")
    # Diese Methoden sind nur für den internen Gebrauch innerhalb der
    # Klasse gedacht, nicht für den Aufruf von außen.
    # ------------------------------------------------------------------

    def _datei_einlesen(self, pfad: str) -> pd.DataFrame:
        """Liest die CSV-Datei ein und wandelt die Zeit-Spalte in ein Datum/Zeit-Objekt um."""
        logger.info(f"Lese GPS-Daten ein aus: {pfad}")
        df = pd.read_csv(pfad, sep=";")             # CSV einlesen; sep=";" da Semikolon-getrennt
        df["time"] = pd.to_datetime(df["time"])      # Text -> echtes Datum/Zeit-Objekt
=======
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
>>>>>>> b492d1f496c722c96632ba499740007064923d97
        return df

    def _distanz_haversine(self, lat1, lon1, lat2, lon2) -> float:
        """Distanz zwischen zwei GPS-Punkten in Metern nach der Haversine-Formel."""
        lat1_rad = math.radians(lat1)               # Grad -> Radiant
        lat2_rad = math.radians(lat2)
        delta_lat = lat2_rad - lat1_rad
        delta_lon = math.radians(lon2) - math.radians(lon1)

        # Haversine-Zwischenwert a (Winkelabstand der zwei Punkte, ergibt einen Wert zwischen 0 und 1)
        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        # asin(sqrt(a)) = halber Zentriwinkel; *2 wegen Formel-Herleitung;
        # *ERDRADIUS_M rechnet den Winkel in eine Bogenlänge (= Distanz) in Metern um
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
        """
        Geht die gesamte Tabelle Zeile für Zeile durch und berechnet für jeden
        Punkt (im Vergleich zu seinem Vorgänger) Distanz, Geschwindigkeit,
        Beschleunigung und Steigungswinkel. Ergebnisse werden als neue Spalten
        direkt in self.df geschrieben.
        """
        n = len(self.df)
<<<<<<< HEAD

        # Listen vorbereiten, erster Punkt hat keinen Vorgänger -> Platzhalter 0
=======
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
>>>>>>> b492d1f496c722c96632ba499740007064923d97
        distanz = [0.0] * n
        geschwindigkeit_roh = [0.0] * n
        steigung_grad = [0.0] * n
        kurs_grad = [0.0] * n
        kompassrichtung = ["N"] * n

        for i in range(1, n):   # ab Index 1, da Index 0 keinen Vorgänger hat
            # Zeitdifferenz zum Vorgänger in Sekunden
            dt = (self.df["time"].iloc[i] - self.df["time"].iloc[i - 1]).total_seconds()
            dt_s[i] = dt

            # Distanz zum Vorgänger in Metern
            d = self._distanz_haversine(
                self.df["lat"].iloc[i - 1], self.df["lon"].iloc[i - 1],
                self.df["lat"].iloc[i], self.df["lon"].iloc[i],
            )
            distanz[i] = d
<<<<<<< HEAD

            # Geschwindigkeit = Distanz / Zeit (Division durch 0 abfangen)
            geschwindigkeit[i] = d / dt if dt > 0 else 0.0

            # Beschleunigung = Geschwindigkeitsänderung / Zeit
            beschleunigung[i] = (geschwindigkeit[i] - geschwindigkeit[i - 1]) / dt if dt > 0 else 0.0
=======
            geschwindigkeit_roh[i] = d / dt if dt > 0 else 0.0
>>>>>>> b492d1f496c722c96632ba499740007064923d97

            # Steigungswinkel phi in Grad: atan2(Höhenunterschied, horizontale Distanz)
            # atan2 statt atan, damit auch Gefälle (negative Höhenänderung) korrekt erfasst wird
            dh = self.df["ele"].iloc[i] - self.df["ele"].iloc[i - 1]
            steigung_grad[i] = math.degrees(math.atan2(dh, d)) if d > 0 else 0.0
    
            kurs_grad[i] = self._kurs_grad(
                self.df["lat"].iloc[i - 1], self.df["lon"].iloc[i - 1],
                self.df["lat"].iloc[i], self.df["lon"].iloc[i]
            )
            kompassrichtung[i] = self._kompassrichtung(kurs_grad[i])

<<<<<<< HEAD
        # Berechnete Listen als neue Spalten in die Tabelle schreiben
=======
        self.df["dt_s"] = dt_s
>>>>>>> b492d1f496c722c96632ba499740007064923d97
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

    # ------------------------------------------------------------------
    # Öffentliche Methoden: Kenngrößen für die gesamte Fahrt
    # ------------------------------------------------------------------

    def gesamtstrecke_km(self) -> float:
        """Summe aller Einzeldistanzen, umgerechnet von Metern in Kilometer."""
        return self.df["distanz_m"].sum() / 1000

    def durchschnittsgeschwindigkeit_kmh(self) -> float:
<<<<<<< HEAD
        """Mittelwert aller Geschwindigkeiten, umgerechnet von m/s in km/h."""
        return self.df["geschwindigkeit_ms"].mean() * 3.6
=======
        gesamtzeit = self.gesamtzeit_s()
        if gesamtzeit <= 0:
            return 0.0
        return (self.df["distanz_m"].sum() / gesamtzeit) * 3.6
>>>>>>> b492d1f496c722c96632ba499740007064923d97

    def gesamtzeit_s(self) -> float:
        """Zeitdauer der gesamten Fahrt in Sekunden (letzter Zeitpunkt - erster Zeitpunkt)."""
        return (self.df["time"].iloc[-1] - self.df["time"].iloc[0]).total_seconds()

    def hoehenmeter_anstieg(self) -> float:
        """Summe aller positiven Höhenänderungen (nur bergauf-Anteile)."""
        dh = self.df["ele"].diff().fillna(0)    # Höhenänderung von Zeile zu Zeile
        return dh[dh > 0].sum()

    def hoehenmeter_abstieg(self) -> float:
        """Summe aller negativen Höhenänderungen (nur bergab-Anteile), als positiver Wert."""
        dh = self.df["ele"].diff().fillna(0)
        return -dh[dh < 0].sum()
    
    def haufigste_kompassrichtung(self) -> str:
        return self.df["kompassrichtung"].mode().iloc[0]

    def kennzahlen_text(self) -> str:
        """
        Baut den Kennzahlen-Text als einen einzigen mehrzeiligen String -
        exakt der gleiche Text, der auch von kennzahlen_ausgeben() auf der
        Konsole ausgegeben wird. So gibt es nur EINE Stelle im Code, an der
        dieser Text definiert wird - er kann z.B. im LaTeX-Bericht 1:1
        wiederverwendet werden, statt ihn ein zweites Mal separat aufzubauen.
        """
        zeilen = [
            # Die Leerzeichen nach dem Doppelpunkt richten die Werte optisch
            # untereinander aus (fester Text links, Wert rechts daneben).
            f"Gesamtstrecke:                 {self.gesamtstrecke_km():.2f} km",
            f"Gesamtzeit:                    {self.gesamtzeit_s() / 60:.1f} min",
            f"Durchschnittsgeschwindigkeit:  {self.durchschnittsgeschwindigkeit_kmh():.1f} km/h",
            f"Höhenmeter Anstieg:            {self.hoehenmeter_anstieg():.0f} m",
            f"Höhenmeter Abstieg:            {self.hoehenmeter_abstieg():.0f} m",
        ]
        return "\n".join(zeilen)

    def kennzahlen_ausgeben(self) -> None:
<<<<<<< HEAD
        """Gibt die wichtigsten Kenngrößen der Fahrt formatiert auf der Konsole aus."""
        # Nur eine dünne Hülle um kennzahlen_text(): so bleibt der Text an
        # genau einer Stelle im Code definiert.
        print(self.kennzahlen_text())
=======
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
>>>>>>> b492d1f496c722c96632ba499740007064923d97

    def __str__(self) -> str:
        """Wird aufgerufen, wenn man z.B. print(track) schreibt -> lesbare Kurzbeschreibung."""
        return f"GPSTrack({len(self.df)} Punkte, {self.gesamtstrecke_km():.2f} km)"

    # ------------------------------------------------------------------
    # Reverse Geocoding (GPS-Koordinaten -> Adresse/Ort)
    # ------------------------------------------------------------------

    def orte_ermitteln(
        self,
        anzahl_wegpunkte: int = 8,
        user_agent: str = "abschlussprojekt_ebike_simulation",
    ) -> pd.DataFrame:
        """
        Wandelt GPS-Koordinaten entlang der Strecke in lesbare Adressen um
        (Reverse Geocoding via Nominatim/OpenStreetMap, kostenlos).

        Aus Rücksicht auf die Nominatim-Nutzungsbedingungen (max. 1 Anfrage/
        Sekunde, keine Massenabfragen) wird NICHT jeder einzelne GPS-Punkt
        abgefragt - bei diesem Track wären das >2000 Anfragen, also >35
        Minuten Laufzeit und ein klarer Verstoß gegen die Nutzungsbedingungen.
        Stattdessen werden Start, Ziel und `anzahl_wegpunkte` gleichmäßig
        verteilte Zwischenpunkte entlang der Strecke abgefragt.

        Parameter:
            anzahl_wegpunkte (int): Anzahl zusätzlicher Zwischenpunkte
                (zusätzlich zu Start/Ziel), gleichmäßig über die Strecke verteilt.
            user_agent (str): Eindeutiger App-Name für die Nominatim-Anfrage
                (von OSM gefordert, sonst wird die Anfrage abgelehnt).

        Rückgabe:
            pd.DataFrame mit Spalten: index (Position im Track), lat, lon,
            adresse (voller Adressstring, oder None bei Fehlschlag). Wird
            zusätzlich als self.orte gespeichert und von karte_erstellen()
            automatisch für die Marker-Popups verwendet. Es findet KEINE
            Speicherung auf der Festplatte statt - das Ergebnis lebt nur,
            solange das Programm läuft.
        """
        # Import erst hier (nicht ganz oben in der Datei), damit geopy nur
        # gebraucht wird, wenn diese Methode auch wirklich aufgerufen wird
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter

        n = len(self.df)

        # Indizes bestimmen: Start (0), gleichmäßig verteilte Zwischenpunkte
        # und Ziel (n-1). Wir teilen die Strecke in (anzahl_wegpunkte + 1)
        # gleich große Abschnitte und nehmen jeweils den Punkt am Anfang
        # jedes Abschnitts.
        abstand = n // (anzahl_wegpunkte + 1)

        indizes = []
        for i in range(anzahl_wegpunkte + 1):
            indizes.append(i * abstand)

        indizes.append(n - 1)  # Ziel garantiert mit aufnehmen

        # Nominatim-Client aufbauen: geolocator.reverse() ist die Funktion,
        # die aus (lat, lon) eine Adresse macht.
        # timeout=10: bricht eine einzelne Anfrage nach 10 Sekunden mit
        # einem Fehler ab, statt bei einer langsamen/gestörten Verbindung
        # (z.B. Firewall, die Pakete stumm verwirft) unbegrenzt zu hängen.
        # Der Fehler wird unten im try/except abgefangen wie jeder andere
        # Netzwerkfehler auch.
        geolocator = Nominatim(user_agent=user_agent, timeout=10)
        # RateLimiter erzwingt die von Nominatim geforderte Pause zwischen
        # Anfragen (>= 1 Sekunde)
        reverse = RateLimiter(geolocator.reverse, min_delay_seconds=1)

        ergebnisse = []
        for idx in indizes:
            # Koordinaten an diesem Index auslesen; float(...) wandelt den
            # numpy-Zahlentyp von pandas in eine normale Python-Zahl um
            lat = float(self.df["lat"].iloc[idx])
            lon = float(self.df["lon"].iloc[idx])

            try:
                # Eigentliche Netzwerk-Anfrage an Nominatim
                location = reverse((lat, lon), language="de")
                # location kann None sein, wenn für diese Koordinate keine
                # Adresse gefunden wurde (z.B. mitten im Wald/auf dem Meer)
                adresse = location.address if location else None
                logger.info(f"Adresse abgefragt (Index {idx}): {adresse}")
            except Exception as fehler:
                # Netzwerkfehler o.ä. abfangen, damit das Programm nicht
                # abstürzt - stattdessen wird die Adresse einfach None
                logger.warning(f"Reverse Geocoding fehlgeschlagen (Index {idx}): {fehler}")
                adresse = None

            ergebnisse.append({"index": idx, "lat": lat, "lon": lon, "adresse": adresse})

        # Ergebnis nur im Arbeitsspeicher ablegen (self.orte) - keine
        # CSV-Datei. karte_erstellen() liest direkt von hier.
        self.orte = pd.DataFrame(ergebnisse)

        return self.orte

    # ------------------------------------------------------------------
    # Kartendarstellung (folium) - interaktive HTML-Karte
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
        Erstellt eine interaktive HTML-Karte (Leaflet über folium) mit der
        gefahrenen Strecke als farbcodierter Linie.

        Parameter:
            df (pd.DataFrame | None): Zu plottende Daten. Wenn None, wird
                self.df verwendet. Erwartet werden mind. die Spalten 'lat'
                und 'lon' sowie die in farbwert angegebene Spalte (z.B. auch
                das Ergebnis-DataFrame von EBikeSimulator.simulate(), das
                zusätzlich 'soc', 'spannung_V', 'motorstrom_A' etc. enthält).
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
                CartoDB-Kacheln funktionieren auch ohne Referer.

        Rückgabe:
            folium.Map: das erzeugte Karten-Objekt (zusätzlich zum Speichern
            auf der Festplatte, z.B. praktisch für die Einbettung in Jupyter).
        """
        import folium
        import branca.colormap as cm

        # Falls kein eigenes DataFrame übergeben wurde, die Trackdaten
        # dieses Objekts (self.df) verwenden
        if df is None:
            df = self.df

        if farbwert not in df.columns:
            raise ValueError(
                f"Spalte '{farbwert}' nicht im DataFrame vorhanden. "
                f"Verfügbare Spalten: {list(df.columns)}"
            )

        # Kartenmittelpunkt = Durchschnitt aller Koordinaten der Strecke
        mitte_lat = df["lat"].mean()
        mitte_lon = df["lon"].mean()
        karte = folium.Map(location=[mitte_lat, mitte_lon], zoom_start=zoom_start, tiles=kartenstil)

        # Farbskala, die von Minimal- bis Maximalwert des gewählten Merkmals
        # (z.B. Geschwindigkeit) von blau über grün/gelb bis rot verläuft
        werte = df[farbwert]
        farbskala = cm.LinearColormap(
            colors=["blue", "green", "yellow", "red"],
            vmin=float(werte.min()),
            vmax=float(werte.max()),
            caption=farbwert,
        )

        # Strecke in einzelne Zwei-Punkt-Segmente zerlegen, damit jedes
        # Segment einzeln nach seinem Wert (z.B. Geschwindigkeit an dieser
        # Stelle) eingefärbt werden kann - so entsteht der Regenbogen-Effekt
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

        # Popups mit Adresse anreichern, falls orte_ermitteln() zuvor
        # aufgerufen wurde (self.orte). Sonst Fallback auf generischen Text.
        start_popup, ziel_popup = "Start", "Ziel"
        orte = getattr(self, "orte", None)
        if orte is not None and len(orte) > 0:
            start_adresse = orte.iloc[0]["adresse"]
            ziel_adresse = orte.iloc[-1]["adresse"]
            if start_adresse:
                start_popup = f"Start: {start_adresse}"
            if ziel_adresse:
                ziel_popup = f"Ziel: {ziel_adresse}"

        folium.Marker(
            koordinaten[0], popup=start_popup, icon=folium.Icon(color="green", icon="play")
        ).add_to(karte)
        folium.Marker(
            koordinaten[-1], popup=ziel_popup, icon=folium.Icon(color="red", icon="stop")
        ).add_to(karte)

        # Zusätzliche Zwischen-Marker mit Adresse für die per orte_ermitteln()
        # abgefragten Wegpunkte (ohne Start/Ziel, die bereits oben gesetzt sind)
        if orte is not None and len(orte) > 2:
            for _, zeile in orte.iloc[1:-1].iterrows():
                if zeile["adresse"]:
                    folium.Marker(
                        [zeile["lat"], zeile["lon"]],
                        popup=zeile["adresse"],
                        icon=folium.Icon(color="blue", icon="info-sign"),
                    ).add_to(karte)

        # Farbskala als Legende in die Karte einfügen und die fertige Karte
        # als eigenständige HTML-Datei abspeichern (im Browser öffenbar)
        farbskala.add_to(karte)
        karte.save(ausgabepfad)
        logger.info(f"Karte gespeichert unter: {ausgabepfad}")
        return karte

    # ------------------------------------------------------------------
    # Kartendarstellung (GeoPandas) - statischer Plot als PNG, mit echtem
    # OpenStreetMap-Kartenhintergrund (via contextily)
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
        Wert aus farbwert verknüpft. Die Segmente werden zu einem
        GeoDataFrame zusammengefasst und farbcodiert geplottet.

        Parameter:
            df, farbwert: wie bei karte_erstellen()
            ausgabepfad (str): Pfad der zu speichernden PNG-Datei
            mit_basiskarte (bool): ob ein Kartenhintergrund (CartoDB
                Positron) über contextily geladen werden soll. Benötigt
                Internetzugriff; schlägt das Laden fehl, wird automatisch
                ohne Hintergrund weitergemacht (kein Fehlerabbruch).
                NICHT der offizielle OpenStreetMap-Tile-Server: der
                blockiert automatisierte Anfragen häufig mit "403
                Forbidden" (gleicher Grund wie bei karte_erstellen()).
                CartoDB liefert die gleichen OSM-Daten über einen
                freundlicheren Server aus.
            cmap (str): Matplotlib-Farbschema (z.B. 'viridis', 'plasma', 'coolwarm')

        Rückgabe:
            geopandas.GeoDataFrame: Liniensegmente inkl. Attributwert -
            kann z.B. direkt weiter für GIS-Analysen oder Export genutzt werden.
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
                # CartoDB Positron statt offiziellem OSM-Tile-Server:
                # tile.openstreetmap.org blockiert automatisierte Anfragen
                # oft mit "403 Forbidden" (gleiches Problem wie bei
                # karte_erstellen()). CartoDB liefert die gleichen
                # OSM-Daten über einen unkomplizierteren Server.
                # timeout=10: bricht das Laden nach 10 Sekunden ab, statt
                # bei einer hängenden Verbindung unbegrenzt zu warten.
                import contextily as cx
                cx.add_basemap(
                    ax, source=cx.providers.CartoDB.Positron,
                    crs=gdf_web.crs.to_string(), timeout=10,
                )
            except Exception as fehler:
                # Kein Absturz, falls kein Internetzugriff möglich ist -
                # der Plot wird dann einfach ohne Kartenhintergrund gespeichert
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
    # Kartendarstellung (GeoPandas) - einfache Variante OHNE Einfärbung
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
        wird die GESAMTE Strecke als EIN einziges LineString-Objekt behandelt.

        Parameter:
            df (pd.DataFrame | None): Zu plottende Daten. Wenn None, wird
                self.df verwendet. Erwartet werden die Spalten 'lat'/'lon'.
            ausgabepfad (str): Pfad der zu speichernden PNG-Datei.
            mit_basiskarte (bool): ob ein Kartenhintergrund (CartoDB
                Positron) über contextily geladen werden soll (mit
                automatischem Fallback, falls kein Internetzugriff auf die
                Kartenkacheln möglich ist).
            linienfarbe (str): Matplotlib-Farbname oder Hex-Code für die
                Streckenlinie (z.B. 'royalblue', 'black', '#FF5733').

        Rückgabe:
            geopandas.GeoDataFrame: enthält genau eine Zeile mit der
            gesamten Strecke als LineString-Geometrie.
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

        # Strecke als Linie und Start-/Zielpunkt als farbige Marker plotten
        fig, ax = plt.subplots(figsize=(10, 10))
        gdf_web.plot(ax=ax, color=linienfarbe, linewidth=3)
        start_ziel.plot(ax=ax, color=["green", "red"], markersize=100, zorder=5, edgecolor="black")

        # Textbeschriftung ("Start"/"Ziel") neben die beiden Marker schreiben
        for x, y, label in zip(start_ziel.geometry.x, start_ziel.geometry.y, start_ziel["typ"]):
            ax.annotate(
                label, xy=(x, y), xytext=(6, 6), textcoords="offset points",
                fontsize=10, fontweight="bold",
            )

        if mit_basiskarte:
            try:
                import contextily as cx
                # CartoDB Positron statt OSM-Server (siehe Erklärung oben
                # in karte_erstellen_geopandas) - timeout=10 gegen unbegrenztes Warten
                cx.add_basemap(
                    ax, source=cx.providers.CartoDB.Positron,
                    crs=gdf_web.crs.to_string(), timeout=10,
                )
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
