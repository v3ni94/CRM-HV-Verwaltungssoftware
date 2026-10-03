# KI-Assistent im Chat

Stand: 29.09.2026. Die Chatblase unten rechts steht auf jeder Seite des CRM bereit und bezieht
sich immer auf die Seite, die gerade geöffnet ist. Regel AI-LOOKUP-01 in
`docs/rules/AI-LOOKUP-01.md`.

## Fragen zu Kontakten, Objekten, Verträgen und Tickets

Schreiben Sie Ihre Frage wie an eine Kollegin, zum Beispiel "Telefonnummer von Herrn
Kowalski", "Mietvertrag von Schmidt", "Einheit 07 im Lindenhof" oder "Status von Ticket 4711".
Die Plattform sucht selbst in Kontakten, Objekten, Einheiten, Verträgen und Tickets, jeweils nur
in den Bereichen, für die Sie eine Berechtigung haben. Unter der Antwort stehen die gefundenen
Datensätze als Links, ein Klick öffnet den Datensatz. Findet die Plattform nichts, sagt der
Assistent das ausdrücklich. Er erfindet keine Datensätze.

## Wo finde ich

Fragen wie "Wo finde ich die Markenfarben?" oder "Wo lege ich eine Rolle an?" beantwortet der
Assistent aus dem Handbuch und dem Verzeichnis der Einstellungsseiten, mit einem Link zur Seite.

## Der Chat kennt die geöffnete Seite

Der Assistent weiß, in welchem Menüpunkt, auf welcher Unterseite und in welchem Datensatz Sie
sich befinden. Das gilt für jede Seite des CRM, auch für Unterebenen wie die Versammlung einer
WEG, den Postausgang, eine Mieterhöhung oder eine einzelne Einstellungsseite. Die Kopfzeile des
Chats zeigt die Seite, zum Beispiel "Kalender" oder "Einstellungen / Mandant".

Beim Öffnen zeigt der Chat Vorschläge passend zur Seite und zum geöffneten Datensatz. Ein Klick
stellt die Frage. Beispiele:

- Start: "Was steht heute an?", "Fristen in den nächsten 7 Tagen"
- Kalender: "Welche Termine habe ich heute?", "Freien Termin nächste Woche finden",
  "Übergabetermine diese Woche", "Termin eintragen (Vorschlag)"
- Fristen: "Welche Fristen sind überfällig?", "Fristen in den nächsten 7 Tagen",
  "Frist eintragen (Vorschlag)"
- Bank: "Nicht zugeordnete Umsätze", "Offene Posten eines Debitors"
- Buchhaltung: "Offene Forderungen", "Frage zum Journal"
- Dokumente und DMS: "Dokument suchen", "Dokument zusammenfassen"
- WEG: "Beschlüsse dieser WEG", "Eigentümerversammlungen dieser WEG",
  "Stand der Erhaltungsrücklage", "Offene Posten dieser WEG"
- Vermietung: "Welche Einheiten stehen leer?", "Offene Mieterhöhungen"
- Aufträge und Tickets: "Offene Aufträge", "Überfällige Tickets"
- Einstellungen: "Diese Einstellung erklären", "Wo ändere ich das?"

Der Assistent bezieht sich auf den geöffneten Datensatz, auch ohne dass Sie den Namen nennen.

## Termine, Fristen, Dokumente, WEG, Bank

Auf diesen Seiten fragt die Plattform ihre eigenen Daten ab, ohne dass Sie einen Suchbegriff
nennen müssen. Zeitangaben wie "heute", "morgen", "diese Woche", "nächste Woche", "in 7 Tagen"
oder "12.10.2026 bis 14.10.2026" versteht die Plattform selbst. Beispiele:

- Termine: eigene und geteilte Einträge des CRM-Kalenders sowie die aus Stammdaten erzeugten
  Termine, die Sie lesen dürfen. "Freien Termin nächste Woche finden" nennt den nächsten
  Werktag ohne Eintrag. Google-Kalender werden im Chat nicht gelesen; die Antwort sagt das.
- Fristen: die Fristenliste (überfällig, fällig in N Tagen) und eigene Termine mit Erinnerung.
  Die Angaben sind Orientierung, keine rechtliche Fristberechnung.
- Dokumente: Suche nach Titel, Kategorie und Objekt, mit Link zum Dokument.
- WEG: Beschlüsse und Versammlungen der geöffneten Gemeinschaft; der Rücklagenstand stammt aus
  der letzten berechneten Jahresabrechnung. Liegt die Gemeinschaft außerhalb Ihrer
  Rechtsträgerzuordnung, sagt der Assistent das, statt einen Wert zu nennen.
- Mieterhöhungen, Aufträge: Stand, Beträge und Termine der Fälle mit Link.
- Bank und Buchhaltung: nicht zugeordnete Umsätze (Betrag, Gegenpartei, Verwendungszweck, nie
  eine IBAN) und offene Posten je Debitor mit Restbetrag.

