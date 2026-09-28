# Handlungsanweisung: Objektordner, Mieterakte und Objektdaten

Stand: 28.09.2026. Legt fest, welche Angabe als Stammdatum im CRM und welche Unterlage in
welchem Ordner der Objektakte geführt wird. Titelmuster und Schreibweisen:
[Erfassungsstandards](erfassungsstandards.md). Technischer Hintergrund:
[Dokumente und DMS](dokumente-dms.md).

## Zweck

Jede Unterlage ist für alle Mitarbeiter an derselben Stelle zu finden, ist mit dem richtigen
Objekt, der Einheit, dem Vertrag oder dem Kontakt verknüpft und fällt unter das richtige
Aufbewahrungsprofil. Inhalte, die die Software auswertet (Flächen, Daten, Beträge, Zähler),
stehen als Stammdatum im CRM und nicht nur in einem PDF.

## Grundregel: Stammdatum oder Dokument

| Angabe | Wo |
| --- | --- |
| Anschrift, Flächen, Baujahr, Grundbuch, Verwaltungsbeginn | Objekt- oder Gebäudeseite, Stammdaten |
| Energieausweiswerte | Gebäudeseite, Energieausweis; das Ausweis-PDF zusätzlich als Dokument |
| Einheit, Lage, Etage, Zimmer, Ausstattung, MEA, Wohnfläche | Einheitenseite |
| Mieter, Eigentümer, Beginn, Ende, Kaution, Zahlungsplan | Vertrag |
| Anschrift, Telefon, E-Mail, IBAN einer Person | Kontakt |
| Unterschriebener Vertrag, Protokoll, Beschluss, Rechnung, Schreiben | Dokument, im Ordner laut Tabelle unten |

Ein Dokument ersetzt nie das Stammdatum. Wer eine Angabe aus einem Dokument übernimmt, trägt sie
im Feld ein und legt das Dokument als Nachweis ab.

## Ordnerstruktur je Objekt

Verbindliche Struktur (Master-Prompt 11.2), im Google Drive des Mandanten als Objektordner
`NNN Ort, Straße Hausnummer` mit sechs Unterordnern:

| Ordner | Inhalt |
| --- | --- |
| 01_Legitimationsunterlagen | Ausweiskopien, Vollmachten, Erbscheine, Handelsregisterauszüge, SEPA-Mandate |
| 02_Stammakte | Teilungserklärung, Gemeinschaftsordnung, Verwaltervertrag, Pläne, Versicherungen, Protokolle und Beschlüsse, Dienstleisterverträge, Energieausweis |
| 03_Buchhaltung | Rechnungen, Abrechnungen, Wirtschaftspläne, Kontoauszüge |
| 04_Mieterakte | je Einheit und Mieter: Mietvertrag, Nachträge, Kündigung, Übergabeprotokolle, Mieterhöhung, Korrespondenz |
| 05_Eigentümerakte | je Einheit und Eigentümer: Grundbuchauszug, Kaufvertragsauszug, Korrespondenz, SEV-Vereinbarung |
| 06_Sonstiges | Unklar, Manuelle Prüfung, Dubletten, Nicht objektbezogen |

Ordnernamen und die Unterteilung von 06_Sonstiges sind in der Software festgelegt. Die Spalte
Inhalt ist die Ablagevorgabe dieser Anleitung; die Software prüft sie nicht.

Mieter- und Eigentümerakte sind laut Bereich DMS je Einheit und Eigentümer in elf Unterordner
gegliedert. Deren Bezeichnungen legt die Objektübernahme (objektakte) fest. Das CRM zeigt die
Struktur unter Verwaltung, DMS, Suche im Archiv, Block Ordnerstruktur der Objektakte (Struktur
anzeigen): je Ordner die Ablagevorgabe dieser Anleitung, die zugeordneten Kategorien und für 04
und 05 die Unterordner samt Dokumenttypen, sobald sie mit der Datenübernahme aus objektakte
(Verwaltung, Objektakte) in das CRM übernommen wurden. Ohne diese Übernahme steht dort
"zu verifizieren"; das CRM erfindet keine Bezeichnungen (offener Punkt F-01 in
`docs/OPEN_QUESTIONS.md`). Bis zur Festlegung im Handbuch gelten die Bezeichnungen der
Objektübernahme.

