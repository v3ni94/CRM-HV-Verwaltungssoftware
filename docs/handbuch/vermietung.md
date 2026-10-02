# Vermietung (Rental Management)

## Zweck

Das Menü Vermietung bietet eine Übersicht der Mietverwaltung mit Leerstandsliste und Mieterhöhungen. Aus diesem Menü lassen sich schnell Mietverträge erfassen und Mieterhöhungsfälle starten.

## Vorbedingungen

- Berechtigung `contracts:read` und `contracts:create` für die Erfassung

## Bedienung

Das Menü zeigt zwei Bereiche:

### Leerstandsliste

Eine Tabelle mit Spalten:

- **Einheit**: Objekt und Einheitsnummer mit Stichtagszahl der laufenden Mietverträge.
- **Fläche**: in Quadratmetern.
- **Ausfall ab**: Enddatum des letzten Mietvertrags oder heute, wenn keine Verträge aktiv sind. Berechnung: Enddatum + 1 Tag.
- **Fällt aus**: Anzahl der Tage seit dem Ausfall.
- **Vermieter**: bei mehreren Rechtsträgern im Objekt der Eigentümer oder SEV-Eigentümer.

Ein Klick auf eine Einheit öffnet die Objektseite mit der Einheit.

### Mieterhöhungen

Ein Formular zum schnellen Start eines Mieterhöhungsfalls (Kapitel [Mieterhöhung](anleitung-mieterhoehung.md)):

- **Vertrag wählen** aus der Liste der laufenden Mietverträge (Suchfeld mit Filterfunktion).
- **Datum der Ankündigung** (Auslösedatum).
- **Neue Nettomiete** im Format 1.234,56 EUR.
- **Grund**: aus dem Katalog der Mieterhöhungsgründe (Indexanpassung, Staffel, Modernisierung, sonstige).

Ein Klick auf „Mieterhöhungsfall starten" erzeugt einen neuen Fall und zeigt diesen zur Bearbeitung.

Weitere Mieterhöhungsfälle werden in der [Anleitung Mieterhöhung](anleitung-mieterhoehung.md) beschrieben.

### Vertrag anlegen

Eine Schaltfläche führt zum Formular für neue Mietverträge. Details stehen im Kapitel [Verträge](vertraege.md), Abschnitt „Vertrag anlegen".

## Struktur und Datenquellen

Mietverträge werden im CRM unter Verträge gepflegt und werden von hier aus zur Vermietungssicht angezeigt. Im Parallelbetrieb mit Immoware24 stammen Mietverträge aus den Datenübernahmen (Kapitel [Datenübernahmen](datenuebernahmen.md)); im Regelbetrieb werden sie im CRM erfasst.

## Grenzen

- Leerstandsliste und Mieterhöhungsformular sind nur Orientierung. Tatsächliche Ausfalltage und Mieterhöhungsfristen sind rechtlich zu prüfen.
- Weitere Mietvertragsverwaltung (Kautionen, Betriebskosten, Sonderabsprachen) erfolgt im Kapitel [Verträge](vertraege.md) und [Abrechnung Miete](abrechnung-miete.md).

## Leerstandsmaßnahmen, Mietspiegel und Interessentenabgleich

- Leerstandsliste: Je Einheit lassen sich Status, Sollmiete, Kosten je Monat, Wiedervorlage und Notiz erfassen (Schaltfläche Maßnahme). Die entgangene Miete und die Leerstandskosten werden anteilig aus den Monatswerten berechnet (Monatswert x 12 / 365 x Leerstandstage). Fehlt die Sollmiete, bleibt der Wert leer. Mit Anzeige anlegen entsteht ein Entwurf der Mietanzeige.
- Mietspiegel: Werte je Gemeinde werden unter der Schnittstelle `/letting/rent-index` einzeln oder per CSV gepflegt (Spalten gemeinde, name, stand, baujahr_von, baujahr_bis, flaeche_von, flaeche_bis, ausstattung, min, mittel, max, quelle). Die Vorschau prüft die Datei, ohne etwas zu speichern. Die Abfrage zeigt die passende Spanne; die Einordnung bleibt Entscheidung der Verwaltung.
- Mieterhöhung mit Begründung Index, Modernisierung oder Staffel: Die Zusatzangaben (Indexwerte, Kosten und Umlagesatz, Staffeln) und das Quelldokument werden erfasst. Die Prüfung rechnet nur nach und sperrt die Freigabe bei Abweichungen. Sie sagt nichts über die Zulässigkeit.
- Exposé: Aus der Einheit und der jüngsten Mietanzeige wird ein PDF auf dem Briefbogen im Dokumentenbereich abgelegt. Offene Angaben stehen im Dokument, solange sie fehlen, mit Entwurfskennzeichnung. Bilder sind in dieser Version nicht eingebettet.
- Interessenten: Zusätzlich zur Einheit lassen sich Anzeige und Suchprofil erfassen. Der Abgleich je Anzeige zeigt erfüllte, nicht erfüllte und nicht prüfbare Kriterien und reiht die Interessenten. Er ist ein Vorschlag, keine Zusage.

- Mietspiegel: Unter Vermietung, Mietspiegel werden Werte je Gemeinde erfasst oder per CSV eingelesen (erst Vorschau, dann Übernehmen). Die Quelle ist Pflicht und vor der Verwendung zu prüfen.
- Mieterhöhung aus dem Mietspiegel: Im Fall im Status Entwurf Gemeinde (und Baujahr) eingeben, Spanne suchen und Untergrenze, Mittelwert oder Obergrenze übernehmen. Die Wahl der Position bleibt Sache der Verwaltung, die Prüfung läuft danach neu.
- Exposé als PDF: An der Einheit "Exposé als PDF ablegen". Bilder der Anzeige werden eingebettet, offene Angaben stehen im Dokument.
- Interessentenabgleich: An der Einheit mit Anzeige "Interessenten abgleichen" zeigt die Reihung nach erfüllten Kriterien. Das ist ein Vorschlag, keine Entscheidung.

## Mietspiegel (Version 1.49.0)

Seite `/vermietung/mietspiegel`. Zweck: Mietspiegelwerte je Gemeinde mit Quellenangabe pflegen.
Voraussetzung zum Ändern: Recht zum Ändern von Verträgen.

* Die Liste zeigt Gemeinde, Mietspiegel, Stand, Kriterien (Baujahr von, bis) und die Spanne je m² und
  Monat (Untergrenze, Mittelwert, Obergrenze in EUR). Einträge lassen sich löschen.
* Wert erfassen: manuell über das Formular, oder per CSV Import (Semikolon getrennt, Dezimalkomma und
  Datum TT.MM.JJJJ zulässig). Die Vorschau meldet gelesene und fehlerhafte Zeilen, Übernehmen legt die
  Werte an und überspringt vorhandene.
* Grenzen: Einordnung in die Spanne und ortsübliche Vergleichsmiete bleiben eine Entscheidung der
  Verwaltung, die Quelle ist vor der Verwendung zu prüfen.

## Selbstauskunft Links je Interessent (GAI-420, Welle 21)

In der Interessentenliste zeigt "Links anzeigen" die erzeugten Selbstauskunft Links mit Status (offen, eingereicht, abgelaufen) und Ablaufdatum. Der vollständige Link wird nur bei der Erzeugung angezeigt.
