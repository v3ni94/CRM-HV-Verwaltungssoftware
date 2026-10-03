# Löschkonzept der Plattform MH Verwaltungsplattform (Entwurf)

Stand: 02.10.2026. Status: Entwurf zur Prüfung durch Betreiber, Datenschutz und Rechtsanwalt. Dieses Dokument ist keine
Rechtsberatung und keine freigegebene Rechtsgrundlage. Es bündelt die bisher verstreuten Angaben aus
`docs/handbuch/datenschutz.md`, `docs/rules/S16-P17-privacy.md`, `docs/rules/M6-04-aufbewahrungsprofile.md`,
`docs/rules/U11-retention-sperren.md`, `docs/rules/AC07-auskunft-loeschung.md`, `docs/runbooks/backup.md` und
MASTER-PROMPT 7.11 (S04 bis S06). Es dient auch dem Nachweis der Rechenschaftspflicht (Art. 5 Abs. 2 DSGVO).

## 1. Grundsätze

1. Keine Rechtsfrist wird in diesem Dokument behauptet. Jede Frist, die nicht aus einer freigegebenen Quelle
   des Quellenregisters (Anhang C) stammt, steht als Platzhalter `[Frist offen, V17]`. Die Matrix zu V17 füllt der
   Betreiber mit Steuerberater und Rechtsanwalt aus (Vorlage: `docs/datenschutz/V17-MATRIXVORLAGE.md`).
2. Keine pauschale Zehnjahresfrist und keine pauschale Löschung: Aufbewahrung je Unterlagenklasse, Rechtsträger,
   Fristbeginn und Sperrgrund (MASTER-PROMPT 7.11 S04, S05).
3. Gebuchte Inhalte werden nie gelöscht oder überschrieben, Korrektur nur per Storno (7.1 B03). Löschung
   personenbezogener Daten erfolgt dort durch Anonymisierung des Personenbezugs, soweit eine Sperre die Löschung
   des Datensatzes verhindert.
4. Jede Löschung läuft über ein freigegebenes Profil, prüft Sperren und wird protokolliert. Ohne freigegebenes
   Profil bleibt die Löschung gesperrt. Es gibt keinen automatischen Löschlauf über das heute Umgesetzte hinaus
   (Betreiberentscheidung 26.09.2026).
5. Backups sind Betriebsabsicherung und kein Archiv. Gelöschte Daten verschwinden aus Backups erst mit Ablauf der
   Backup-Aufbewahrung. Die Behauptung einer Löschung in Backups wird nicht aufgestellt.
6. Löschfristen und Rechtsgrundlagen sind je Rechtsträger (Mandant, Gesellschaft, GdWE) getrennt zu bestimmen.

## 2. Übersicht je Datenkategorie

Spalten: Löschfrist und Rechtsgrundlage stehen bis zur Freigabe der V17-Matrix als Platzhalter. Der Stand der
Umsetzung beschreibt, was die Plattform heute technisch kann (Quelle jeweils genannt).

| Nr | Datenkategorie | Frist | Rechtsgrundlage der Verarbeitung und Aufbewahrung | Löschweg heute | Sperrgrund | Backup |
| --- | --- | --- | --- | --- | --- | --- |
| K1 | Kontakte (Personen, Anschriften, Telefon, E-Mail, Bankkonten) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Löschantrag je Kontakt mit Sperrprüfung und Vier-Augen-Freigabe, Anonymisierung (S16-P17). Kein Job, der das Löschprofil flächig anwendet (GAI-501) | Löschprofil nicht freigegeben, Aufbewahrungsprofil, Verknüpfung zu Verträgen, Buchungen, Dokumenten mit Frist | siehe Abschnitt 4 |
| K2 | Verträge, Vertragsparteien, Kautionen | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Kein Löschweg für Verträge, Anonymisierung nur der Person (K1) | laufende oder nicht abgerechnete Verträge, Abrechnungsfristen | siehe Abschnitt 4 |
| K3 | Buchhaltung, Buchungssätze, Belege, Abrechnungen | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Kein Löschweg, Korrektur nur per Storno (B03) | Aufbewahrungsprofil je Unterlagenklasse, offene Verfahren | siehe Abschnitt 4 |
| K4 | Dokumente (DMS, Objektspeicher, Spiegel Paperless und Google Drive) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Löschvorschlag mit Prüfung, optional Papierkorb (Standard aus), Löschcheckliste je Ziel, täglicher Nachlauf (M6-03, AC07, AE33) | Aufbewahrungsprofil, Löschsperre, Rechtsstreit, Beweissicherung | nicht bearbeitet, Ablauf der Backup-Dauer |
| K5 | Kommunikation (E-Mails, Zustellungen, Postausgang, Anhänge) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Profil vorhanden, kein Anwendungsjob (GAI-501) | Bezug zu Vorgang oder Beleg mit Frist | siehe Abschnitt 4 |
| K6 | Tickets, Kommentare, Aufträge | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Kommentare werden archiviert, nicht gelöscht; Profil ohne Anwendungsjob (GAI-501) | Bezug zu Vertrag, Schaden, Verfahren | siehe Abschnitt 4 |
| K7 | Portalzugänge (Mieter, Eigentümer, Beirat, Dienstleister) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Löschung des Zugangs löscht abhängige Protokollzeilen, zum Beispiel portal_chat_log (AE28-02); kein Anwendungsjob für das Profil | Bezug zu Vorgängen | siehe Abschnitt 4 |
| K8 | Sitzungen und Gerätemetadaten (Refresh-Token, vertrauenswürdige Geräte, Portal-Sitzungen mit User-Agent und IP) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Ablauf und Widerruf gesetzt, kein Bereinigungsjob (GAI-502, Umsetzung in Prüfung) | keine bekannte | siehe Abschnitt 4 |
| K9 | Audit-Protokoll und Domain-Ereignisse (inklusive Anmeldeereignisse mit IP) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Kein Bereinigungs- oder Anonymisierungspfad. Die Kontoanonymisierung lässt Ereignisse stehen (GAI-503) | Nachweisfunktion für Buchungen und Freigaben | siehe Abschnitt 4 |
| K10 | Plattformbenutzer (Mitarbeiter, Steuerberater) | [Frist offen, V17] | [Rechtsgrundlage offen, V17, Beschäftigtendatenschutz M20-08-Q7] | Kein Lösch- oder Anonymisierungspfad (GAI-504) | Nachweis in Protokollen, Freigaben | siehe Abschnitt 4 |
| K11 | KI-Protokolle (Fragenprotokoll des Portal-Assistenten, KI-Auszüge, Embeddings) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | portal_chat_log endet nur mit dem Portalzugang (AE28-02); Embeddings und Auszüge werden im Löschnachlauf der Dokumente behandelt (AC07) | Bezug zu Dokumenten mit Frist | siehe Abschnitt 4 |
| K12 | Bankdaten (Kontoumsätze, Importdateien, Mandate, Zustimmungen) | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Kein Löschweg für gebuchte Umsätze; Rohdaten laut Regel M11-07 | Buchungsbezug, Belegkette | siehe Abschnitt 4 |
| K13 | Exportarchive und Auskunftsdateien | [Frist offen, V17] | [Rechtsgrundlage offen, V17] | Aufbewahrung je Mandant einstellbar, Standard keine automatische Löschung (V04-01) | keine bekannte | siehe Abschnitt 4 |

