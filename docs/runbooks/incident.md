# Runbook: Vorfall (Sicherheitsvorfall, Datenpanne, Ausfall)

Quelle: MASTER-PROMPT Abschnitt 17 (Repository-Struktur, `runbooks/`), Regel 14 und 15 (Datenschutz,
Rechtsfristen, Beweise). Dieses Runbook beschreibt den Ablauf, es ist keine Rechtsberatung. Rechtliche
Einordnungen und Fristen sind Einschätzungen und sind vom Rechtsanwalt bzw. Datenschutzbeauftragten zu
verifizieren. Zuständigkeit für Entscheidungen: Betreiber (Timo Müller), bei Mandantendaten die
Geschäftsführung des betroffenen Mandanten. Ergänzend: `monitoring.md` (Alarme), `backup.md`
(Wiederherstellung), `server-recovery-und-haertung.md` (Server), `schluesselrotation.md`.

## 1. Vorfallklassen

| Klasse | Beispiele | Erste Reaktion |
| --- | --- | --- |
| A Datenschutz oder Sicherheit | unbefugter Zugriff, Verlust oder Offenlegung personenbezogener Daten, Schadsoftware, gestohlenes Gerät oder Schlüssel, falsch versandte Dokumente | sofort eindämmen, Beweise sichern, Datenschutzbeauftragten informieren |
| B Verfügbarkeit | Plattform oder Bankabruf nicht erreichbar, Datenbank defekt, Speicher voll | Ursache eingrenzen, Wiederherstellung nach `backup.md` oder `server-recovery-und-haertung.md` |
| C Fachliche Integrität | falsche Buchungen, doppelte Läufe, falsche Beträge oder Empfänger, fehlerhafte Importe | betroffene Funktion sperren (Gate, Feature Flag, Jobschalter), nichts überschreiben, Korrektur nur per Storno (Regel 7) |

Ein Vorfall kann mehreren Klassen angehören. Im Zweifel gilt die strengere Klasse.

## 2. Erkennung

- Alarme aus Uptime Kuma und Beszel (`monitoring.md`), Warnmeldungen des Systems, Auffälligkeiten im Audit Log und in den Jobprotokollen.
- Meldungen von Mitarbeitern, Eigentümern, Mietern, Dienstleistern oder Banken.
- Jede Person, die einen Vorfall vermutet, meldet ihn unverzüglich an den Betreiber (E-Mail an die Betreiberadresse, bei Dringlichkeit telefonisch). Eine Meldung ohne Gewissheit ist erwünscht.
- Zeitpunkt der Kenntnisnahme sofort festhalten (Datum, Uhrzeit, Meldender). Dieser Zeitpunkt ist für spätere Fristen maßgeblich und zu dokumentieren.

## 3. Sofortmaßnahmen (Eindämmung)

1. Vorfallprotokoll anlegen (Abschnitt 8) und Verantwortlichen benennen.
2. Betroffene Zugänge sperren: Benutzer deaktivieren, Sitzungen beenden, Passwörter und Tokens zurücksetzen, API Schlüssel und Integrationszugänge widerrufen (`schluesselrotation.md`).
3. Bei Verdacht auf Kompromittierung eines Servers: Zugang nur über Schlüsselanmeldung, verdächtige Prozesse und Container nicht löschen, sondern anhalten, damit Beweise erhalten bleiben.
4. Fachliche Folgen begrenzen: Zahlungsfreigaben, Bankabruf, Läufe und Automatisierung des Mandanten anhalten (Jobschalter unter Einstellungen, Automatisierung; Gates bleiben geschlossen oder werden geschlossen). Das Abschalten öffnet keine Sperre.
5. Keine Daten löschen und keine Buchungen ändern. Korrekturen später per Storno.

## 4. Beweissicherung

- Protokolle (Anwendung, Traefik, Datenbank, Audit Log) und betroffene Konfigurationen sichern, bevor Container neu gestartet oder Logs rotiert werden.
- Datenbankstand und Objektspeicher über eine zusätzliche Sicherung festhalten (`backup.md`), Prüfsumme (SHA 256) der gesicherten Dateien notieren.
- Screenshots und E-Mails im Original (mit Kopfzeilen) ablegen. Zugriff nur für den Vorfallkreis.
- Jede Maßnahme mit Datum, Uhrzeit, ausführender Person und Ergebnis protokollieren. Keine Beweise auf dem betroffenen System allein belassen.

## 5. Bewertung und Meldepflichten

Gemeinsam mit dem Datenschutzbeauftragten und dem Rechtsanwalt zu klären, sofort nach Eindämmung:

