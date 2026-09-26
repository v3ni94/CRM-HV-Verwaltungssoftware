# Datenübernahmen

## Zweck

Dieses Kapitel beschreibt die Übernahme von Daten aus bisherigen Einzelanwendungen in die
Plattform: U-Protokoll, objektakte und den Immoware24-Spiegel. Jede Übernahme ist als
eigener, geprüfter Vorgang zu verstehen, keine automatische Ersetzung der Quelle.

## U-Protokoll

Die bisherige Anwendung U-Protokoll (Übergabeprotokolle, produktiv unter
uprotokoll.muellerhv.de) ist als Unterpunkt Übergabeprotokoll im Bereich Makler in die
Plattform überführt. Bestehende Datensätze werden per MariaDB-Dump mit Vorschau vor der
Übernahme geprüft; Dateien werden per ZIP mit Prüfsummenabgleich mit übernommen. Die
Übernahme ist idempotent je Quelldatensatz: ein wiederholter Lauf über denselben Dump legt
keine doppelten Protokolle an. Nach der Übernahme läuft die Bearbeitung ausschließlich im
CRM weiter (siehe Kapitel Makler, Abschnitt Übergabeprotokoll).

## objektakte

Die bisherige Anwendung objektakte (Dokumentenverwaltung mit rund 26.000 Dokumenten,
OCR, dreistufiger Klassifikation, Eigentümer- und Mieterlisten, Vollständigkeitsprüfung,
Google-Drive-Ablage je Objekt) läuft heute als eigener Dienst unter
uebernahme.muellerhv.de. Die vollständige Überführung in dieses Repository ist
beschlossen und mehrstufig geplant (`docs/plans/M35-objektakte-uebernahme.md`); Daten und
Funktionen werden dabei als Neubau übernommen, nicht als Code-Kopie (unterschiedliche
technische Basis).

Zum Stand dieses Handbuchs zeigt der Bereich DMS im CRM in Stufe 1 nur einen Verweis:
Objekt anklicken bzw. Objektnummer öffnet die Dokumentensuche der objektakte-Anwendung in
einem eigenen Fenster (Schaltfläche zum Öffnen der Anwendung). Eine eigene Übernahmeseite
im CRM (Stufe 2 und folgende) ist noch nicht freigegeben; Mitarbeiter arbeiten bis dahin
weiterhin direkt in objektakte unter uebernahme.muellerhv.de für die dort geführten
Dokumente.

## Immoware24-Listen und Abgleichbericht

Die Exportlisten aus Immoware24 (Objektdaten, Kontaktlisten je Gruppe) werden im CRM unter
Importe, Importassistent, Abschnitt Immoware24-Listen als CSV (UTF-8, Semikolon, höchstens
20 MB) mit Testlauf und Übernahme angelegt; vorhandene Datensätze werden nie überschrieben,
jeder Lauf erscheint unter Importe und lässt sich zurücknehmen. Einzelheiten in den Kapiteln
Objekte und Einheiten aus der Objektliste und Kontakte aus den Kontaktlisten. Solange
Immoware24 führt, vergleicht der Abgleichbericht Parallelbetrieb täglich Journal- und
Bankumsatzexporte mit der Plattform (Kapitel Abgleichbericht im Parallelbetrieb).

## Immoware24-Spiegel

Immoware24 bleibt in jeder Stufe Master der Stammdaten. Die Plattform hält lediglich einen
lesenden Spiegel per WebDAV (Dokumente), CardDAV (Kontakte) und CalDAV (Termine); ein
Schreibpfad zurück nach Immoware24 existiert nicht. Unter Einstellungen, Immoware24-
Anbindung wird die Verbindung eingerichtet und geprüft (siehe Kapitel Einstellungen).

Die Lernphase (Menü Immoware24, Lernphase) untersucht lesend die bereits gespiegelten
Daten: Ordnerstruktur und Feldnutzung je Art (WebDAV, CardDAV, CalDAV). Jeder Lauf
vergleicht sich mit dem letzten erfolgreichen Lauf gleicher Art und zeigt lesbare
Änderungen (neue Ordner, neu oder nicht mehr genutzte Felder, geänderte Anzahl
gespiegelter Datensätze). Die Lernphase verändert nichts in Immoware24 und dient allein
der Kontrolle des Spiegels.

## Was ist Vorschlag, was verbindlich

Jede Datenübernahme ist zunächst eine Vorschau, die vor der endgültigen Übernahme zu
prüfen ist. Bereits gebuchte oder rechtlich bedeutsame Inhalte (zum Beispiel
Übergabeprotokolle mit Unterschrift) werden bei der Übernahme nicht verändert, nur
zusätzlich im CRM verfügbar gemacht.

## Häufige Fehler

- **Übernahme aus U-Protokoll bricht ab**: Der ZIP-Anhang stimmt nicht mit dem
  Prüfsummenabgleich überein; Export erneut aus U-Protokoll ziehen.
- **Kein Verweis auf ein Objekt in objektakte**: Die Objektnummer im CRM stimmt nicht mit
  der in objektakte hinterlegten Nummer überein; Feld-ID Objektnummer unter Einstellungen,
  DMS-Anbindung prüfen.
- **Lernphase zeigt keine Änderung, obwohl in Immoware24 etwas geändert wurde**: Der
  letzte Abholungslauf (WebDAV/CardDAV/CalDAV) liegt vor der Änderung; unter Einstellungen,
  Immoware24-Anbindung zunächst Jetzt abrufen ausführen, danach die Lernphase erneut
  starten.
