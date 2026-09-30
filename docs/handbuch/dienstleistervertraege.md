# Dienstleisterverträge (Service Contracts)

## Zweck

Das Menü Dienstleisterverträge verwaltet Verträge mit externen Dienstleistern (Handwerker, Reinigung, Hausmeister, Energieauditor, Abrechnungsstelle, Versicherungsmakler, etc.). Kündigungsfristen werden automatisch in die Fristenliste (Kapitel Fristen) übernommen.

## Vorbedingungen

- Berechtigung `contracts:read` und `contracts:create` für die Verwaltung

## Bedienung

Das Menü zeigt eine Tabelle mit Spalten:

- **Dienstleister**: Name und optional Ansprechpartner (Kontakt mit Rolle Dienstleister).
- **Leistung**: Kurzbeschreibung der Leistung (z. B. „Hausmeister", „Schornsteinfeger").
- **Objekt / Gebäude**: Zuordnung zu einem Objekt oder mehreren Objekten (kommagetrennt).
- **Start**: Vertragsbeginn (ISO 8601: TT.MM.JJJJ).
- **Ende**: Vertragsenddatum (leer bei unbefristet).
- **Kündigungsfrist**: z. B. 14 Tage, 3 Monate, zum Ende eines Quartals.
- **Nächster Anlass**: berechnetes Kündigungsdatum, um die Kündigungsfrist einzuhalten (Orientierung, zu verifizieren).

Ein Klick auf einen Vertrag öffnet die Detailseite.

### Vertrag anlegen / bearbeiten

Schaltfläche „Dienstleistervertrag anlegen" öffnet ein Formular mit:

- **Dienstleister** (Pflicht): Kontakt mit Rolle Dienstleister (Suchfeld mit Rollenfilter). Ist der Kontakt nicht vorhanden, kann er über den Link „Neuer Kontakt" angelegt werden.
- **Leistung** (Pflicht): Kurzbeschreibung (z. B. „Hausmeisterservice", „Energieberatung").
- **Objekte / Gebäude** (optional): ein oder mehrere Objekte, für die die Leistung erbracht wird.
- **Vertragsbeginn** (Pflicht): Datum im Format TT.MM.JJJJ.
- **Vertragsende** (optional): Enddatum; leer bei unbefristet.
- **Kündigungsfrist** (optional): Frist und optional der Anlass (z. B. „zum Ende eines Kalendermonats"), z. B. „14 Tage", „3 Monate zum Ende eines Quartals".
- **Kosten** (optional): geschätzte oder vereinbarte Jahreskosten im Format 1.234,56 EUR (Orientierung, wird nicht in die Buchhaltung übernommen).
- **Verantwortlich** (optional): Person oder Rolle (Erfassungsstandard ES-10).
- **Notizen** (optional): interne Hinweise.

Nach dem Speichern wird die Detailseite angezeigt und kann bearbeitet werden. Eine neue Version ab Stichtag wird angelegt, wenn einzelne Felder geändert werden; Dienstleister und Leistung bleiben fest. Der Vertrag wird beendet durch Erfassung eines Enddatums (wenn nicht bereits vorhanden).

### Kündigungsfristen und Fristenliste

Der nächste Kündigungsanlass wird berechnet, um die vereinbarte Kündigungsfrist einzuhalten:

- Wenn ein Vertragsende bekannt ist, wird das Kündigungsdatum aus Enddatum minus Kündigungsfrist berechnet.
- Wenn das Ende offen ist, wird der nächste Anlass aus der Kündigungsfrist und dem heutigen Tag berechnet (z. B. heute + 3 Monate für eine 3-Monatsfrist).
- Alle Kündigungsanlässe erscheinen in der Fristenliste (Kapitel Fristen) mit Typ „Kündigungsfrist Dienstleistervertrag".

Die berechneten Termine sind Orientierung und müssen rechtlich geprüft werden; die Kündigungsfrist selbst richtet sich nach der Vertragsformulierung, nicht nach dem hier eingetragenen Text.

## Grenzen

- Dienstleisterverträge werden nur für Verwaltungszwecke geführt. Eine Verknüpfung zu Rechnungen, Aufträgen oder Kosten erfolgt nicht automatisch (siehe Kapitel [Buchhaltung](buchhaltung.md) und [Belegeingang](belegeingang.md)).
- Ein Dienstleistervertrag ist nicht erforderlich, um eine Rechnung eines Dienstleisters zu erfassen; es ist ein Verwaltungsinstrument für Kündigungsfristen.
- Verträge mit Vertragsparteien mit anderen Rollen (z. B. Makler bei Bestandsobjekten) werden im Kapitel [Verträge](vertraege.md) gepflegt.