## Dokumentkategorien und Zielordner

Jede Kategorie hat im CRM einen Zielordner (Standard je Mandant, änderbar):

| Kategorie | Zielordner |
| --- | --- |
| Rechnung | 03_Buchhaltung |
| Abrechnung | 03_Buchhaltung |
| Vertrag | 02_Stammakte |
| Protokoll | 02_Stammakte |
| Versicherung | 02_Stammakte |
| Teilungserklärung | 02_Stammakte |
| Legitimationsunterlage | 01_Legitimationsunterlagen |
| Mieterakte | 04_Mieterakte |
| Eigentümerakte | 05_Eigentümerakte |
| Schreiben | 06_Sonstiges |
| Foto | 06_Sonstiges |
| Sonstiges | 06_Sonstiges |

Mieterunterlagen (Mietvertrag, Nachträge, Kündigung, Übergabeprotokolle, Mieterhöhung,
Korrespondenz) erhalten die Kategorie Mieterakte, Eigentümerunterlagen die Kategorie
Eigentümerakte; ein Mietvertrag mit Kategorie Vertrag landet über die Spiegelung in
02_Stammakte. Mandanten, die vor dem 28.09.2026 angelegt wurden, ergänzen die beiden
Kategorien einmalig über den Knopf Standardkategorien ergänzen im Block Ordnerstruktur der
Objektakte (Recht `tenant_settings:update`). Ist die Ablage über die Objektübernahme
eingeschaltet (Hinweis Hochgeladen, die Ablage in Drive und Paperless läuft über die
Objektübernahme), ordnet objektakte das Dokument anhand der Einheit der Mieter- oder
Eigentümerakte zu. Ohne diese Ablage (Hinweis Hochgeladen, die Ablage folgt der Spiegelung des
CRM) entscheidet die Kategorie über den Zielordner; die Unterordner je Person legt das CRM
nicht an, der Ordner in Drive ist zu prüfen und die Datei gegebenenfalls von Hand in den
Unterordner zu verschieben.

## Ablauf: Dokument ablegen

1. Verwaltung, DMS, Suche im Archiv (Seite Dokumentsuche), Abschnitt Dokument hochladen.
2. Datei wählen, Objekt wählen, Einheit wählen (bei Mieter- oder Eigentümerunterlagen immer),
   sonst ganzes Objekt.
3. Kategorie wählen (zum Beispiel Mieterakte); ohne Auswahl ergibt sie sich aus der
   Klassifikation. Vertrag wählen (Verträge der Einheit, ohne Einheit die des Objekts) und
   Kontakt suchen und übernehmen, wenn die Unterlage eine Person betrifft.
4. Titel nach Erfassungsstandards, zum Beispiel `WE 05, Mietvertrag, Müller, 01.10.2026`.
5. Hochladen, dann Dokument öffnen.
6. Auf der Dokumentseite prüfen:
   - Verknüpfungen: Objekt, Einheit, Vertrag und Kontakt aus dem Upload; weitere
     Verknüpfungen entstehen aus dem jeweiligen Vorgang (zum Beispiel Übergabeprotokoll,
     Kautionsabrechnung, Mandat, Ticket).
   - Ablage über die Objektübernahme: Status abgelegt, In Drive öffnen.
   - Sichtbarkeit im Portal: nur intern, Mieter, Eigentümer, Dienstleister, Beirat oder alle;
     Sichtbarkeit speichern. Standard ist nicht freigegeben. Personenbezogene Unterlagen eines
     Mieters nie für Eigentümer oder alle freigeben.
7. Dokumente aus Mails bleiben am Ticket; Rechnungen gehen in den Belegeingang
   ([Belegeingang](belegeingang.md)).