Jede Abfrage prüft die Berechtigung, die auch die jeweilige Seite verlangt; ohne Berechtigung
nennt die Antwort den Bereich als nicht durchsucht. Je Bereich werden höchstens 10 Treffer
gezeigt.

## Gespräch mit Rückfragen

Jede Nachricht geht an den freigegebenen KI-Anbieter, mit Seite, Datensatz, den Treffern und
dem bisherigen Gespräch. Anmerkungen und Anschlussfragen ("Und seit wann?") versteht der
Assistent deshalb im Zusammenhang. Ist kein Anbieter freigegeben oder das Monatsbudget
erreicht, zeigt der Chat nur die Treffer der Plattformsuche und sagt das in einem Satz.

## Änderungen über den Chat

Bitten Sie zum Beispiel "Neue Telefonnummer von Kowalski: 0211 7654321", "Notiz an Kowalski:
Rückruf erbeten" oder "Lege ein Ticket für Kowalski an", erstellt der Assistent nur einen
Vorschlag. Die Karte zeigt, was geändert würde. Erst mit "Bestätigen und übernehmen" wird die
Änderung gespeichert, über denselben Weg wie in der Kontaktakte oder beim Ticket anlegen, mit
Änderungshistorie. "Verwerfen" ändert nichts. Bankverbindungen ändert der Chat nie; sie werden
in der Kontaktakte erfasst und laufen dort über die Vier-Augen-Freigabe.

Termine und Fristen: "Trag einen Übergabetermin mit Kowalski am 05.10.2026 um 10:00 ein" oder
"Trag die Frist Widerspruch zum 09.10.2026 ein" erzeugt einen Vorschlag mit Datum, Uhrzeit,
Beteiligten und Objekt. Nach der Bestätigung steht der Eintrag in Ihrem eigenen CRM-Kalender;
der Fristeintrag trägt Erinnerungen (ein Tag und sieben Tage vorher) und erscheint in der
Fristenliste. Es werden keine Einladungen versendet und kein Google-Termin angelegt; Datum und
Uhrzeit können Sie vor dem Bestätigen korrigieren. Fehlt das Datum in Ihrer Nachricht, fragt
der Assistent danach.

Sind die Unterlagen einer Frage zu umfangreich für den KI-Anbieter, kürzt die Plattform zuerst
gefundene Dokumente und den Gesprächsverlauf, nie Ihre Frage. Reicht das nicht, sehen Sie die
Trefferliste mit einem Hinweis.

## Datenschutz und Protokoll

Telefonnummern, E-Mail-Adressen und Bankverbindungen verlassen die Plattform nur maskiert. Die
Trefferliste mit den vollständigen Angaben sehen Sie im Chat, sie kommt nicht von der KI. Alle
Fragen, Antworten, Links und Vorschläge bleiben im Assistentenprotokoll nachvollziehbar.

## Grenzen

- Für Übergabeprotokolle (Mängel, Zählerstände, Unterschriften), Rechnungen, Abrechnungen und
  Mahnläufe gibt es Vorschläge, aber noch keine eigene Datenabfrage; der Assistent kennt dort
  nur Seite und Datensatz.
- Eine Zuständigkeit je Frist ist nicht hinterlegt; "Fristen nach Zuständigem" kann der
  Assistent deshalb nicht beantworten.
- Der Chat verschiebt keine Termine und verschickt keine Einladungen; das bleibt in der
  Kalenderseite.
- Die Plattform wählt die Suchbereiche nach festen Regeln; die KI selbst löst keine Abfragen aus.

## Ablehnungsgrund und Kostenübersicht (Nachtrag 30.09.2026)

* Beim Ablehnen eines Kontakt- oder Chat-Vorschlags kann ein Grund eingetragen werden (freiwillig, höchstens 2.000 Zeichen). Er wird im Protokoll gespeichert und als Lernbeispiel verwendet.
* Die Kostenübersicht in den KI-Einstellungen zeigt je Aufgabe zusätzlich die Zahl der Läufe und der Token im laufenden Monat.
* Vor dem Aufruf eines externen Anbieters werden Straßen mit Hausnummer und Postleitzahl mit Ort durch Platzhalter ersetzt, Namen bleiben erhalten (Regel AI-MASK-02).

## Weitere Aktionen und Folgeschritte (Nachtrag 30.09.2026)

Der Assistent bereitet zusätzlich vor, jeweils als Vorschlag mit Bestätigung im Chat:

* Objekt anlegen: Nennen Sie Objektnummer, Namen, Verwaltungsart (Miete, WEG oder WEG mit SEV) und gegebenenfalls die Anschrift in Ihrer Nachricht. Das Objekt entsteht im Status Übernahme.
* Dokument ablegen: Hängen Sie das Dokument an die Nachricht an und nennen Sie Objekt, Einheit oder Kontakt.
* Portaleinladung vorbereiten: Der Zugang wird mit der E-Mail-Adresse aus der Kontaktakte angelegt. Es wird nichts versendet; das Einladungsschreiben erzeugen Sie danach in der Kontaktakte.
* Brief aus Vorlage: Nennen Sie Vorlage und Empfänger. Der Brief wird als Entwurf abgelegt und nicht versendet.

