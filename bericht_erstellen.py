"""
bericht_erstellen.py
---------------------
Erstellt automatisch einen vollständigen LaTeX-Bericht (.tex-Datei) aus
einem GPSTrack-Objekt: Kennzahlen, Orte entlang der Strecke (Reverse
Geocoding) und eine Kartenübersicht als eingebundene Grafik.

Bewusst als eigenständiges Modul (statt als Methode auf GPSTrack) gehalten:
Die Berichterstellung ist reine Präsentationslogik und nutzt nur die
öffentlichen Methoden von GPSTrack (orte_ermitteln, karte_erstellen_geopandas,
gesamtstrecke_km, ...) - sie muss die Klasse selbst nicht verändern oder
kennen, wie diese intern aufgebaut ist.

Nutzung (z.B. aus main.py):
    from bericht_erstellen import bericht_erstellen
    bericht_erstellen(track)
"""

import os                  # für Pfad-Operationen (Ordner anlegen, Dateiname extrahieren)
import logging             # für Info-/Warnmeldungen, passend zum Rest des Projekts
import subprocess          # um pdflatex als externes Programm aufzurufen

logger = logging.getLogger(__name__)


def _latex_escape(text: str | None) -> str:
    """
    Ersetzt LaTeX-Sonderzeichen (&, %, $, #, _, {, }, ~, ^, \\) durch ihre
    escapte Form. Nötig, weil Adressen aus dem Reverse Geocoding z.B.
    Sonderzeichen enthalten können (Straßen mit "&", Hausnummern mit "#"
    o.ä.), die sonst den LaTeX-Bericht zum Absturz bringen würden.

    text ist als str | None getippt, weil eine Adresse auch None sein kann
    (z.B. wenn Nominatim für eine Koordinate nichts gefunden hat).
    """
    if text is None:
        return ""
    text = str(text)

    # Backslash MUSS zuerst ersetzt werden - sonst würden die durch die
    # anderen Ersetzungen neu eingefügten Backslashes selbst nochmal
    # (fälschlicherweise) escaped werden.
    ersetzungen = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for alt, neu in ersetzungen:
        # Jedes Sonderzeichen ("alt") wird nacheinander durch seine
        # LaTeX-sichere Variante ("neu") ersetzt, z.B. "&" wird zu "\&"
        text = text.replace(alt, neu)
    return text


def _pdf_kompilieren(tex_pfad: str) -> bool:
    """
    Kompiliert eine .tex-Datei zu PDF, indem pdflatex als externes Programm
    aufgerufen wird (subprocess). Läuft nur EINMAL: unser Bericht enthält
    weder ein Inhaltsverzeichnis noch Querverweise/Zitate, die - wie bei
    komplexeren LaTeX-Dokumenten üblich - erst einen zweiten Durchlauf
    bräuchten, um korrekt aufgelöst zu werden. Ein Durchlauf reicht daher aus.

    Schlägt die Kompilierung fehl (z.B. weil pdflatex nicht installiert
    ist), wird das nur als Warnung geloggt - kein Programmabsturz, da die
    .tex-Datei selbst ja bereits erfolgreich erstellt wurde.

    Parameter:
        tex_pfad (str): Pfad zur .tex-Datei, die kompiliert werden soll.

    Rückgabe:
        bool: True, wenn die PDF-Datei erfolgreich erstellt wurde, sonst False.
    """
    # pdflatex erwartet Ordner und Dateiname getrennt (-output-directory
    # bzw. den reinen Dateinamen als letztes Argument)
    verzeichnis = os.path.dirname(tex_pfad) or "."
    dateiname = os.path.basename(tex_pfad)

    try:
        ergebnis = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",  # bei Fehlern nicht auf Tastatureingabe warten
                # "." statt verzeichnis: cwd=verzeichnis (siehe unten) wechselt
                # das Arbeitsverzeichnis bereits nach z.B. "output" - würde man
                # hier nochmal "output" als relativen Pfad übergeben, würde
                # pdflatex das relativ zum NEUEN Arbeitsverzeichnis auflösen
                # und einen verschachtelten Ordner output/output/ anlegen.
                "-output-directory", ".",
                dateiname,
            ],
            cwd=verzeichnis,
            capture_output=True,  # Konsolen-Ausgabe von pdflatex abfangen statt im Terminal auszugeben
            text=True,            # Ausgabe als String statt als Bytes
            timeout=60,           # Sicherheitsnetz, falls pdflatex sich aufhängt
        )
        if ergebnis.returncode != 0:
            # returncode != 0 heißt: pdflatex hatte einen Fehler (z.B.
            # kaputtes LaTeX). Die genaue Fehlermeldung steht in der
            # zugehörigen .log-Datei im Ausgabeordner.
            logger.warning(
                f"pdflatex meldete einen Fehler (returncode {ergebnis.returncode}) "
                f"- siehe .log-Datei im Ausgabeordner für Details."
            )
    except FileNotFoundError:
        # pdflatex ist auf diesem Rechner nicht installiert/nicht im PATH
        logger.warning(
            "pdflatex wurde nicht gefunden - PDF konnte nicht automatisch "
            "erstellt werden. Die .tex-Datei ist trotzdem vollständig und "
            "kann später manuell kompiliert werden (siehe Docstring)."
        )
        return False
    except subprocess.TimeoutExpired:
        logger.warning("pdflatex hat das Zeitlimit überschritten - PDF wurde nicht erstellt.")
        return False

    # Erfolg wird NICHT nur am returncode festgemacht (pdflatex gibt bei
    # kleineren Warnungen manchmal trotzdem 0 zurück oder umgekehrt) -
    # stattdessen prüfen wir einfach direkt, ob die PDF-Datei tatsächlich
    # auf der Festplatte existiert.
    pdf_pfad = os.path.join(verzeichnis, dateiname.replace(".tex", ".pdf"))
    if os.path.exists(pdf_pfad):
        logger.info(f"PDF erfolgreich erstellt: {pdf_pfad}")
        return True
    return False


