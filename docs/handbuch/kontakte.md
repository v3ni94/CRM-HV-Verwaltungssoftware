# Kontakte

## Zweck

Kontakte bilden alle Personen und Firmen ab, mit denen die Verwaltung zu tun hat:
Eigentümer, Mieter, Verwalter, Dienstleister, Banken und Sonstiges. Ein Kontakt kann
mehrere dieser Rollen (Feld Rollen/Klassifizierung) gleichzeitig tragen.

## Liste, Suche und Sammelaktion

Liste mit Suche (Name, E-Mail, Telefon, Ort) und Filter nach Art und Schlagwort. Ein
Filter lässt sich unter einem Namen speichern; gespeicherte Filter sieht nur, wer sie
angelegt hat. Für mehrere Kontakte gleichzeitig: Zeilen markieren, Schlagwort eingeben,
Hinzufügen oder Entfernen; die Aktion wird ganz oder gar nicht ausgeführt.

## Stammdaten und Reiter

Ein Kontakt gliedert sich in Stammdaten, Kommunikation (Telefonnummern, E-Mail-Adressen,
Adressen), Bankverbindungen, Notizen und Einwilligungen. Bei einer Person sind Vor- oder
Nachname Pflicht, bei einer Firma der Firmenname.

## Bankverbindungen und SEPA-Mandat

Je Bankverbindung lässt sich IBAN, BIC, Bank und Kontoinhaber erfassen. Eine
SEPA-Lastschrift wird erst nach einer eigenen Freigabe (SEPA-Lastschrift aktiv) mit
Mandatsreferenz, Datum der Erteilung und Erteilungsart aktiv:

- Erteilungsart Mandat als PDF: Das unterschriebene Mandat wird hinterlegt.
- Erteilungsart Telefon, Brief oder E-Mail: Datum und Vermerk der Erteilung werden
  eingetragen.

Ohne Datum der Erteilung, Erteilungsart und Nachweis (PDF oder Vermerk) lässt sich die
SEPA-Freigabe nicht speichern. Bereits gespeicherte Bankverbindungen werden beim
erneuten Speichern des Kontakts nicht verändert und nur maskiert angezeigt.

## Löschen und DSGVO-Auskunft

Löschen markiert den Kontakt als gelöscht (Endgültig löschen zur Bestätigung); die
Nachvollziehbarkeit bleibt gewahrt. DSGVO-Auskunft lädt die beim Kontakt gespeicherten
Daten als JSON-Datei herunter. Vor Herausgabe an die betroffene Person ist die Datei
inhaltlich zu prüfen, insbesondere auf Daten Dritter, die nicht in die Auskunft gehören.

## Was ist Vorschlag, was verbindlich

Von der KI vorgeschlagene Kontaktdaten aus einem Import sind stets zu prüfen, bevor sie
übernommen werden. Eine SEPA-Freigabe ist erst mit vollständigem Nachweis verbindlich;
ohne Mandat darf keine Lastschrift eingezogen werden.

## Häufige Fehler

- **IBAN oder BIC ungültig**: Formatprüfung schlägt fehl; Eingabe ohne Leerzeichen und
  mit korrektem Länderpräfix wiederholen.
- **SEPA-Freigabe lässt sich nicht speichern**: Datum der Erteilung, Erteilungsart oder
  Mandatsnachweis (Bitte das Mandat als PDF hinterlegen oder einen Vermerk eintragen)
  fehlt.
- **Speichern trotz möglicher Dublette**: Die Dublettenprüfung meldet einen ähnlichen
  Kontakt; Trotzdem speichern legt den Kontakt dennoch an, vorher die Trefferliste
  prüfen.
