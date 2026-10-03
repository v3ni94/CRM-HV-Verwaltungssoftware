# Datenschutz im CRM

Einstellungen, Datenschutz (`/einstellungen/datenschutz`). Lesen mit dem Recht privacy:read, Pflege mit privacy:manage, Freigabe mit privacy:approve.

## Löschprofile

Je Datenart (Kontakte, Portalzugänge, Kommunikation, Tickets, sonstige Daten) werden Frist in Monaten und Fristbeginn gepflegt. Ein Profil gilt erst nach Freigabe durch eine berechtigte Person. Jede Änderung setzt die Freigabe zurück. Ohne freigegebenes Profil bleibt jede Löschung gesperrt. Die Fristen sind Entwürfe des Betreibers und vor dem produktiven Einsatz rechtlich zu prüfen.

## Löschanträge

Antrag mit Kontakt, Eingangsdatum und Anlass erfassen. Die Sperrprüfung nennt jede Sperre im Klartext (Löschprofil, Aufbewahrungsfrist, Verknüpfungen, Dokumentfristen). Freigabe, Ablehnung und Anonymisierung erfolgen durch eine zweite Person. Die Anonymisierung ist nicht umkehrbar, gebuchte Inhalte bleiben unberührt. Ob ein gesperrter Antrag mit einer Einschränkung der Verarbeitung beantwortet wird, ist mit einer Rechtsanwältin oder einem Rechtsanwalt zu klären. Die Antwortfrist ist zu prüfen.

## Register und Verzeichnis

Das Register führt Auftragsverarbeiter, Unterauftragsverarbeiter, Verarbeitungstätigkeiten und Verantwortlichkeiten mit AVV-Status. Mit Entwurf erzeugen wird das Verzeichnis von Verarbeitungstätigkeiten aus dem Register gebildet und kann als Markdown-Datei heruntergeladen werden. Der Entwurf ist kein geprüftes Dokument.

## Dienstleister laut Konfiguration und Pflegefelder

Der Bereich „Dienstleister laut Konfiguration“ zeigt, welche externen Dienste die Einstellungen und Konnektoren tatsächlich nutzen, zum Beispiel Gmail, Google Drive, Paperless, finAPI, KI-Anbieter oder LetterXpress, mit Zustand (aktiv oder nur konfiguriert), Herkunft (Mandant oder Plattform) und der Angabe, ob ein Registereintrag besteht. Angezeigt werden nur technische Angaben wie Host und Modus. Mit „Erkannte Dienste ins Register übernehmen“ werden fehlende Dienste als Unterauftragnehmer angelegt; nicht aktive Dienste nur mit dem Haken darüber. Neue Einträge starten mit AVV kein Nachweis, Drittland offen und rechtlicher Prüfung offen. Bereits gepflegte Angaben bleiben bei jeder weiteren Übernahme unverändert.

Mit „Bearbeiten“ in der Registertabelle werden die Pflegefelder eines Eintrags erfasst. Bei einer Verarbeitungstätigkeit sind das die Rolle von GdWE, Verwalter und Betreiber der Plattform (offen, Verantwortlicher, gemeinsam Verantwortlicher, Auftragsverarbeiter, nicht beteiligt), die Rechtsgrundlage als Freitext, die eingesetzten Auftragsverarbeiter, Datenkategorien, Empfänger und Löschfristen. Bei Dienstleistern sind es AVV-Status und Drittlandübermittlung (offen, nein, ja mit Ländern und Garantien). Die Plattform schlägt keine Rolle und keine Rechtsgrundlage vor; die Einträge sind vor der Verwendung rechtlich zu prüfen.

„PDF-Entwurf herunterladen“ erzeugt das Verzeichnis als PDF mit denselben Inhalten wie der Markdown-Entwurf, einschließlich der Liste offener Punkte und der Dienste, die laut Konfiguration genutzt werden, aber noch keinen Registereintrag haben.

## DSGVO-Auskunft mit Prüfschritt

Im Kontakt öffnet die Schaltfläche „DSGVO-Auskunft“ den Bereich „DSGVO-Auskunft mit Prüfschritt“. Eine Person bereitet die Auskunft vor. Eine zweite Person sieht die Vorschau, markiert sie als geprüft und gibt sie zur Herausgabe frei. Erst danach ist der Download möglich; jeder Schritt und jeder Download wird protokolliert. Haben sich die Daten nach der Vorbereitung geändert, ist die Auskunft neu vorzubereiten. Die Auskunft enthält keine Hashwerte, Tokens, internen Vermerke oder KI-Rohdaten; andere Personen erscheinen standardmäßig nur mit ihrer Rolle. Ob zurückgehaltene Angaben doch herauszugeben sind, ist rechtlich zu prüfen (AC07-01); bis zur Entscheidung bleibt der Standard.

## Löschcheckliste

Unter Dokumente, Löschvorschläge zeigt „Löschcheckliste“ bei jedem gelöschten Dokument den Stand je Ziel: Index und Volltext, Original, Paperless, Google Drive, Embeddings, KI-Auszüge, Vorschaubilder und Backups. Offene Ziele bearbeitet der tägliche Nachlauf; mit „Nachlauf starten“ lässt er sich sofort auslösen. Backups werden nicht bearbeitet, gelöschte Daten verschwinden dort erst mit Ablauf der Backupfrist. Ein nach einer Wiederherstellung gesperrtes Dokument bleibt erhalten.

## Umfang der Auskunft einstellen