def bericht_erstellen(
    track,
    tex_pfad: str = "output/bericht.tex",
    karte_pfad: str = "output/bericht_karte.png",
    titel: str = "Abschlussprojekt: Auswertung der GPS-Strecke",
    pdf_erstellen: bool = True,
) -> str:
    """
    Erstellt automatisch einen vollständigen LaTeX-Bericht (.tex-Datei) mit
    drei Abschnitten:
      1. Kennzahlen (Strecke, Zeit, Geschwindigkeit, Höhenmeter)
      2. Orte entlang der Strecke (Ergebnis von track.orte_ermitteln())
      3. Eine statische Kartenübersicht (PNG, per GeoPandas + contextily
         erzeugt, mit echtem OpenStreetMap-Kartenhintergrund) als
         eingebundene Grafik

    Wurde track.orte_ermitteln() vorher noch nicht aufgerufen, holt diese
    Funktion die Orte automatisch selbst nach (mit Standardwerten), damit
    der Bericht immer vollständig ist, egal in welcher Reihenfolge die
    Methoden aufgerufen wurden.

    Ist pdf_erstellen=True (Standard), wird die .tex-Datei zusätzlich
    automatisch per pdflatex zu einem PDF kompiliert (siehe
    _pdf_kompilieren()). Ist auf dem Rechner kein pdflatex installiert,
    wird das nur als Warnung geloggt - die .tex-Datei wird trotzdem
    erstellt und kann später manuell kompiliert werden, z.B. mit:
        pdflatex -output-directory output output/bericht.tex

    Parameter:
        track (GPSTrack): das auszuwertende Track-Objekt
        tex_pfad (str): Zielpfad der .tex-Datei
        karte_pfad (str): Zielpfad des Karten-Screenshots (PNG), wird
            automatisch per track.karte_erstellen_geopandas() erzeugt
        titel (str): Titel des Berichts
        pdf_erstellen (bool): ob zusätzlich automatisch ein PDF per
            pdflatex erzeugt werden soll (Standard: True)

    Rückgabe:
        str: der erzeugte LaTeX-Quelltext (zusätzlich unter tex_pfad gespeichert)
    """
    # Orte automatisch nachholen, falls noch nicht vorhanden.
    # getattr(track, "orte", None) fragt sicher nach dem Attribut "orte":
    # existiert es (weil orte_ermitteln() schon lief), wird es zurückgegeben;
    # existiert es nicht, gibt es None zurück statt einen Fehler zu werfen.
    orte = getattr(track, "orte", None)
    if orte is None or len(orte) == 0:
        logger.info("Keine Orte vorhanden - rufe orte_ermitteln() automatisch auf.")
        orte = track.orte_ermitteln()

    # Kartenscreenshot erzeugen (GeoPandas + contextily -> PNG mit echtem
    # OpenStreetMap-Kartenhintergrund, sofern Internetzugriff möglich ist)
    track.karte_erstellen_geopandas(ausgabepfad=karte_pfad)

    # --- Abschnitt 1: Kennzahlen als LaTeX-Tabellenzeilen -----------------
    kennzahlen_zeilen = [
        ("Gesamtstrecke", f"{track.gesamtstrecke_km():.2f} km"),
        ("Gesamtzeit", f"{track.gesamtzeit_s() / 60:.1f} min"),
        ("Durchschnittsgeschwindigkeit", f"{track.durchschnittsgeschwindigkeit_kmh():.1f} km/h"),
        ("Höhenmeter Anstieg", f"{track.hoehenmeter_anstieg():.0f} m"),
        ("Höhenmeter Abstieg", f"{track.hoehenmeter_abstieg():.0f} m"),
    ]
    kennzahlen_tex = "\n".join(
        f"{_latex_escape(name)} & {_latex_escape(wert)} \\\\"
        for name, wert in kennzahlen_zeilen
    )

    # --- Abschnitt 2: Orte als LaTeX-Tabellenzeilen -----------------------
    # Die Adresse steht in einer p{}-Spalte (statt der normalen l-Spalte),
    # damit LANGE Adressen automatisch umbrechen, statt über den Seitenrand
    # hinauszulaufen und abgeschnitten zu werden (das Problem bei verbatim).
    orte_zeilen = "\n".join(
        f"{int(zeile['index'])} & {_latex_escape(zeile['adresse']) or '--'} \\\\"
        for _, zeile in orte.iterrows()
    )

    # --- LaTeX-Quelltext zusammensetzen ------------------------------------
    # Kennzahlen und Orte landen jetzt wieder in echten LaTeX-Tabellen
    # (\begin{tabular}) statt in \begin{verbatim}. Die Orte-Tabelle nutzt
    # eine p{11cm}-Spalte (statt der normalen l-Spalte) für die Adresse -
    # p{} lässt LaTeX lange Texte automatisch als Absatz umbrechen, l lässt
    # sie einfach über den Seitenrand hinauslaufen. Da wir jetzt wieder
    # echten LaTeX-Code (statt verbatim-Text) einfügen, muss jeder Wert
    # zuerst durch _latex_escape() laufen, damit Sonderzeichen (&, %, ...)
    # in Adressen den Bericht nicht zum Absturz bringen.
    #
    # tex_quelltext ist eine Vorlage (Template) mit vier Platzhaltern "%s".
    # Das "r" vor dem String sorgt dafür, dass Backslashes (z.B. \section,
    # \\) wörtlich übernommen werden und nicht als Python-Sonderzeichen
    # interpretiert werden - wichtig, da fast jeder LaTeX-Befehl mit einem
    # Backslash beginnt.
    tex_quelltext = r"""\documentclass[a4paper,11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage[margin=2.5cm]{geometry}

\title{%s}
\author{Automatisch erzeugt}
\date{\today}

\begin{document}
\maketitle

\section{Kennzahlen}
\begin{tabular}{ll}
\toprule
Kennzahl & Wert \\
\midrule
%s
\bottomrule
\end{tabular}

\section{Orte entlang der Strecke}
\begin{tabular}{@{}r p{11cm}@{}}
\toprule
Index & Adresse \\
\midrule
%s
\bottomrule
\end{tabular}

\section{Kartenübersicht}
\begin{figure}[h!]
\centering
\includegraphics[width=\textwidth]{%s}
\caption{Streckenverlauf}
\end{figure}

\end{document}
""" % (
        # Die vier Werte hier werden der Reihe nach in die vier "%s" oben
        # eingesetzt (1. Titel, 2. Kennzahlen, 3. Orte, 4. Bildname).
        _latex_escape(titel),
        kennzahlen_tex,
        orte_zeilen,
        # \includegraphics erwartet nur den Dateinamen (nicht den ganzen
        # Pfad), da das Bild im selben Ordner wie die .tex-Datei liegt.
        os.path.basename(karte_pfad),
    )

    # Zielordner der .tex-Datei anlegen, falls er noch nicht existiert
    # (z.B. "output"). exist_ok=True verhindert einen Fehler, falls der
    # Ordner schon vorhanden ist.
    verzeichnis = os.path.dirname(tex_pfad)
    if verzeichnis:
        os.makedirs(verzeichnis, exist_ok=True)

    # "w" überschreibt eine evtl. vorhandene alte Version der Datei - der
    # Bericht wird also bei jedem Aufruf komplett neu geschrieben.
    # encoding="utf-8" sorgt dafür, dass Umlaute (ä, ö, ü) korrekt gespeichert werden.
    with open(tex_pfad, "w", encoding="utf-8") as datei:
        datei.write(tex_quelltext)

    logger.info(f"LaTeX-Bericht gespeichert unter: {tex_pfad}")

    # PDF automatisch erstellen, falls gewünscht (Standard: ja)
    if pdf_erstellen:
        _pdf_kompilieren(tex_pfad)

    # Quelltext zusätzlich zurückgeben, falls er direkt weiterverarbeitet
    # oder z.B. in der Konsole angezeigt werden soll.
    return tex_quelltext
