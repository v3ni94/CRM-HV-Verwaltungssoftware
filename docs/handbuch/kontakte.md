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

Ein Kontakt gliedert sich in die Reiter Stammdaten, Beziehungen (Objekte, Einheiten,
Bevollmächtigte), Kommunikation (Telefonnummern, E-Mail-Adressen, Adressen, Anrufliste),
Tickets, Bankverbindungen, Dokumente, Portal-Freigaben, Notizen, Einwilligungen und
Ereignisprotokoll. Bei einer Person sind Vor- oder Nachname Pflicht, bei einer Firma der
Firmenname. Der Reiter Tickets zeigt alle Tickets, die diesem Kontakt zugeordnet sind,
einschließlich der erledigten (seit 1.23.0).

Weitere Felder (Ergänzung 27.09.2026, Abschnitt 4.1): Briefanrede als Freitext, Bundesland je
Adresse, Landesvorwahl, Vorwahl und Notiz je Telefonnummer, beliebig viele Datumsfelder mit
Art (Geburtstag, Sterbedatum, Hochzeit, Gründung, Sonstiges), je Bankkonto der Kontotyp
(Mietkonto, Bankkonto 1, Bankkonto 2, WEG-Konto, Rücklagenkonto, Kautionskonto,
Hausgeldkonto, Altkonto), das Kennzeichen Standardkonto und der Bankkontakt. Genau eine
E-Mail-Adresse darf Portal-Login-Adresse sein, genau ein Bankkonto Standardkonto; das Formular
und die API weisen weitere Markierungen ab. Notizen tragen Titel, Kategorie und eine
Wiedervorlage mit Datum. Der Reiter Ereignisprotokoll zeigt das Änderungsprotokoll des
Kontakts und erfordert das Recht audit:read.

## Beziehungen zu Objekten und Einheiten

Unten auf der Kontaktseite steht der Abschnitt Beziehungen zu Objekten und Einheiten: je
Zeile Objekt, Einheit, Art der Beziehung (Mieter, Eigentümer), Kategorie, Zeitraum und Status.
Die Zeilen entstehen aus den Verträgen des Kontakts, aus Eigentümerzuordnungen und aus den
Zuordnungen der objektakte-Übernahme; sie werden nicht von Hand gepflegt. Die Rollen Mieter
und Eigentümer werden aus denselben Quellen automatisch abgeleitet und ergänzen die von Hand
gesetzten Rollen, entfernen aber keine. Für Bestände, die vor 1.23.0 importiert wurden, lassen
sich die abgeleiteten Rollen einmalig über die API neu berechnen (POST
/contacts/roles/recompute, Recht Kontakte ändern).
Im Reiter Kommunikation steht zusätzlich der Abschnitt Portalzugang mit der Einladung in das
Portal (Einladungscode, Link und QR-Code, nur einmal sichtbar, Einzelheiten im Kapitel Portal).

Kontakte mit der Rolle Dienstleister zeigen im Reiter Beziehungen zusätzlich den Abschnitt
Objekte als Dienstleister: die Objekte, an denen der Kontakt als Kreditor verknüpft ist, mit
Gewerk, Beginn und Quelle (aus Buchung, von Hand, nachgezogen). Gepflegt wird die Verknüpfung
auf der Objektseite im Reiter Dienstleister/Handwerker.

## Bevollmächtigte und Zustellregel

Unter den Objektbezügen steht der Abschnitt Bevollmächtigte und Zustellregel. Ein Kontakt kann
einen oder mehrere Bevollmächtigte haben, zum Beispiel wenn ein Eigentümer die
Sondereigentumsverwaltung durch eine andere Person abwickeln lässt. Je Bevollmächtigtem gilt
eine Zustellregel:

* beide (Vorgabe): Vollmachtgeber und Bevollmächtigter erhalten E-Mails, Briefe und
  WEG-Einladungen,