Unter Einstellungen, Datenschutz legt der Bereich „Umfang der DSGVO-Auskunft“ zwei Schalter je Mandant fest. „Angaben zu anderen Personen“ steht standardmäßig auf „nur mit Rolle“; die Stufe „mit Name und Rolle“ nennt zusätzlich den Namen von Beziehungen, weiteren Parteimitgliedern und einem abweichenden Kontoinhaber, nie Anschrift, Kontaktdaten, Kennungen oder Bankdaten. „Interne Vermerke aufnehmen“ ist standardmäßig aus; eingeschaltet erscheinen Notizfeld und Kontaktnotizen ohne Verfasser. Der Umfang wird beim Vorbereiten einer Auskunft festgehalten und gilt bis zur Freigabe unverändert, auch wenn der Schalter inzwischen geändert wurde. Die Einstellung ändert die Prüfung durch eine zweite Person nicht. Welcher Umfang zulässig ist, klärt die Rechtsberatung (AC07-01).

## Papierkorb für Dokumente

Der Papierkorb ist standardmäßig aus; eine zulässige Löschung bleibt dann endgültig. Unter Einstellungen, Aufbewahrung schaltet „Papierkorb für Dokumente“ ihn ein und legt die Frist fest (Vorschlag 30 Tage, keine Rechtsfrist; ob personenbezogene Daten so lange im Papierkorb bleiben dürfen, ist offen, AE33-01). Mit eingeschaltetem Papierkorb legt jede zulässige Löschung (einzeln oder durch einen Löschvorschlag) das Dokument unter Dokumente, Papierkorb ab. Dort stehen Löschzeitpunkt, frühestes Datum der endgültigen Löschung und der Grund einer Sperre.

„Wiederherstellen“ holt das Dokument mit Begründung zurück; „Endgültig löschen“ löscht vor Fristende mit Begründung. Beides wird protokolliert. Ein täglicher Auftrag löscht nach Fristende endgültig, prüft dabei Aufbewahrungsfrist und alle Sperren erneut und lässt gesperrte Dokumente im Papierkorb (Status „gesperrt“). Eine Sperre am Dokument selbst setzt man nach der Wiederherstellung. Die Löschcheckliste zeigt ein Dokument im Papierkorb als „im Papierkorb“; die übrigen Ziele folgen mit der endgültigen Löschung. Backups werden vom Papierkorb nicht berührt.

## Erkannte Dienstleister (Stand 02.10.2026)

Das Verzeichnis erkennt zusätzlich das Schadenstool, Makler-CRM-Anbieter, Webhook-Ziele und
EBICS- oder FinTS-Bankzugänge aus der Konfiguration. Je Dienst wird lesend angezeigt, welche
Rechtsgrundlage für die betroffenen Einwilligungszwecke gilt (Register Rechtsgrundlagen der
Einwilligung). Ob ein Dienst Auftragsverarbeiter ist, tragen Sie im Registereintrag ein.

## Löschvorschläge

Unter Datenschutz, Löschprofile lässt sich je Datenart der Schalter "Löschvorschläge erzeugen" setzen. Er wirkt erst, wenn das Profil von einer zweiten Person freigegeben ist. Das System löscht nichts selbst: Für Kontakte mit abgelaufenem Löschdatum entsteht jede Nacht ein Löschantrag im Status "Vorschlag". Eine Person übernimmt den Vorschlag als Antrag, eine zweite Person gibt ihn frei. Für Kommunikation, Tickets, Portalzugänge und das Ereignisprotokoll zeigt die Übersicht nur die Anzahl der Einträge, die älter als die Frist sind. Die Löschfristen selbst sind noch nicht entschieden (V17).

## Datenschutzübersicht (Stand 02.10.2026)

Unter Einstellungen, Datenschutz zeigt die Datenschutzübersicht die Einwilligungen aller Kontakte je Zweck (aktiv, widerrufen, Widersprüche, ohne Nachweisdokument). Im Bereich Fristen tragen Personen mit Freigaberecht die Antwortfristen für Auskunft und Löschung sowie eine Vorfrist in Tagen ein. Die Fristen haben bewusst keinen Standardwert; ohne Eintrag erscheinen offene Löschanträge ohne Fälligkeit. Die Vor-G1-Auswertung listet aktiv genutzte Dienste ohne Registereintrag und Einträge mit offenem AVV, Drittland oder rechtlicher Prüfung; sie öffnet kein Gate.

Im Abschnitt Einwilligungsregeln wird festgelegt, ob E-Mail-Zustellung und Datenweitergabe nur mit Einwilligung (Standard) oder auch auf Vertragsgrundlage zulässig sind. Die Änderung ist eine Rechtsentscheidung und wird protokolliert.

Im Abschnitt Umfang der DSGVO-Auskunft lassen sich Vorgänge, Nachrichten und Dokumentbezüge des Kontakts zuschalten. Ausgeschaltet erscheinen sie in der Auskunft nur als Anzahl.

## Auskunftsanträge erfassen und überwachen

Unter Einstellungen, Datenschutz, Auskunftsanträge erfassen Sie den Eingang eines Auskunftsantrags: Kontakt suchen, Eingangsdatum und Eingangsweg wählen, Antrag erfassen. Über die Schaltflächen der Zeile setzen Sie den Status (In Bearbeitung, Beantwortet, Abgelehnt, Zurückgenommen). Eine Frist wird nur angezeigt, wenn unter Fristen für Datenschutzanträge eine Auskunftsfrist hinterlegt ist; dann erscheint der Antrag auch in der Fristenliste. Die Daten sind eine Orientierung und zu prüfen. Die Auskunft selbst bereiten Sie am Kontakt über den Auskunftsexport vor. Unter Umfang der DSGVO-Auskunft können Portalkonto mit Anmeldungen, Zahlungsdaten und Vertragsdaten zugeschaltet werden (Standard aus, Rechtsfrage AC07-01).