## 3. Löschweg und Verantwortung

| Schritt | Beschreibung | Verantwortlich |
| --- | --- | --- |
| 1 | Anlass: Antrag nach Art. 17 DSGVO, Fristablauf eines freigegebenen Profils oder Austritt | Datenschutz, Sachbearbeitung |
| 2 | Sperrprüfung in der Plattform (Profil, Aufbewahrung, Verknüpfungen, Dokumentfristen) | Plattform, Sachbearbeitung |
| 3 | Freigabe oder Ablehnung durch eine zweite Person (Vier-Augen-Prinzip) | Freigebende Person mit Recht privacy:approve |
| 4 | Ausführung: Anonymisierung beziehungsweise Löschung je Ziel mit Protokoll | Plattform |
| 5 | Nachlauf für Spiegel und Ableitungen (Paperless, Google Drive, Embeddings, KI-Auszüge) | Plattform, täglicher Auftrag |
| 6 | Nachweis: Protokoll, Löschcheckliste, Eintrag in der Löschcheckliste des Verzeichnisses | Datenschutz |

Die Frist zur Beantwortung eines Antrags berechnet die Plattform nicht. Sie ist zu verifizieren: [Frist offen, V17].

## 4. Backups

Das Runbook `docs/runbooks/backup.md` beschreibt: Offsite 14 tägliche, 8 wöchentliche und 12 monatliche Stände,
MASTER-PROMPT 6.9.5 nennt 30 Tage rollierend. Die Dauer für personenbezogene Daten in Backups ist offen
(OPEN_QUESTIONS AC07-03): [Frist offen, V17]. Nach einer Wiederherstellung verhindert das Löschjournal mit
Probelauf und Replay, dass bereits gelöschte Dokumente wieder auftauchen (backup.md).

## 5. Lücken und Folgearbeiten

| Befund | Lücke | Status |
| --- | --- | --- |
| GAI-501 | Kein Job wendet Löschprofile je Datenart an (Kommunikation, Tickets, Portalzugänge) | offen, hängt an V17 |
| GAI-502 | Bereinigung abgelaufener Sitzungen | offen, technisch, keine Rechtsfrist nötig, Dauer trotzdem festzulegen |
| GAI-503 | Frist und Pfad für Audit und Domain-Ereignisse | offen, V17 |
| GAI-504 | Pfad für Plattformbenutzer | offen, V17, M20-08-Q7 |
| GAI-505 | Dieses Dokument | Entwurf angelegt |
| GAM-401 | Audit-Protokoll behält nach Kontaktlöschung alte und neue Werte | technisch vorbereitet (AP13): Schalter privacy.audit_redaction, Standard aus; eingeschaltet bleiben nur Feldnamen, Frage AP13-01 |
| GAM-404 | Keine Löschprofile für KI-Läufe, Anrufnotizen, Webhook-Ausgang, Postaufträge | technisch vorbereitet (AP13): Datenarten ai_run, call_log, webhook_delivery, postal_job, nur Zählung, Frist offen (V17, AP13-03) |
| GAM-405 | Jeder Kommunikationsbezug sperrt die Kontaktlöschung dauerhaft | teilweise (AP13): Schalter privacy.erasure_coupling, Standard aus; gekoppelter Löschvorschlag der Kommunikationszeilen fehlt, Frage AP13-02 |
| GAM-406 | Kein Widerspruch gegen KI-Verarbeitung und SMS | technisch vorbereitet (AP13): Einwilligungsarten sms und ai_processing, Widerspruch sperrt KI-Läufe, Rechtsgrundlage offen (AP13-04) |

## 6. Freigabe

| Rolle | Name | Datum | Ergebnis |
| --- | --- | --- | --- |
| Betreiber (Geschäftsführung) | [offen] | [offen] | [offen] |
| Datenschutz | [offen] | [offen] | [offen] |
| Rechtsanwalt / Steuerberater | [offen] | [offen] | [offen] |

Solange die Freigabe fehlt, ist dieses Konzept ein Arbeitsentwurf. Änderungen werden unter Datum fortgeschrieben.
