# Datenschutz im CRM

Einstellungen, Datenschutz (`/einstellungen/datenschutz`). Lesen mit dem Recht privacy:read, Pflege mit privacy:manage, Freigabe mit privacy:approve.

## Löschprofile

Je Datenart (Kontakte, Portalzugänge, Kommunikation, Tickets, sonstige Daten) werden Frist in Monaten und Fristbeginn gepflegt. Ein Profil gilt erst nach Freigabe durch eine berechtigte Person. Jede Änderung setzt die Freigabe zurück. Ohne freigegebenes Profil bleibt jede Löschung gesperrt. Die Fristen sind Entwürfe des Betreibers und vor dem produktiven Einsatz rechtlich zu prüfen.

## Löschanträge

Antrag mit Kontakt, Eingangsdatum und Anlass erfassen. Die Sperrprüfung nennt jede Sperre im Klartext (Löschprofil, Aufbewahrungsfrist, Verknüpfungen, Dokumentfristen). Freigabe, Ablehnung und Anonymisierung erfolgen durch eine zweite Person. Die Anonymisierung ist nicht umkehrbar, gebuchte Inhalte bleiben unberührt. Ob ein gesperrter Antrag mit einer Einschränkung der Verarbeitung beantwortet wird, ist mit einer Rechtsanwältin oder einem Rechtsanwalt zu klären. Die Antwortfrist ist zu prüfen.

## Register und Verzeichnis

Das Register führt Auftragsverarbeiter, Unterauftragsverarbeiter, Verarbeitungstätigkeiten und Verantwortlichkeiten mit AVV-Status. Mit Entwurf erzeugen wird das Verzeichnis von Verarbeitungstätigkeiten aus dem Register gebildet und kann als Markdown-Datei heruntergeladen werden. Der Entwurf ist kein geprüftes Dokument.

## DSGVO-Auskunft mit Prüfschritt

Im Kontakt öffnet die Schaltfläche „DSGVO-Auskunft“ den Bereich „DSGVO-Auskunft mit Prüfschritt“. Eine Person bereitet die Auskunft vor. Eine zweite Person sieht die Vorschau, markiert sie als geprüft und gibt sie zur Herausgabe frei. Erst danach ist der Download möglich; jeder Schritt und jeder Download wird protokolliert. Haben sich die Daten nach der Vorbereitung geändert, ist die Auskunft neu vorzubereiten. Die Auskunft enthält keine Hashwerte, Tokens, internen Vermerke oder KI-Rohdaten; andere Personen erscheinen nur mit ihrer Rolle. Ob zurückgehaltene Angaben doch herauszugeben sind, ist rechtlich zu prüfen (AC07-01).

## Löschcheckliste

Unter Dokumente, Löschvorschläge zeigt „Löschcheckliste“ bei jedem gelöschten Dokument den Stand je Ziel: Index und Volltext, Original, Paperless, Google Drive, Embeddings, KI-Auszüge, Vorschaubilder und Backups. Offene Ziele bearbeitet der tägliche Nachlauf; mit „Nachlauf starten“ lässt er sich sofort auslösen. Backups werden nicht bearbeitet, gelöschte Daten verschwinden dort erst mit Ablauf der Backupfrist. Ein nach einer Wiederherstellung gesperrtes Dokument bleibt erhalten.