- Sind personenbezogene Daten betroffen, welche Kategorien, wie viele Personen, welche Mandanten und Gesellschaften (Müller Holding AG, Hausverwaltung Müller GmbH, Timo Müller Einzelunternehmen, Eigentümergemeinschaften)? Wer ist Verantwortlicher, wer Auftragsverarbeiter? Bei Verwaltungsdaten von WEG und Mietern handelt die Hausverwaltung regelmäßig im Auftrag oder als Verantwortlicher, das ist im Einzelfall zu klären.
- Meldung an die Aufsichtsbehörde: Nach der DSGVO besteht bei einer Verletzung des Schutzes personenbezogener Daten mit Risiko für Betroffene eine Meldepflicht, nach Einschätzung binnen 72 Stunden nach Kenntnis (Art. 33 DSGVO). Frist und Anwendbarkeit sind zu verifizieren und nicht allein auf Basis dieses Runbooks zu berechnen. Eintrag mit Vorfrist in den Fristenkalender (`kalender-fristen.md`).
- Benachrichtigung der Betroffenen bei voraussichtlich hohem Risiko (Art. 34 DSGVO): Inhalt und Zeitpunkt mit dem Datenschutzbeauftragten abstimmen.
- Weitere mögliche Pflichten (vertragliche Meldepflichten gegenüber Eigentümergemeinschaften, Banken oder Zahlungsdienstleistern, Versicherungen, Strafanzeige, Meldung an Behörden): mit dem Rechtsanwalt prüfen. Fristen aus Verträgen den Unterlagen entnehmen, nicht schätzen.
- Anerkenntnisse, Zusagen und Erklärungen gegenüber Dritten gibt nur die Geschäftsführung ab (Freigabe erforderlich).

## 6. Wiederherstellung

1. Ursache beheben (Schwachstelle schließen, Zugänge erneuern, betroffene Systeme neu aufsetzen nach `server-recovery-und-haertung.md`).
2. Daten aus verifizierter Sicherung wiederherstellen (`backup.md`, Restore Test), Stand und Datenverlustfenster dokumentieren.
3. Fachliche Prüfung vor Wiederaufnahme: Salden und offene Posten gegen Bankstände abstimmen, doppelte oder fehlende Läufe prüfen, Kontrolllisten der Gates prüfen. Wiederaufnahme der Läufe und des Bankabrufs erst nach Freigabe durch den Betreiber.
4. Erhöhte Überwachung für mindestens zwei Wochen (Alarme, Audit Log).

## 7. Kommunikation

| Adressat | Wann | Wer | Inhalt |
| --- | --- | --- | --- |
| Intern (Betreiber, Mitarbeiter) | sofort | Betreiber | Lage, Verhaltensregeln, keine Spekulation |
| Datenschutzbeauftragter, Rechtsanwalt | sofort bei Klasse A | Betreiber | Sachverhalt, Zeitpunkt der Kenntnis, Protokoll |
| Aufsichtsbehörde | nach Bewertung, innerhalb der verifizierten Frist | Datenschutzbeauftragter mit Geschäftsführung | Meldung nach Vorgabe der Behörde |
| Betroffene, Eigentümer, Mieter | nach Bewertung | Geschäftsführung | sachlich, was passiert ist, welche Daten, was zu tun ist, Ansprechpartner |
| Banken, Dienstleister | bei Bezug zu deren Zugängen | Betreiber | betroffene Zugänge, Sperrung, Neuausgabe |

Alle externen Schreiben nur als Entwurf, Versand nach Freigabe der Geschäftsführung. Keine Gedankenstriche, sachliche Sprache, keine Schuldzuweisung vor Abschluss der Untersuchung.

## 8. Vorfallprotokoll (Vorlage)

| Feld | Inhalt |
| --- | --- |
| Vorfall Nr. | JJJJ-NN |
| Klasse | A, B oder C |
| Kenntnis am (TT.MM.JJJJ, Uhrzeit) | |
| Gemeldet von | |
| Betroffene Systeme, Mandanten, Gesellschaften | |
| Betroffene Daten und Personenkreis (Schätzung) | |
| Sofortmaßnahmen mit Zeitpunkt | |
| Beweise gesichert (Ort, Prüfsumme) | |
| Bewertung Datenschutzbeauftragter, Rechtsanwalt (Datum) | |
| Meldung Aufsichtsbehörde (Frist zu verifizieren, Datum der Meldung) | |
| Benachrichtigung Betroffene | |
| Ursache | |
| Wiederherstellung und Freigabe zur Wiederaufnahme (Datum, wer) | |
| Maßnahmen zur Vermeidung, Termin | |

Das Protokoll wird in der Dokumentenablage des Betreibers geführt und nicht rückwirkend geändert, Ergänzungen mit Datum.

## 9. Nachbereitung

- Nachbesprechung innerhalb von zwei Wochen, Ergebnis im Protokoll.
- Maßnahmen in `docs/OPEN_QUESTIONS.md` oder im Maßnahmenplan mit Eigentümer und Termin erfassen.
- Runbook, Alarme und Tests anpassen, wenn der Ablauf Lücken zeigte.
- Jährliche Übung (Tabletop) mit Betreiber und Datenschutzbeauftragtem, Ergebnis dokumentieren.

## Offene Punkte

- Benennung der Ansprechpartner (Datenschutzbeauftragter, Rechtsanwalt, Telefonnummern) im Betreiberhandbuch, nicht im Repository: `docs/OPEN_QUESTIONS.md` AA15-02.
- Rechtliche Prüfung dieses Ablaufs und der Fristen durch Rechtsanwalt bzw. Datenschutzbeauftragten vor produktiver Nutzung.
