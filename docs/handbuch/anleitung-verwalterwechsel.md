# Handlungsanweisung: Verwalterwechsel und Objektübernahme

Stand: 28.09.2026. Gilt für die Hausverwaltung Müller GmbH als übernehmende Verwaltung.
Menüpfade beziehen sich auf die linke Navigation des CRM (Gruppen Übersicht, Verwaltung,
Makler, Finanzen, System). Erfassungsregeln für Schreibweisen und Pflichtfelder stehen in
[Erfassungsstandards](erfassungsstandards.md).

## Zweck

Ein Objekt wird von einer Vorverwaltung übernommen. Ziel ist, dass Stammdaten, Verträge,
Kontakte, Bankkonten und die Objektakte am Tag des Verwaltungsbeginns vollständig und geprüft
im CRM stehen, dass jede Unterlage der Vorverwaltung nachvollziehbar abgelegt ist und dass
fehlende Unterlagen schriftlich nachgefordert werden.

## Wann anwenden

- Neuer Verwaltervertrag über eine WEG, eine Mietverwaltung oder eine WEG mit
  Sondereigentumsverwaltung (SEV).
- Übernahme eines Bestands aus Immoware24 in den Parallelbetrieb.

Nicht anwenden, wenn die Hausverwaltung Müller GmbH ein Objekt abgibt: dafür gilt Abschnitt
"Abgabe eines Objekts" am Ende.

## Rechtliche Voraussetzungen

Rechtlich zu prüfen durch Rechtsanwalt: [Platzhalter] Wirksamkeit der Bestellung und des
Verwaltervertrags, Beginn der Befugnisse, Herausgabepflichten der Vorverwaltung und Umfang der
herauszugebenden Unterlagen, Umgang mit Konten der Gemeinschaft und Fristen für die
Herausgabe. In `docs/rules/` ist dazu keine Regel mit Quellenstatus hinterlegt; die Software
prüft keine dieser Voraussetzungen.

## Voraussetzungen im CRM

- Rechte: `properties:create` und `properties:update` (Objekte), `contacts:create`,
  `contracts:create`, `documents:create`. Die Systemrollen Standard, Sachbearbeiter ohne
  Löschen und Sachbearbeiter ohne Buchhaltung haben diese Rechte.
- Für die Freigabe importierter Verträge: `contracts:approve` (in der Vorbelegung nur
  Mandantenadministrator und Administrator).
- Für die Freigabe von Bankverbindungen der Kontakte: `contacts:approve` (Vorbelegung ebenso nur
  Administratorrollen), stets eine zweite Person.
- Unterlagen der Vorverwaltung liegen digital vor oder sind gescannt.
- Freigabestufen G1 bis G5 bleiben geschlossen. Die Übernahme erzeugt keine produktiven
  Buchungen und keine Zahlungen.

## Ablauf in der Software

### 1. Objekt anlegen

Weg A, Einzelanlage: Übersicht, Objekte, Schaltfläche Objekt anlegen.

1. Objektnummer (3 Ziffern), Name, Verwaltungsart (Mietverwaltung, WEG, WEG mit SEV),
   Straße, Hausnummer, PLZ, Ort, Bundesland eintragen, Anlegen.
2. Die Verwaltungsart ist nach der Anlage nicht mehr änderbar. Vorher klären, ob SEV
   übernommen wird.
3. Auf der Objektseite im Abschnitt Stammdaten Verwaltungsbeginn, Grundbuchangaben und
   Flächen ergänzen (Stift am Feld).

Weg B, Übernahme aus Immoware24: System, Importe. Ablauf und Dateiformate in
[Objekte und Einheiten aus der Immoware24-Objektliste](import-objektdaten.md),
[Kontakte aus den Immoware24-Kontaktlisten](import-kontakte.md) und
[Eigentümer und Mieter den Einheiten zuordnen](import-zuordnung.md). Jeder Import läuft zuerst
als Testlauf; der Bericht ist vor der Übernahme zu prüfen.

### 2. Gebäude, Einheiten, Umlageschlüssel

Gebäude, Einheiten und Schlüsselwerte (zum Beispiel MEA, WFL) lassen sich in der Oberfläche
nicht neu anlegen. Anlage über den Import (Weg B) oder über die Schnittstelle. Bestehende
Einheiten werden danach auf der Einheitenseite (Aufruf über die Tabelle Einheiten der
Objektseite) und auf der Gebäudeseite direkt geändert. Einzelheiten in [Stammdaten](anleitung-stammdaten.md).

### 3. Kontakte

Übersicht, Kontakte, Kontakt anlegen (oder Import). Je Eigentümer, Mieter, Beirat,
Dienstleister und Versorger ein Kontakt; Rollen im Feld Rollen/Klassifizierung setzen. Vor dem
Speichern die Dublettenprüfung beachten; Trotzdem speichern nur nach Prüfung der Trefferliste.
Beiratsmitglieder und Ansprechpartner des Objekts erscheinen im Abschnitt Ansprechpartner der
Objektseite; deren Pflege erfolgt über den Import oder die Schnittstelle.

