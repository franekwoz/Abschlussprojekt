"""
motor.py
--------
Eigene Motor-Klasse, wie im UML-Klassendiagramm aus Kapitel 09.5 vorgegeben
(EBikeSimulator --> Motor, per Assoziation, nicht Vererbung - der
Simulator "hat ein" Motor-Objekt).

WICHTIG - Abweichung vom Kurs-Vorbild:
Im Kurs berechnet Motor.get_current_draw(power, voltage) den Strom über
P = V * I * eta, also aus Leistung, Spannung und Wirkungsgrad.
Das Abschlussprojekt verlangt hingegen ausdrücklich die Berechnung des
Motorstroms über eine gegebene MOTORKONSTANTE (I = T / km, mit Drehmoment T
in Nm und Motorkonstante km in Nm/A). Da die Abschlussprojekt-Anforderung
Priorität hat, wird hier diese Variante umgesetzt - die Klasse behält aber
bewusst dieselbe strukturelle Rolle (eigenständige, per Assoziation
eingebundene Klasse) wie im Kurs-Vorbild.
"""


class Motor:
    """
    Modelliert den Antriebsmotor über seine Motorkonstante.

    Attribute:
        km (float): Motorkonstante in Nm/A (Verhältnis Drehmoment/Strom)
    """

    def __init__(self, motorkonstante_Nm_A: float = 1.5):
        if motorkonstante_Nm_A <= 0:
            raise ValueError("motorkonstante_Nm_A muss > 0 sein.")
        self.km = motorkonstante_Nm_A

    def get_current_draw(self, torque_Nm: float) -> float:
        """Berechnet den vom Motor benötigten Strom aus dem Antriebsdrehmoment: I = T / km"""
        return torque_Nm / self.km

    def __str__(self) -> str:
        return f"Motor(km={self.km:.2f} Nm/A)"