## Objektmappe und Portal

Die Objektmappe auf der Objektseite zeigt Dokumente, die im Portal für Mieter oder Eigentümer
sichtbar sind (zum Beispiel Hausordnung, Wirtschaftsplan). Freigabe über die Sichtbarkeit des
Dokuments. Welche Unterlagen Eigentümern zur Einsicht zustehen, ist rechtlich zu prüfen durch
Rechtsanwalt [Platzhalter]; die Einsicht der Gemeinschaft läuft über Einsichtsanfragen
(Regel `docs/rules/A61-einsicht.md`).

## Vollständigkeit und Prüffälle

- Objektseite, Vollständigkeit der Objektakte: Pflichtunterlagen vorhanden oder fehlend,
  Nachforderungsschreiben als Entwurf erzeugen.
- Verwaltung, Objektakte: Prüffälle der Klassifikation (Offen, In Bearbeitung, Erledigt,
  Verworfen); je Fall Klasse bestätigen oder manuell setzen. Recht `objektakte:update`.
- Verwaltung, Objektakte, Listen aus der Objektakte: Anforderungsliste und Dokumentenübersicht
  je Kategorie.

## Aufbewahrung

Einstellungen, Aufbewahrung: Aufbewahrungsprofile je Unterlagenklasse mit Zuordnung der
Kategorien. Die Standardprofile sind Entwürfe (Prüfung Steuerberatung offen, Regel
`docs/rules/M6-04-aufbewahrungsprofile.md`); ein Entwurf gibt keine Löschung frei.
Unterlagenklassen: Buchungsbelege, Journale, Abrechnungen, Geschäftsbriefe, Vorgänge, E-Mails,
Verträge, Portaldaten, Bewerberdaten, WEG-Protokolle, WEG-Beschlüsse. Löschen nur über
Verwaltung, Dokumente, Löschvorschläge (Aufbewahrung) im Vier-Augen-Prinzip. Dokumente nie in
Drive oder Paperless von Hand löschen.

## Checkliste

- [ ] Angabe als Stammdatum eingetragen, Dokument nur als Nachweis
- [ ] Objekt und bei Personenunterlagen Einheit, Kategorie Mieterakte oder Eigentümerakte,
      Vertrag und Kontakt gewählt
- [ ] Titel nach Erfassungsstandards
- [ ] Ordner in Drive geprüft (04 und 05 insbesondere)
- [ ] Sichtbarkeit im Portal bewusst gesetzt
- [ ] Keine Dublette (Dubletten werden markiert, nicht gelöscht)

## Häufige Fehler

- Upload ohne Einheit: Mieterunterlage landet nicht in der Mieterakte.
- Mietvertrag mit Kategorie Vertrag statt Mieterakte hochgeladen: landet über die Spiegelung in
  02_Stammakte; Kategorie auf der Dokumentseite ändern.
- Datei direkt in Drive abgelegt: im CRM nicht verknüpft; über DMS, Objekt, Als
  CRM-Dokumente verknüpfen nachholen.
- Personalausweis ohne Erfordernis gespeichert (Datensparsamkeit).
- Dokument für alle im Portal freigegeben.

## Lücken in der Software

- Standardkategorien Mieterakte (04) und Eigentümerakte (05) (28.09.2026 geschlossen), Upload
  mit Kategorie, Vertrag und Kontakt (28.09.2026 geschlossen), Ordnerstruktur im CRM
  beschrieben (28.09.2026 geschlossen).
- Die Bezeichnungen der elf Unterordner erscheinen im CRM erst nach der Datenübernahme aus
  objektakte; sie liegen nicht im Repository und sind zu verifizieren (F-01).
- Die Unterordner je Einheit und Person legt das CRM in Drive nicht selbst an; das bleibt bei
  der Ablage über die Objektübernahme.
- Aufbewahrungsprofile noch nicht durch die Steuerberatung freigegeben.