### 4. Verträge

- WEG: je Einheit ein Vertrag der Art Eigentum (WEG, SEV) mit Eigentumsübergang (Grundbuch)
  als Pflichtfeld. Verwaltung, Verträge, Vertrag anlegen.
- Mietverwaltung: zuerst muss der Eigentümer des Objekts erfasst sein, sonst ist der Vermieter
  nicht bestimmbar; danach je Mieter ein Mietvertrag.
- Aus dem Import angelegte Verträge stehen unter Verwaltung, Verträge, Freigabe Importverträge
  (Seite `/vertraege/freigabe`). Vertragsbeginn und Beträge sind dort Annahmen des Imports. Die
  Geschäftsführung prüft und gibt frei (Ausgewählte freigeben) oder lehnt eine Fehlzuordnung ab
  (Ablehnen). Erst nach der Freigabe erzeugen die Zahlungspläne Sollstellungen.

### 5. Bankkonten

- Konten der Gemeinschaft oder des Eigentümers: Finanzen, Bank beziehungsweise Einstellungen,
  Bank (finAPI oder FinTS, nur lesend). Auf der Objektseite im Abschnitt Bankkonten des Objekts
  ein Standardkonto je Zweck festlegen (Als Standard setzen).
- Bankverbindungen der Eigentümer und Mieter: im Kontakt. Jede neue IBAN wartet auf Freigabe
  durch eine zweite Person, siehe [Bankverbindung](anleitung-bankverbindung.md).
- Ob und wann Konten der Vorverwaltung auf die neue Verwaltung umgestellt werden, entscheidet
  die Geschäftsführung; die Software bildet diesen Schritt nicht ab.

### 6. Unterlagen der Vorverwaltung ablegen

1. Verwaltung, DMS, Suche im Archiv öffnen (Seite Dokumentsuche). Im Abschnitt Dokument
   hochladen Datei, Objekt, gegebenenfalls Einheit (sonst ganzes Objekt) und Titel wählen,
   Hochladen.
2. Ablage nach [Objektordner](anleitung-objektordner.md): Teilungserklärung, Verträge,
   Protokolle, Versicherungen in 02 Stammakte; Abrechnungen und Belege in 03 Buchhaltung;
   Unterlagen je Mieter in 04 Mieterakte; Unterlagen je Eigentümer in 05 Eigentümerakte;
   Ausweiskopien und Vollmachten in 01 Legitimationsunterlagen.
3. Titel nach dem Muster der Erfassungsstandards vergeben, zum Beispiel
   `Übergabe Vorverwaltung, Teilungserklärung, 12.03.1998`.

### 7. Vollständigkeit prüfen und nachfordern

1. Objektseite, Abschnitt Vollständigkeit der Objektakte: zeigt, welche Pflichtunterlagen
   vorhanden sind und welche fehlen. Welche Unterlagen je Verwaltungsart Pflicht sind, wird
   derzeit nur über die Schnittstelle gepflegt (Recht `objektakte:approve`); eine Seite dafür
   gibt es nicht.
2. Schaltfläche Nachforderungsschreiben als Entwurf erzeugen: Entwurf (nicht versendet) mit
   der Liste der fehlenden Unterlagen. Text prüfen, auf den Briefbogen der Hausverwaltung
   Müller GmbH übernehmen, durch die Geschäftsführung freigeben lassen, versenden und das
   versandte Schreiben als Dokument am Objekt ablegen.
3. Verwaltung, Objektakte, Listen aus der Objektakte: Anforderungsliste über alle Objekte für
   die Nachverfolgung.

### 8. Checkliste, Fristen und Wiedervorlagen

1. Objektseite, Abschnitt Checkliste Verwalterwechsel, Checkliste starten. Die zehn Schritte
   dieser Anleitung erscheinen als Liste; jeder Schritt wird beim Abhaken mit Datum und
   Benutzer festgehalten. Sind alle Schritte erledigt, gilt die Liste als abgeschlossen; ein
   zurückgesetzter Schritt öffnet sie wieder. Je Objekt ist eine offene Liste möglich.
2. Objektseite, Abschnitt Fristen, Frist anlegen: Fristtyp Verwalterwechsel (Auslöser
   Verwaltungsbeginn), Auslösedatum, verantwortliche Person. Ist im Fristtyp eine Dauer
   hinterlegt, wird die Fälligkeit daraus berechnet und als zu verifizieren angezeigt; sonst
   die Fälligkeit eintragen. Die Frist erscheint in Übersicht, Fristen (Typ Eigene Frist) und
   im Kalender; die Vorfrist aus den Einstellungen der Tagesjobs benachrichtigt die
   verantwortliche Person.