* nur Bevollmächtigter: Schreiben gehen ausschließlich an den Bevollmächtigten,
* nur Vollmachtgeber: der Bevollmächtigte ist hinterlegt, erhält aber keine Schreiben.

Die Regel wirkt im Serienversand (Kommunikation, Zustellung je Zustellweg), bei
Serienbriefen aus Vorlagen und in der Empfängerliste einer Eigentümerversammlung. Ein
Serienbrief an den Bevollmächtigten nennt unter dem Namen "für <Vollmachtgeber>" und ist mit
beiden Kontakten verknüpft. Einzelbriefe und Einzelzustellungen an einen ausdrücklich gewählten
Kontakt bleiben unverändert. Eine abgelaufene Vollmacht (Gültigkeit bis) wird nicht mehr
beachtet; dann erhält der Kontakt selbst wieder alles.

Hinterlegen, Regel ändern und Vollmacht beenden setzen das Recht Kontakte ändern voraus;
jede Änderung steht mit altem und neuem Wert im Audit-Log des Vollmachtgebers. Auf der Seite
des Bevollmächtigten steht, für wen er bevollmächtigt ist. Ob eine Zustellung an den
Bevollmächtigten rechtlich als Zugang beim Eigentümer gilt, entscheidet die Plattform nicht;
im Zweifel Rechtsanwalt fragen.

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

## IBAN-Freigabe im Vier-Augen-Prinzip

Jede neue oder geänderte Bankverbindung (IBAN) steht zunächst im Status zur Freigabe.
Freigeben oder Ablehnen (mit Rückfrage) darf nur eine andere Person als die, die die
Bankverbindung erfasst hat (Recht Kontakte freigeben; bei eigener Erfassung zeigt die
Zeile selbst erfasst, Freigabe durch eine andere Person). Ein zweites Benutzerkonto
derselben Person zählt nicht als zweite Person.

Bis zur Freigabe wird die Bankverbindung nicht verwendet: nicht im SEPA-Mandat, nicht in
der Lastschrift, nicht in Zahlungsaufträgen und nicht im Rechnungsabgleich. Eine
abweichende IBAN auf einer Rechnung meldet der Rechnungseingang als IBAN weicht von den
freigegebenen Stammdaten ab (Kapitel Belegeingang); ein Zahlungsauftrag an eine nicht
freigegebene IBAN wird abgewiesen. Bankverbindungen, die vor Einführung der Freigabe
bestanden, gelten als freigegeben.

Vorschläge aus dem Portal (Datenänderung) oder aus Ticket-Mails enthalten nie eine
automatische Übernahme von Bankdaten; die IBAN ist von Hand mit Nachweis zu erfassen und
anschließend freizugeben.

## Sperre und Löschdatum

Kontakt sperren setzt das Sperrdatum automatisch; beim Aufheben der Sperre wird es gelöscht.
Die Kontaktliste zeigt mit dem Filter Nur gesperrte Kontakte die Sperrliste. Über das
Löschprofil (ein freigegebenes Aufbewahrungsprofil, Einstellungen) wird ein Löschdatum
vorgemerkt: Beginn ist das Sperrdatum, sonst der Tag der Zuordnung, bei Profilen mit Beginn
Jahresende der 31.12. dieses Jahres, darauf die Frist des Profils. Das Datum ist eine
Vormerkung und wird als fällig angezeigt (Betreiberentscheidung 26.09.2026). Die Löschung
selbst erfolgt manuell über Löschen im Vier-Augen-Prinzip; es gibt keinen automatischen
Löschlauf. Entwürfe von Aufbewahrungsprofilen werden abgewiesen.

## Löschen und DSGVO-Auskunft

Löschen markiert den Kontakt als gelöscht (Endgültig löschen zur Bestätigung); die
Nachvollziehbarkeit bleibt gewahrt. DSGVO-Auskunft lädt die beim Kontakt gespeicherten
Daten als JSON-Datei herunter. Vor Herausgabe an die betroffene Person ist die Datei
inhaltlich zu prüfen, insbesondere auf Daten Dritter, die nicht in die Auskunft gehören.

