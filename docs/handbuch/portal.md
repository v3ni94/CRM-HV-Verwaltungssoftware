# Portal

## Zweck

Das Portal (eigene Anwendung unter der Portal-Adresse des Mandanten) gibt Mietern,
Eigentümern und Dienstleistern einen eigenen, rollenabhängigen Zugang zu ihren Daten. Alle
Angaben mit Geld- oder Vertragsbezug sind Vorschläge und werden von der Verwaltung
geprüft; nichts wird automatisch übernommen (Hinweis im Portal: Vorschlag, wird von der
Verwaltung geprüft).

## Mieter und Eigentümer

Nach der Anmeldung (mit zweitem Faktor bei jeder Anmeldung, vertrauenswürdige Geräte gibt
es im Portal bewusst nicht) zeigt die Übersicht rollenabhängige Kacheln:

- Dokumente einsehen und herunterladen
- Meldungen: Schäden und Anliegen mit Verlauf, Foto und Kommentar melden
- Kontoauszug ansehen
- Zählerstand melden (als Vorschlag)
- Datenänderung: Stammdaten ändern lassen (als Vorschlag)
- Übergabeprotokolle, sofern für den Beteiligten freigegeben

## Dienstleister

Dienstleister sehen unter Aufträge ihre zugewiesenen Vorgänge mit Ablehnen, Angebot mit
Anhang, Termin nach Zusage der Verwaltung, Ausführungsbericht und Rechnungseinreichung.
Eine eingereichte Rechnung ist ein Vorschlag und durchläuft den Rechnungseingang wie jede
andere Eingangsrechnung (siehe Kapitel Belegeingang).

## Mitarbeiterzugang

Jede Mitarbeiterin und jeder Mitarbeiter erhält zusätzlich einen eigenen Portalzugang für
den gesamten Mandanten, um Vorgänge aus Sicht des Portals nachvollziehen zu können.

## Portalrechte je Rolle

Unter Einstellungen, Rollen und Rechte legt die Matrix Portalrechte je Rolle fest, welche
Portalfunktionen der Mitarbeiterzugang je CRM-Systemrolle im Portal sieht. Die Rollen
Portalnutzer, Nur-Lesezugriff, Steuerberater und Versicherungsmakler erhalten grundsätzlich
keinen Portalzugang. Änderungen an der Matrix verlangen das Recht Mandanteneinstellungen
ändern; Übernehmen auf bestehende Zugänge wendet eine geänderte Matrix nachträglich auf
bereits angelegte Portalzugänge an.

## Was ist Vorschlag, was verbindlich

Jede Eingabe im Portal mit Geld- oder Vertragsbezug (Zählerstand, Datenänderung,
Angebot, Rechnung) ist ein Vorschlag. Verbindlich wird sie erst, wenn die Verwaltung sie
im CRM prüft und übernimmt.

## Häufige Fehler

- **Portalfunktion fehlt für eine Rolle**: Die Portalrechte-Matrix schaltet die Funktion
  für diese Rolle nicht frei; unter Einstellungen, Rollen und Rechte ergänzen und
  Übernehmen auf bestehende Zugänge ausführen.
- **Kein Portalzugang trotz Mitarbeiterrolle**: Die Rolle gehört zu den ausgenommenen
  Rollen (Portalnutzer, Nur-Lesezugriff, Steuerberater, Versicherungsmakler); diese
  erhalten grundsätzlich keinen Portalzugang.
- **Zweiter Faktor bei jeder Anmeldung**: Das Portal kennt keine vertrauenswürdigen
  Geräte; anders als im CRM ist der zweite Faktor bei jeder Anmeldung erneut einzugeben.
