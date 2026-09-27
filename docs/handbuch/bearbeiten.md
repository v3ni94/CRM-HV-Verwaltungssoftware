# Stammdaten direkt bearbeiten

## Zweck

Stammdaten von Objekt, Gebäude, Einheit und Kontakt lassen sich auf der Detailseite an Ort und
Stelle ändern. Ein Feld wird über den Stift daneben oder der gesamte Abschnitt über
"Bearbeiten" geöffnet. Jede Änderung wird einzeln gespeichert, ein Formular mit Speichern-Knopf
ist nicht nötig. Beim Vertrag gilt das nur für Bemerkungen und Mahnsperre; Zahlungen, Laufzeit
und Parteien werden weiterhin als neue Vertragsversion erfasst.

## Bedienung

* "Bearbeiten" im Abschnittskopf schaltet alle Felder des Abschnitts in den Änderungsmodus,
  "Fertig" schließt ihn wieder. Der Stift neben einem Wert öffnet nur dieses Feld.
* Text, Zahl und Datum werden beim Verlassen des Feldes oder mit Eingabe gespeichert. Escape
  verwirft die Eingabe. Bemerkungen speichern beim Verlassen oder mit Strg+Eingabe.
* Auswahlfelder und Ja/Nein speichern sofort bei der Änderung.
* Unter dem Feld erscheint der Zustand: "Speichert", "Gespeichert" oder eine Fehlermeldung.
  Der Abschnittskopf zeigt den Gesamtzustand.
* Ungültige Angaben (zum Beispiel eine negative Fläche) werden nicht übernommen; die Meldung
  steht direkt am Feld, der bisherige Wert bleibt erhalten.
* Hat jemand anderes den Datensatz zwischenzeitlich geändert, erscheint der Hinweis "Von
  jemand anderem geändert, neu laden". Danach ist die Seite neu zu laden; die eigene Eingabe
  ist erneut vorzunehmen.
* Ohne Schreibrecht (Objekte bzw. Kontakte) sind weder Stift noch "Bearbeiten" sichtbar.

## Nachvollziehbarkeit

Jede gespeicherte Änderung wird im Ereignisprotokoll des Datensatzes mit altem und neuem Wert
festgehalten, genau wie bei der Bearbeitung über das Formular. Finanzfelder, Bankverbindungen,
Adressen und sonstige Untertabellen des Kontakts sind von der Direktbearbeitung ausgenommen und
werden weiterhin über die jeweiligen Formulare gepflegt.