Nach einer Übernahme zeigt der Chat mögliche nächste Schritte, zum Beispiel Portaleinladungen, Verträge anlegen oder fehlende Daten per Formular anfordern. Jeder Schritt ist eine eigene Aktion.

Am Kontakt gibt es den Reiter Assistent, am Objekt den Bereich Assistent (Schaltfläche oben rechts). Beide öffnen den Chat mit dem geöffneten Datensatz als Kontext.

Kosten: Liefert das kleine Modell eine ungültige Antwort oder eine Konfidenz unter der eingetragenen Schwelle, fragt die Plattform einmal das große Modell. Beide Stufen erscheinen getrennt mit ihren Kosten im Lauf. Ist das Monatsbudget erreicht, sperrt die Plattform weitere Läufe und benachrichtigt die Personen mit Recht auf die Einstellungen.

## Objekt anlegen: weitere Angaben und Personenabgleich (Nachtrag 01.10.2026)

Vor dem Bestätigen eines Objektvorschlags zeigt die Tabelle "Personenabgleich (Vorschau)" nach Klick auf "Abgleich anzeigen", ob eine Person mit einem vorhandenen Kontakt verknüpft würde, nur vorgeschlagen wird oder neu entsteht. Dabei wird nichts angelegt. Unter "Weitere Angaben zum Objekt" können Bankkonten (IBAN, Inhaber, Art, Standardkonto), Umlageschlüssel (vorhandener Schlüssel nur mit Werten, neuer Schlüssel mit Name, Einheit und Art; Werte als Zeilen "01=70,5"), die Übernahme der Debitorenkonten und die Verknüpfung der Quelldokumente gewählt werden. Alles wird mit "Bestätigen und übernehmen" in einem Schritt angelegt, bei einem Fehler entsteht nichts. "Rückgängig" entfernt die Anlage wieder, solange nichts darauf gebucht oder zugeordnet wurde.

## Verwendete Nachschlagewerkzeuge

Ist für den KI-Anbieter das Nachschlagen eingeschaltet (Einstellungen, KI-Anbieter, Stufe mit
`tool_use`, Standard aus), kann der Assistent vor der Antwort selbst in den Daten nachsehen:
Kontakte, Verträge, offene Posten, Dokumente, Termine und Kontenplan. Er sieht dabei nie mehr
als Sie: Werkzeuge ohne Ihre Berechtigung liefern nichts. Unter der Antwort steht
"Verwendete Nachschlagewerkzeuge" mit Werkzeug, Suchtext (E-Mail, Telefon und Anschrift
maskiert) und Trefferzahl. Je Frage sind höchstens sechs Abfragen möglich. Die Antwort bleibt
ein Vorschlag; Änderungen entstehen weiterhin nur über bestätigte Vorschläge.

## Nachschlagewerkzeuge: Schalter, Verlauf und Links (Nachtrag 01.10.2026)

* Schalter: Unter Einstellungen, KI-Anbieter gibt es je Stufe (klein, groß) die Option "Werkzeuge (Tool Use) für Stufe ... erlauben". Standard aus. Wie alle Anbieterfelder hebt jede Änderung eine bestehende Freigabe auf; wirksam wird sie erst nach der Freigabe im Vier-Augen-Prinzip mit AVV-Nachweis. Ob und für welchen Mandanten das Nachschlagen eingeschaltet wird, ist eine offene Entscheidung des Betreibers (AC08-01).
* Verlauf: Auch in einem wieder geöffneten Chat steht unter jeder Antwort, welche Nachschlagewerkzeuge verwendet wurden, mit Suchtext und Trefferzahl.
* Links: Treffer der Werkzeuge (Kontakt, Vertrag, Dokument, Objekt und weitere) erscheinen unter der Antwort als Links in die jeweilige Akte. Die Links erzeugt die Plattform nach Prüfung Ihrer Rechte, nicht das Modell. Kontakttreffer zeigen keine Telefonnummer und keine E-Mail-Adresse.

## KI-Einstellungen: drei Schalter (Welle 24, AM04)

Unter Einstellungen, KI sind die Schalter "Einzel-Einordnung von E-Mails", "Stammdatenvorschläge" und "KI-Aufgaben aus Regeln" sichtbar und mit dem Recht zur Pflege der KI-Einstellungen schaltbar. Alle drei bleiben ausgeschaltet, bis Sie sie bewusst einschalten. KI liefert in allen Fällen nur Vorschläge; eine Übernahme erfolgt durch die Mitarbeiterin oder den Mitarbeiter.