## Was ist Vorschlag, was verbindlich

Von der KI vorgeschlagene Kontaktdaten aus einem Import sind stets zu prüfen, bevor sie
übernommen werden. Eine SEPA-Freigabe ist erst mit vollständigem Nachweis verbindlich;
ohne Mandat darf keine Lastschrift eingezogen werden.

## Stammdaten direkt bearbeiten

Im Reiter Stammdaten lassen sich Anrede, Briefanrede, Titel, Vor- und Nachname beziehungsweise
Firma und Rechtsform, Position, Geburtsdatum, Sprache, bevorzugter Kanal und Notizen an Ort und
Stelle ändern (Stift am Feld oder "Bearbeiten" im Abschnittskopf, Recht Kontakte ändern).
Jede Änderung wird einzeln gespeichert und im Ereignisprotokoll festgehalten; Bedienung und
Konflikthinweis siehe Kapitel Stammdaten direkt bearbeiten. Adressen, Telefonnummern,
E-Mail-Adressen, Bankverbindungen, Typen, Rollen und Schlagworte werden weiterhin über
Bearbeiten im Formular gepflegt. Die Verknüpfungsleiste unter dem Kopf führt zu den Objekten,
Einheiten und Verträgen des Kontakts sowie zu seinen Tickets.

## Anrufen und E-Mail vom Handy

Die Reiter der Kontaktseite bilden am Handy eine Zeile, die sich seitlich wischen lässt;
alle zehn Reiter bleiben erreichbar, der aktive Reiter ist hervorgehoben. Im Kopf der
Kontaktseite stehen die Knöpfe Anrufen und E-Mail, sobald eine Telefonnummer oder eine
E-Mail-Adresse erfasst ist; sie öffnen die Telefon- oder Mail-App des Geräts mit der
Hauptnummer beziehungsweise der Hauptadresse. Im Reiter Kommunikation sind alle
Telefonnummern und E-Mail-Adressen antippbar. Die Einheitenseite verlinkt Mieter und
Eigentümer auf ihre Kontakte, von dort stehen dieselben Knöpfe bereit. Das CRM protokolliert
diese Anrufe nicht selbst; die Anrufliste im Reiter Kommunikation kommt weiter aus der
Telefonanlage.

## Häufige Fehler

- **IBAN oder BIC ungültig**: Formatprüfung schlägt fehl; Eingabe ohne Leerzeichen und
  mit korrektem Länderpräfix wiederholen.
- **SEPA-Freigabe lässt sich nicht speichern**: Datum der Erteilung, Erteilungsart oder
  Mandatsnachweis (Bitte das Mandat als PDF hinterlegen oder einen Vermerk eintragen)
  fehlt.
- **Speichern trotz möglicher Dublette**: Die Dublettenprüfung meldet einen ähnlichen
  Kontakt; Trotzdem speichern legt den Kontakt dennoch an, vorher die Trefferliste
  prüfen.
- **Freigeben der Bankverbindung abgewiesen**: Die Freigabe muss eine andere Person als
  die erfassende vornehmen, oder die Bankverbindung wartet nicht mehr auf eine Freigabe.
- **Lastschrift oder Zahlung nutzt die neue IBAN nicht**: Die Bankverbindung ist noch
  nicht freigegeben (Reiter Bankverbindungen, Freigabe).
- **Rufnummer in der Anrufliste maskiert**: Recht Kontakte lesen fehlt (Kapitel
  Kommunikation).

## Serienversand (Seite Kontakte, Serienversand)

Je Empfänger wird aus einer aktiven Dokumentvorlage ein eigenes Dokument erzeugt und abgelegt. Danach wird je Zustellweg eine Zustellung vorbereitet. Versendet wird nichts automatisch.
