# Importe (Imports)

## Zweck

Das Menü Importe zeigt den Verlauf aller Importe (Datenübernahmen aus Listen, dem Assistenten, Schnittstellen oder Immoware24-Exporten) und bietet die Möglichkeit, Importe rückgängig zu machen.

Ein Import ist eine automatisierte oder assistierte Übernahme von Daten:

- **Kontakte, Objekte, Einheiten, Verträge** aus Immoware24-Listen oder CSV-Dateien (Kapitel [Datenübernahmen](datenuebernahmen.md)).
- **Kontakte und Objekte** aus dem KI-Assistenten im Chat (Kapitel [KI-Assistent im Chat](assistent-chat.md)).
- **Geschäftsdatensätze** aus dem Importassistenten (Schaltfläche „Import starten" im Menü Einstellungen).

## Vorbedingungen

- Berechtigung `ai:read` zum Anzeigen von Importer-Verlauf
- Berechtigung `ai:delete` zum Rückgängigmachen von Importen

## Bedienung

Das Menü zeigt eine Tabelle mit Spalten:

- **Lauf-ID / Timestamp**: eindeutige Nummer und Uhrzeit des Imports.
- **Kategorie**: z. B. „Kontakte", „Objekte", „Verträge", „Zuordnung", „Chat" (für AI-assistierte Importe).
- **Quelle**: Dateiname, Liste (z. B. „Immoware24-Kontaktliste") oder Assistent.
- **Benutzer**: Person, die den Import gestartet hat.
- **Status**: angewendet (applied), teilweise rückgängig (partially_undone), rückgängig (undone).
- **Datensätze**: Anzahl der erstellten oder geänderten Datensätze (z. B. „42 Kontakte", „15 Verträge").
- **Aktion**: Schaltfläche zum Rückgängigmachen (wenn angewendet und die Berechtigung vorliegt).

Ein Klick auf einen Eintrag öffnet die Detailseite mit:

- Vollständiger Lauf-ID und Zeitstempel.
- Detailliste der betroffenen Datensätze (Name, Typ, Änderung).
- Fehlerprotokolle (falls Einträge fehlgeschlagen sind).
- Schaltfläche „Import rückgängig machen" (nur wenn angewendet).

### Import rückgängig machen

Wenn ein Import rückgängig gemacht wird, werden alle in diesem Lauf erstellten Datensätze gelöscht und alle geänderten Datensätze auf ihren Zustand vor dem Import zurückgesetzt. Der Status wechselt zu „rückgängig gemacht" (undone).

Eine teilweise Rückgängigmachung tritt auf, wenn einzelne Datensätze nicht gelöscht werden können (z. B. weil ein Mietvertrag bereits gebucht wurde). Diese werden mit dem Status „teilweise rückgängig" gekennzeichnet.

Nach dem Rückgängigmachen ist der Import nicht mehr ausführbar.

### Typen von Importen

| Quelle | Kategorie | Einzelheiten |
| --- | --- | --- |
| Immoware24-Export (CSV) | Objekte, Einheiten | Gebäude und Einheitsbestand mit Stammdaten. |
| Immoware24-Export (CSV) | Kontakte | Kontaktlisten (Mieter, Eigentümer, Dienstleister). |
| Immoware24-Export (CSV) | Verträge, Zahlungsplan | Mietverträge und Eigentumsverhältnisse mit Zahlbeträgen. |
| Immoware24-Zuordnung (CSV) | Zuordnung | Verknüpfung von Objekten, Einheiten, Kontakten (z. B. Eigentümer und Wohnung). |
| CSV-Upload (Listenimport) | Kontakte | Neue Kontakte aus einer Tabelle, optional mit Rolle und Zuordnung. |
| KI-Assistent (Chat) | Chat | Aus einer Chatanweisung vorgeschlagene Kontakte, Objekte oder Tickets. |
| Assistentenlauf | Laufaufruf | Geplante oder manuelle Durchläufe von Automatisierungsregeln (Kapitel [Automatisierung](automatisierung.md)). |

## Fehlerbehang und Protokoll

Falls ein Import nicht vollständig erfolgreich war, zeigt die Detailseite:

- **Erfolgreiche Einträge**: z. B. „32 von 42 Kontakte übernommen".
- **Fehler**: Pro Eintrag eine Fehlermeldung (z. B. „Pflichtfeld ‚Name' fehlt", „Kontakt bereits vorhanden", „Ungültige Telefonnummer").
- **Manueller Schritt erforderlich**: z. B. „Rolle fehlt; Benutzer wird um Bestätigung gebeten".

Fehler werden im Protokoll protokolliert und können aus der Detailseite heruntergeladen werden (CSV oder Textformat).

## Grenzen

- Ein Import wird nicht geplant oder zeitgesteuert; alle Importe sind manuelle Aufträge.
- Eine selektive Rückgängigmachung einzelner Datensätze aus einem Import ist nicht möglich; es ist alles oder nichts.
- Rechnungen und Buchungen können nicht durch Importe rückgängig gemacht werden (gesperrt nach Gate G1); diese müssen manuell reversiert werden (Kapitel [Buchhaltung](buchhaltung.md)).

Weitere Details zu den verschiedenen Datenübernahmen stehen in den verlinkten Kapiteln [Datenübernahmen](datenuebernahmen.md), [Objekte und Einheiten aus der Immoware24-Objektliste](import-objektdaten.md), [Kontakte aus den Immoware24-Kontaktlisten](import-kontakte.md), [Eigentümer und Mieter den Einheiten zuordnen](import-zuordnung.md), [Abgleichbericht](import-abgleichbericht.md) und [KI-Assistent im Chat](assistent-chat.md).

## Weitere Importberichte der Migration (30.09.2026, M8-02 bis M8-07)

Unter `/importe/immoware24` stehen sechs weitere Berichtsarten zur Wahl: Kontenplan je Objekt,
SEPA-Übersicht, Bankumsätze (Historie), Offene Posten und Verwandtes, DMS-Dokumente und
historische Tickets. Der Ablauf ist wie bei den anderen Berichten: Datei hochladen, Spalten
zuordnen (Vorlage speichern), prüfen, Testlauf mit Prüfbericht, übernehmen. Pflichtfelder sind
in der Zuordnung markiert; eine Zeile mit Fehler wird nicht übernommen und im Bericht genannt.

- Ein zweiter Lauf mit derselben Datei legt nichts doppelt an. Abweichende Werte bereits
  vorhandener Datensätze erscheinen als Konflikt und werden nie überschrieben.
- Bankumsätze kommen als Historie (nicht abgleichbar, nicht buchbar) und nur bis zum Stichtag
  des Buchungskreises. Die Zuordnung zum Migrationsjournal erfolgt über die Buchungsnummer; ist
  das Journal noch nicht importiert, wiederholen Sie den Lauf danach.
- Bei der SEPA-Übersicht entsteht ein Mandat nur, wenn Referenz, Gläubiger-ID, Unterschriftsdatum,
  IBAN und Nachweisdokument vorliegen; sonst nennt der Bericht, was fehlt. Der Zahlungsplan wird
  in jedem Fall angelegt. Der Einzug bleibt gesperrt.
- Offene Posten, Guthaben, Kautionen, Rücklagen, Darlehen und Sonderumlagen werden als
  Einzelposten mit Ursprungsfälligkeit und Teilzahlung gespeichert und nur gelesen (Summen je
  Art unter `/api/v1/imports/immoware24/history/open-items/summary`). Es entsteht keine Buchung
  und keine Mahnung.
- Historische Tickets sind nur lesend einsehbar (`/api/v1/imports/immoware24/history/tickets`).
- Eine Rücknahme über den Import ist für diese Berichte nicht vorgesehen, weil sie nur Historie
  ablegen; Korrekturen erfolgen durch einen neuen Lauf mit geänderter Datei nach Klärung des
  Konflikts.