3. Termin im Kalender für Übergabegespräch und Begehung.
4. Die Dauer des Fristtyps pflegt die Geschäftsführung unter Einstellungen, Fristtypen (siehe
   [Einstellungen](einstellungen.md)). Die konkrete Herausgabefrist ist rechtlich zu prüfen
   durch Rechtsanwalt: [Platzhalter]; die Software gibt keine Dauer vor.

## Zu verknüpfende Datensätze

| Datensatz | Verknüpfung |
| --- | --- |
| Objekt | alle Dokumente der Vorverwaltung, Ticket Verwalterwechsel |
| Einheit | Dokumente, die nur eine Einheit betreffen (Upload mit Einheit) |
| Vertrag | entsteht je Eigentümer oder Mieter; Dokumente über den Vertragsbezug in Mieter- oder Eigentümerakte |
| Kontakt | Vorverwaltung als Kontakt mit Rolle Verwalter; Eigentümer, Mieter, Beirat |

## Freigaben

| Schritt | Wer | Durch die Software erzwungen |
| --- | --- | --- |
| Importverträge freigeben | Geschäftsführung (Recht `contracts:approve`) | ja, Recht erforderlich |
| Bankverbindung eines Kontakts | zweite Person (Recht `contacts:approve`) | ja, Vier-Augen-Prinzip |
| Nachforderungsschreiben | Geschäftsführung | nein, organisatorisch |
| Kontoumstellung, Verwaltervertrag | Geschäftsführung | nein, außerhalb der Software |

## Checkliste

- [ ] Verwaltungsart vor Anlage geklärt
- [ ] Objekt angelegt, Verwaltungsbeginn eingetragen
- [ ] Gebäude, Einheiten und Schlüsselwerte per Import angelegt und geprüft
- [ ] Kontakte angelegt, Dubletten geprüft, Rollen gesetzt
- [ ] Verträge angelegt; Importverträge durch die Geschäftsführung freigegeben
- [ ] Bankkonten zugeordnet, Standardkonto gesetzt; neue IBAN freigegeben
- [ ] Unterlagen der Vorverwaltung hochgeladen und im richtigen Ordner abgelegt
- [ ] Vollständigkeit geprüft, Nachforderungsschreiben freigegeben und versandt, Kopie abgelegt
- [ ] Frist Verwalterwechsel mit Fälligkeit und Verantwortlichem angelegt
- [ ] Rechtliche Punkte durch Rechtsanwalt geprüft

## Häufige Fehler

- Verwaltungsart falsch gewählt: nicht korrigierbar, Objekt muss neu angelegt werden.
- Mietverträge vor dem Objekteigentümer erfasst: Import meldet Konflikt, kein Vermieter.
- Importverträge ohne Prüfung freigegeben: Beginn 01.01. des laufenden Jahres ist eine Annahme
  des Imports; falsche Sollstellungen sind die Folge.
- Dokumente ohne Objekt hochgeladen: landen in 06 Sonstiges.
- IBAN aus einer E-Mail der Vorverwaltung ohne Nachweis übernommen.

## Abgabe eines Objekts

Objektseite, Verwaltung beenden: Gekündigt von, Kündigungsdatum, Ende der Verwaltung,
Nachfolgender Verwalter, Nachfolgender Eigentümer, Kündigungsschreiben (Datei hochladen),
Notiz; Weiter, dann Verwaltung beenden. Das Objekt wird deaktiviert, alle Daten bleiben
erhalten. Wieder aktivieren kann nur der Superadmin (Regel `docs/rules/M4-05-objekt-deaktivieren.md`).
Die Kündigung selbst ist vorher durch die Geschäftsführung freizugeben. Umfang und Frist der
Herausgabe an den Nachfolger: rechtlich zu prüfen durch Rechtsanwalt [Platzhalter]. Einen
Export der Objektakte für den Nachfolger bietet die Oberfläche nicht an.

## Lücken in der Software

- Keine Oberfläche zum Anlegen von Gebäuden, Einheiten und Umlageschlüsselwerten; nur Import
  oder Schnittstelle.
- Dauer des Fristtyps Verwalterwechsel noch nicht hinterlegt (WS-01-Q1); bis dahin Fälligkeit je
  Frist von Hand eintragen.
- Ansprechpartner des Objekts (Beirat) nicht in der Oberfläche pflegbar.
- Pflichtunterlagen der Vollständigkeitsprüfung nur über die Schnittstelle pflegbar.
- Nachforderungsschreiben nur als Textentwurf, kein Briefbogen-PDF und kein Versandnachweis.
- Kein Export der Objektakte bei Abgabe an einen Nachfolger.
- Offene Posten, Salden und Rücklagenstände der Vorverwaltung lassen sich wegen G1 nicht
  produktiv als Eröffnungsbestand übernehmen.
