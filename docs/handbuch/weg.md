# WEG (Versammlung, Beschlüsse, Abrechnung, Prüfauftrag)

## Zweck

Der Bereich WEG (Menü Finanzen, WEG) führt die laufende Verwaltung der Gemeinschaften der
Wohnungseigentümer: Wirtschaftspläne, Hausgeldabrechnungen, Eigentümerversammlungen,
Sonderumlagen und die Beschluss-Sammlung. Die Stammdaten der Gemeinschaften (Objekt,
Einheiten, Miteigentumsanteile, Eigentumsverhältnisse) stehen im Bereich Objekte (Kapitel
Objekte und Einheiten, Kapitel Verträge).

Ausgabe und Buchung von WEG-Abrechnungen sind bis zur Freigabestufe G4 gesperrt; ein
Hinweis auf jeder WEG-Seite erinnert daran. Bis dahin endet der Ablauf einer
Hausgeldabrechnung mit dem erfassten Beschluss.

## Einstieg

Die Seite WEG-Verwaltung listet die WEG-Objekte; WEG-Objekte öffnen führt zur Objektliste
mit dem Reiter WEG. Die Seite einer Gemeinschaft zeigt die Listen Wirtschaftspläne,
Hausgeldabrechnungen, Versammlungen, Sonderumlagen, Darlehen, Versicherungsfälle, Größere
Maßnahmen und Beiratsprüfungen mit jeweils einer Schaltfläche zum Anlegen, den Link zu den
Einsichtsanfragen sowie darunter die Beschluss-Sammlung. Voraussetzung ist ein Buchungskreis der
GdWE; fehlt er, erscheint der Hinweis Für die Gemeinschaft ist noch kein Buchungskreis
angelegt (Kapitel Buchhaltung).

## Wirtschaftsplan

Plan anlegen mit Jahr. Der Plan erhält Positionen mit Bezeichnung, Betrag, Schlüssel
(Umlageschlüssel des Objekts, zum Beispiel MEA), Komponente (Hausgeld oder
Erhaltungsrücklage) und Grundlage. Berechnen erstellt den Gesamt- und Einzelwirtschaftsplan:
je Einheit Hausgeld jährlich und monatlich sowie Rücklage jährlich und monatlich (zum
Beispiel 1.200,00 EUR nach MEA auf eine Einheit ergibt 100,00 EUR je Monat).

Ablauf der Status: Entwurf, berechnet, intern freigegeben (zweite Person, nicht der
Ersteller), beschlossen. Der Beschluss wird mit Beschlussdatum über Beschluss zu diesem
Stand erfassen aufgenommen; er ist an den berechneten Stand gebunden. Ändert sich der Plan
danach, ist eine neue Version nötig, der alte Beschluss bleibt an der alten Version.

Nach dem Beschluss zeigt Vorschau Vorschüsse je Einheit und Komponente das
Eigentumsverhältnis zum Wirksamkeitsbeginn, den bisherigen und den beschlossenen monatlichen
Sollbetrag und die Aktion (anlegen, unverändert, kein Betrag, kein Eigentumsverhältnis).
Vorschau bestätigen und übernehmen legt die Sollbeträge ab Wirksamkeitsbeginn in den
Eigentumsverhältnissen an (Kapitel Verträge, Abschnitt Sollbeträge) und schließt den
vorherigen Sollbetrag am Vortag; die Bestätigung muss eine andere Person als der Ersteller
des Plans geben, die Übernahme ist an den berechneten Stand gebunden und wird je Plan nur
einmal ausgeführt (Regel W02). Die Zeilen sind Stammdaten der Verträge und keiner
Freigabestufe unterworfen; die monatlichen Sollstellungen daraus erzeugt erst der
Sollstellungslauf hinter G1. Bereits gebuchte Monate ab Wirksamkeitsbeginn zeigt die
Vorschau als Hinweis; sie werden nicht erneut nachgefordert, eine Anpassung ist eine
Korrektur der Buchhaltung.

## Hausgeldabrechnung

Abrechnung anlegen mit Jahr. Kostenpositionen werden mit Bezeichnung, Betrag, Schlüssel,
Kostenkonto und Grundlage erfasst; eine Position ohne Kostenkonto sperrt die Freigabe
(Hinweis Freigabe gesperrt (Abrechnungspaket W12)). Berechnen ermittelt je Einheit den
Kostenanteil, die beschlossenen Vorschüsse (Soll), die Abrechnungsspitze beziehungsweise
Anpassung sowie den Rückstand als Information. Rückstände bleiben eigene Forderungen aus
den Sollstellungen; der Gesamtbetrag ist nur Information. Die Zeile Rücklage zeigt
Anfangsbestand, eingegangene Beiträge, Entnahmen, Zinsen und Endbestand sowie offene
Beiträge (nicht verfügbar); sie ist die Grundlage des Vermögensberichts.

Die KI-Plausibilität liefert Hinweise ohne Wirkung auf die Abrechnung: Sie nennt keine
Beträge und keine Korrekturen, die Prüfung und Entscheidung bleiben bei einer Person.

Status: Entwurf, berechnet, intern freigegeben, Beirat geprüft (über den Prüfauftrag, siehe
unten), beschlossen (Beschluss zu diesem Stand erfassen), ausgegeben, fällig, gebucht,
gesperrt. Ausgeben, Fällig stellen und Ergebnis buchen (Korrektur nur per Storno) verlangen
die Freigabestufe G4 und werden bis dahin abgewiesen. Neue Version legt eine Folgeversion
an; der Beschluss bleibt an der alten Version.

### Überleitungsrechnung Gesamtgeldfluss (W04)

Die Abrechnungsseite zeigt im Abrechnungspaket die Überleitungsrechnung Gesamtgeldfluss
(Rechte wie die übrige WEG-Arbeit: Buchhaltung lesen, Erklärungen erfassen mit Buchhaltung
anlegen):

- Bank und Kasse: je Konto Anfangsbestand, Zuflüsse, Abflüsse, Endbestand des
  Abrechnungsjahres. Umbuchungen zwischen eigenen Bank- und Kassenkonten zählen weder als
  Zu- noch als Abfluss.
- Brücke von den Zahlungsausgängen über die gezahlten Kosten zu den gebuchten und den
  verteilungsrelevanten Kosten: davon Rücklage, davon Darlehensposten, davon Erstattungen an
  Eigentümer, davon Durchlauf und Sonstiges, abzüglich Erstattungen auf Kosten, Zeitbezug
  Kreditorenbuchung gegen Zahlung. Diese Positionen ermittelt die Plattform aus den
  gebuchten Buchungssätzen.
- Erklärte Differenzen: Zeilen mit Art (Heizkostenabgrenzung, Zeitbezug Kreditorenbuchung,
  Vorjahr, Sonstige erklärte Differenz), Betrag mit Vorzeichen und Begründung. Erklärungen
  speichern ist nur im Status Entwurf oder berechnet möglich (Hinweis Erklärungen nur vor
  der internen Freigabe).
- Unerklärte Differenz: der verbleibende Rest. Solange er nicht 0,00 EUR ist, weist das
  Abrechnungspaket die interne Freigabe mit dem Hinweis Überleitungsrechnung: unerklärte
  Differenz ab. Dasselbe gilt, wenn Anfangsbestand plus Zu- und Abflüsse nicht den
  Endbestand ergeben.

Welche Erklärungsarten fachlich ausreichen und wie Zins und Tilgung von Darlehen in der
Jahresabrechnung verteilt werden, ist Betreiberentscheidung mit Rechts- und Steuerberatung
(offener Punkt M24-03). Bis dahin werden Darlehensposten nur ausgewiesen.

## Eigentümerversammlung

Versammlung anlegen mit Termin. Auf der Versammlungsseite:

- Tagesordnung: TOP hinzufügen mit Tagesordnungspunkt und Beschlussvorschlag.
- Einladung erfassen mit Datum Einladung versandt am; die Ladungsfrist wird geprüft, bei
  verkürzter Frist ist die Dringlichkeit anzugeben. Versendet wird die Einladung außerhalb
  der Plattform.
- Anwesenheit und Stimmen: je Eigentümer anwesend oder nicht anwesend, per Vollmacht;
  die Kopfzeile zeigt zum Beispiel 8 vertreten, davon 2 per Vollmacht. Stimmen werden je
  TOP als Ja, Nein oder Enthaltung erfasst.
- Mehrheitsregeln dieser Gemeinschaft: Bezeichnung, Stimmprinzip (Kopfprinzip,
  Miteigentumsanteile, Objektprinzip), Anteil der abgegebenen Stimmen in Prozent (mehr
  als oder mindestens), Mindestanteil aller MEA, Allstimmigkeit, Fundstelle (Gesetz,
  Vereinbarung), Gültig ab. Ohne Regel gilt die einfache Mehrheit der abgegebenen Stimmen.
- Auszählen zeigt Ja, Nein, Enthaltung und die Mehrheitsgrundlage. Die Auszählung ist ein
  Vorschlag; maßgeblich ist die Verkündung. Qualifizierte Mehrheiten werden nicht
  automatisch ausgewertet, die Schaltfläche Mehrheit manuell prüfen weist darauf hin.
- Verkünden übernimmt das verkündete Ergebnis (angenommen oder abgelehnt) als Beschluss
  mit Nummer in die Beschluss-Sammlung. Je Tagesordnungspunkt lässt sich der
  Beschlussgegenstand wählen (Wirtschaftsplan, Jahresabrechnung, Erhaltung, Bauliche
  Veränderung, Verwalterbestellung, Sonstiges); dann zeigt die Plattform nach der
  Verkündung die Mehrheitsprüfung (siehe Mehrheitsregeln je Beschlussgegenstand).

Status der Versammlung: geplant, eingeladen, eröffnet, geschlossen. Über die Schnittstelle
stehen außerdem bereit: Umlaufbeschluss in Textform und Vermerk einer technischen Störung
bei Online-Teilnahme.

### Umlaufbeschluss

Unter der Beschluss-Sammlung der Gemeinschaft lässt sich ein Umlaufbeschluss erfassen:
Gegenstand, Beschlusstext, Datum der Feststellung, je Eigentümer die in Textform
eingegangene Stimme mit Kanal (E-Mail, Portal, Brief, Sonstiges) und Eingangszeitpunkt, das
Fristende für die Stimmabgabe und der Nachweis der Textform als Datei. Standard ist die
Allstimmigkeit: positiv nur, wenn alle Eigentümer fristgerecht mit Ja gestimmt haben.

Die zugelassene Mehrheit "einfache Mehrheit" steht nur zur Verfügung, wenn der Schalter des
Mandanten gesetzt ist (Schnittstelle `PUT /hoa/circular-lower-majority`, Standard aus,
Freigabe erst nach Rechtsprüfung). Dann sind der zulassende Beschluss aus der
Beschluss-Sammlung (Absenkungsbeschluss, positiv gefasst und vor dem Umlaufbeschluss), das
Fristende und der Beschlussgegenstand Pflicht. Die Plattform zählt nach der Mehrheitsregel
des Mandanten für den Gegenstand (Köpfe, Miteigentumsanteile oder Einheiten), lässt
verspätete Stimmen unberücksichtigt und stellt das Ergebnis mit Auszählung, Verweis auf den
zulassenden Beschluss und dem Vermerk "zu prüfen" in der Beschluss-Sammlung fest. Die
Zulässigkeit der Absenkung ist eine rechtliche Einschätzung und keine Feststellung des
Systems (docs/rules/M25-02-umlaufbeschluss.md).

### Protokollentwurf

Protokollentwurf erzeugen (Recht Buchhaltung anlegen) erstellt aus Tagesordnung, Anwesenheit
mit Stimmrechten, Beschlusstexten, Auszählung, Verkündung und Unterschriftszeilen ein PDF
auf dem Briefbogen des Mandanten und legt es als Entwurfsdokument an der Versammlung ab
(Entwurf herunterladen, Protokollentwurf neu erzeugen). Der Entwurf hat keine Rechtsfolge
und ersetzt nicht das unterschriebene Protokoll; dieses bleibt getrennt verknüpft und wird
nie überschrieben.

### Protokollabschluss

Nach der Versammlung (Status eröffnet) trägt eine Person unter Protokollabschluss die
Dokument-ID des unterschriebenen Protokolls ein und wählt Abschluss beantragen (Recht
Buchhaltung freigeben). Ab dann sind Tagesordnung, Anwesenheit, Stimmabgabe, Verkündung und
Beschlussfrist gesperrt. Eine zweite Person bestätigt mit Abschluss bestätigen; dieselbe
Person kann nicht bestätigen. Danach ist die Versammlung geschlossen und das Ereignis
meeting.closed wird an abonnierte Webhooks geliefert. Ein offener Antrag kann mit Antrag
zurückziehen aufgehoben werden. Eine Frist für das Protokoll berechnet die Plattform nicht;
sie zeigt nur einen Hinweis (offene Frage R07-01).

### Beschlussfrist virtueller Versammlungen

Bei einer virtuellen Versammlung kann unter Beschlussfrist der virtuellen Versammlung ein
Datum mit Quelle (Beschluss oder Gemeinschaftsordnung mit Fundstelle, mindestens drei
Zeichen) eingetragen werden. Die Frist wird eingetragen, nicht berechnet; bei anderen
Versammlungsarten weist die Plattform sie ab. Sie erscheint in der Fristenliste (Menü
Fristen, Typ Beschlussfrist virtuelle Versammlung) mit 7 Tagen Vorfrist als Orientierung,
zu prüfen; rechtliche Fristberechnung bleibt Aufgabe der Sachbearbeitung.

## Mehrheitsregeln je Beschlussgegenstand

Unter Einstellungen, WEG werden Mehrheitsregeln je Beschlussgegenstand gepflegt (Lesen mit
Buchhaltung lesen, Anlegen, Ändern, Freigeben und Deaktivieren mit Buchhaltung freigeben):

- Beschlussgegenstand (Wirtschaftsplan, Jahresabrechnung, Erhaltung, Bauliche Veränderung,
  Verwalterbestellung, Sonstiges), Geltung (Alle Gemeinschaften oder eine Gemeinschaft als
  Vorrangregel), Mehrheit (einfache Mehrheit, qualifiziert 2/3, qualifiziert 3/4,
  allstimmig, eigener Bruch mit Zähler und Nenner), Zählbasis (Köpfe, Miteigentumsanteile,
  Einheiten), Fundstelle (Pflicht, zum Beispiel Gemeinschaftsordnung § 7).
- Freigabe durch eine zweite Person (nicht Anleger oder letzter Bearbeiter); jede Änderung
  hebt die Freigabe auf. Deaktivieren erhält die Regel im Verlauf.
- Fehlt eine Regel, gilt die Standardregel einfache Mehrheit nach Köpfen mit dem Hinweis
  Standardregel, nicht fachlich freigegeben.

Die Mehrheitsprüfung vergleicht die erfasste Auszählung mit der Regel und ergibt erreicht,
nicht erreicht oder nicht prüfbar (zum Beispiel Beschlussgegenstand nicht angegeben,
Auszählung unvollständig, Zählbasis weicht ab, Gesamtzahl der Stimmberechtigten fehlt bei
Allstimmigkeit). Enthaltungen werden bei einfacher und qualifizierter Mehrheit nicht
gezählt; ob dies der Regel der Gemeinschaft entspricht, ist fachlich zu prüfen. Das Ergebnis
ist Anzeige und Protokollvermerk, der Beschlussstatus wird nie automatisch geändert; die
Verkündung bleibt bei der Versammlungsleitung. Die Prüfung ist am Beschluss in der
Beschluss-Sammlung sichtbar. Die ältere Mehrheitsregel je Gemeinschaft (Abschnitt
Eigentümerversammlung) bleibt daneben bestehen.

## Beschluss-Sammlung

Die Beschluss-Sammlung zeigt Nr., Datum, Gegenstand, Art (Versammlung, Umlaufbeschluss,
Gericht, extern erfasst) und Status (positiv gefasst, abgelehnt, bestandskräftig,
angefochten, für ungültig erklärt, rechtskräftig, nichtig). Beschlüsse aus Versammlungen
vor der Plattformnutzung werden als extern erfasst aufgenommen; der Wirksamkeitsstatus
wird nachgeführt (zum Beispiel angefochten, bestandskräftig). Beschlüsse zu Wirtschaftsplan,
Hausgeldabrechnung und Sonderumlage sind an den jeweils berechneten Stand gebunden.

## Sonderumlage

Sonderumlage anlegen mit Zweck, Gesamtsumme, Schlüssel, erster Fälligkeit und Anzahl
Raten. Berechnen verteilt je Einheit Anteil und Raten. Nach Beschluss zu diesem Stand
erfassen übernimmt Raten als Sollstellungen übernehmen die Raten als Vertragszahlungen
der Eigentümer. Der Bericht Zweckgebundener Bestand zeigt beschlossen, gefordert,
eingegangen, offen, verwendet und verbleibend zweckgebunden.

Ein Änderungsbeschluss legt eine neue Version mit neuer Gesamtsumme, Grund und dem Monat
an, ab dem die Differenz fällig wird; die übernommene Version bleibt unverändert, die
Differenz je Einheit wird als Nachforderung oder Gutschrift fällig. Status: Entwurf,
berechnet, beschlossen, Raten übernommen, verworfen.

## Darlehen, Versicherungsfälle, größere Maßnahmen

Die Seite der Gemeinschaft führt drei weitere Listen (Lesen mit Buchhaltung lesen, Erfassen
mit Buchhaltung anlegen). Alle drei erfassen und weisen nach; sie buchen nichts, zahlen
nichts und verteilen nichts in die Abrechnung. Ein Betrag zählt nur, wenn die Position auf
eine gebuchte Journalbuchung desselben Buchungskreises verweist (Kennzeichen gebucht);
Positionen ohne Buchung stehen als ohne Buchung dabei. Dokumente werden am Datensatz
verknüpft.

- Darlehen anlegen: Darlehensgeber, Darlehensbetrag, Zinssatz in Prozent, Laufzeit in
  Monaten, Rate, Beginn, Zweck, Darlehenskonto. Positionen je Art Auszahlung, Tilgung,
  Zins, Gebühr mit Datum, Betrag, Journalbuchung (ID) und Hinweis. Die Seite zeigt Stand
  laut gebuchten Positionen, Saldo Darlehenskonto und Differenz; Status Entwurf, laufend,
  getilgt, abgeschlossen. Darlehensposten fließen als solche in die Überleitungsrechnung
  ein.
- Versicherungsfall anlegen: Bezeichnung, Schadensdatum, Versicherer, Versicherungsschein,
  Schadensnummer, Selbstbehalt, Regressgegner. Positionen je Art Schadenskosten,
  Versicherungsleistung, Selbstbehalt, Regress, Zahlung an Eigentümer (nur mit
  Eigentumsvertrag). Die Seite zeigt die Belastung der Gemeinschaft (gebucht); Status
  gemeldet, anerkannt, abgelehnt, reguliert, abgeschlossen (Status setzen).
- Maßnahme anlegen: Bezeichnung, Kostenrahmen, Einordnung (offen, Erhaltung, bauliche
  Veränderung) mit Sachverhalt und Rechtsgrund als Text, Beschluss (Verweis). Finanzierung
  mit Quelle (Erhaltungsrücklage, Sonderumlage, Darlehen, Sonstige) und Betrag; die Seite
  zeigt finanziert und offen. Status geplant, beschlossen, in Ausführung, abgeschlossen,
  aufgehoben.

Die Einordnung einer Maßnahme wird als Sachverhalt erfasst, nie aus einem Kontenvorschlag
abgeleitet. Steuer- und Umlagebehandlung je Fall sowie die Verteilung von Zins und Tilgung
in der Jahresabrechnung sind vor G4 zu entscheiden (offener Punkt M24-03).

## Prüfauftrag (Beirat)

Die Belegprüfung durch den Verwaltungsbeirat wird als Prüfauftrag je Hausgeldabrechnung
geführt. Die Seite Beiratsprüfung (Liste Beiratsprüfungen auf der Seite der Gemeinschaft)
zeigt Zeitraum, Stichprobe oder Vollprüfung, Gesamtstatus, die Prüfpositionen mit Status
(offen, geprüft, Rückfrage, beanstandet, veraltet) und die Vermerke, Fragen und Antworten.
Das Anlegen eines Prüfauftrags, der Prüfpositionen und des Prüfberichts erfolgt zum Stand
dieses Handbuchs über die Schnittstelle (Recht Buchhaltung anlegen); die Maske dient der
Ansicht, der Beantwortung und dem Beiratszugang.

Beiratszugang und Rückfragen: Unter Beiratszugang anlegen wird ein Prüfer (Kontakt aus dem
Prüfauftrag) eingeladen (Recht Kontakte ändern). Hat der Kontakt bereits einen Portalzugang,
zum Beispiel als Eigentümer, wird er um die Beiratsrolle ergänzt; sonst wird er wie ein
Eigentümer eingeladen, der Einladungscode erscheint nur einmal für das Einladungsschreiben.
Zugang beenden entzieht die Rolle, Vermerke und Rückfragen bleiben erhalten. Rückfragen des
Beirats aus dem Portal (Kapitel Portal, Prüfungsraum) werden mit Antwort senden beantwortet;
die Frage wird nie überschrieben, eine zweite Antwort ist nicht möglich. Der Beirat sieht
nur diesen Prüfauftrag, die ausgewählten Positionen und die dazu freigegebenen Belege; der
Abruf eines Belegs wird als Indiz vermerkt. Der Beirat bucht nichts, gibt nichts frei und
ändert keine Abrechnung. Das Ergebnis der Beiratsprüfung entspricht dem Status Beirat
geprüft der Hausgeldabrechnung; eine Beiratsstellungnahme ist kein Testat.

Dazu gehört das Abrechnungspaket (W12): Eine Hausgeldabrechnung wird nur freigegeben, wenn
jede Kostenposition einem Kostenkonto zugeordnet ist, die Belege zuordenbar sind und die
Überleitungsrechnung ohne unerklärte Differenz schließt.

## Einsichtsanfragen außerhalb des Portals

Solange das Eigentümerportal keine Einsicht in die Verwaltungsunterlagen bietet,
protokolliert die Seite Einsichtsanfragen (Link Einsichtsanfragen außerhalb des Portals
protokollieren auf der Seite der Gemeinschaft) Anfragen von Eigentümern oder Vertretern.
Rechte: Lesen mit WEG lesen, Erfassen und Bearbeiten mit WEG ändern (eigene
Berechtigungsressource hoa).

1. Einsichtsanfrage erfassen: Antragsteller (Kontakt suchen), Datum Antrag, Umfang
   (Abrechnung, Belege, Verträge, Beschlüsse) und Umfang als Freitext.
2. Status angefragt. Freigeben (Benutzer und Zeit werden vermerkt) oder Ablehnen (Grund
   Pflicht).
3. Bereitstellungspaket erzeugen: Aus den Dokumenten des Objekts sind nur die für
   Eigentümer freigegebenen wählbar (nicht freigegebene sind gekennzeichnet). Das Paket ist
   eine ZIP-Datei mit Index (Dateiname, Dokumentkategorie, Datum, Prüfsumme SHA-256) und
   wird als Dokument an der Anfrage abgelegt; jeder Download wird protokolliert.
4. Bereitstellen mit Bereitstellungsart Portal, Datenträger oder Einsicht vor Ort (außer
   vor Ort ist das Paket Voraussetzung), danach Als abgerufen vermerken (der protokollierte
   Download setzt dies automatisch) und Abschließen.
5. Rückfrage vermerken hält Fragen und Antworten fest. Der Verlauf zeigt Statuswechsel,
   Rückfragen, Paket erzeugt und Paket abgerufen.

Fristen und Umfang der Einsicht sind Entscheidung des Verwalters (offener Punkt M25-05);
die Plattform berechnet keine Frist und leitet aus einem Status keinen Anspruch ab.

## Häufige Fehler

- Für die Gemeinschaft ist noch kein Buchungskreis angelegt: Buchungskreis der GdWE
  anlegen (Kapitel Buchhaltung).
- Keine Einzelbeträge nach Berechnen: Miteigentumsanteile (MEA) der Einheiten fehlen oder
  gelten nicht für den Zeitraum.
- Intern freigeben abgewiesen: Ersteller und Freigebende müssen verschiedene Personen sein.
- Ausgeben oder Ergebnis buchen abgewiesen: Freigabestufe G4 ist geschlossen.
- Interne Freigabe abgewiesen mit Überleitungsrechnung: unerklärte Differenz: Erklärte
  Differenzen mit Begründung erfassen oder fehlende Buchungen prüfen; Erklärungen sind nur
  im Status Entwurf oder berechnet möglich.
- Darlehensposition zählt nicht: Die Position verweist auf keine gebuchte Journalbuchung
  desselben Buchungskreises.
- Beschlussfrist abgewiesen: Nur für virtuelle Versammlungen und nur mit Quelle.
- Mehrheitsprüfung nicht prüfbar: Beschlussgegenstand fehlt am TOP, Auszählung
  unvollständig oder Zählbasis der Regel weicht vom Stimmprinzip der Auszählung ab.
- Bereitstellungspaket enthält ein Dokument nicht: Das Dokument ist nicht für Eigentümer
  freigegeben (Sichtbarkeit am Dokument, Kapitel Dokumente und DMS).

## Beiratsprüfung und Einsicht: Ergänzungen (Stand 30.09.2026)

Hinweis: Diese Funktionen sind zunächst über die Schnittstelle verfügbar, eine Bedienoberfläche im CRM folgt.

* Prüfauftrag: Im Feld Berechtigungsnachweis wird der Beschluss oder Auftrag des Beirats vermerkt, im Feld Datenstand das Stichtagsdatum der Daten. Beides erscheint im Prüfbericht. Ein nicht vorhandener Beirat wird nicht unterstellt, der Nachweis ist optional.
* Prüfpositionen lassen sich nach Betrag, fehlendem Beleg, Risikohinweis und Prüfstatus filtern. Der Risikohinweis ist ein Vermerk der Prüfenden.
* Jede Änderung einer Prüfposition steht mit altem und neuem Wert im Verlauf der Position.
* Ein Prüfbericht kann je Version einmal bestätigt werden. Die Bestätigung ist kein Beschluss, keine Entlastung und keine Zahlungsfreigabe.
* Ein Einsichtspaket kann befristet werden (1 bis 365 Tage) und lässt sich mit Begründung widerrufen. Danach ist der Abruf gesperrt, bis ein neues Paket bereitgestellt wird. Die Frist ist eine Produktfunktion und keine rechtliche Frist.

## Rücklagen, Kosten aus der Buchhaltung, Einzelabrechnung (Stand 30.09.2026)

* Zweckrücklagen legen Sie je Gemeinschaft an (Name, Zweck, Konto). Rücklagenpositionen im
  Wirtschaftsplan ordnen Sie einer Rücklage zu; Entnahmen, Steuern, Gebühren und Zinsen erfassen
  Sie je Abrechnung mit Beleg. Die Abrechnung zeigt die Entwicklung je Rücklage.
* Kostenpositionen können Sie aus den gebuchten Belegen eines Kontos übernehmen. Das Paket zeigt
  je Position, ob Buchung und Beleg verknüpft sind.
* Für Lohnanteile nach § 35a EStG tragen Sie den belegten Betrag je Position ein. Der Ausweis dient
  der Information der Eigentümer; die steuerliche Beurteilung bleibt beim Steuerberater.
* Die Quelle einer Verteilung auf einen Teil der Einheiten wählen Sie als Beschluss oder Dokument.
* Die Einzelabrechnung je Einheit steht als PDF Entwurf nach interner Freigabe bereit, nur mit
  geöffneter Freigabestufe G4.
* Der Wirtschaftsplan hat Bezeichnung, Stichtag, Zahlungsrhythmus, Fälligkeitstag, Fortgeltung
  und Vergleichsgrundlage (Vorjahresabrechnung oder Vorplan) mit Abweichung je Position.

## Rücklagen, Zahlungsrhythmus, Gesamtabrechnung, Einsicht und Prüfung: Bedienung (Stand 30.09.2026)

* Rücklagen: Unter Rücklagen der Gemeinschaft legen Sie zweckgebundene Rücklagen an und erfassen
  Entnahmen, Steuern, Gebühren und Zinsen je Abrechnung. Die Entwicklung je Rücklage steht als
  eigener Block unter dem Gesamtblock. Gezahlte Beträge erscheinen je Rücklage nur, wenn der
  Vorschuss der Eigentümer an genau eine Rücklage gebunden ist; sonst steht "nicht zugeordnet"
  und der gezahlte Betrag bleibt ein Gesamtwert.
* Wirtschaftsplan: Beim Anlegen wählen Sie Zahlungsrhythmus (monatlich, vierteljährlich,
  jährlich), Fälligkeitstag und optional den Vorplan als Vergleich. Nach der Berechnung zeigt die
  Planseite den Vergleich mit dem Vorjahr je Komponente und je Position. Bei vierteljährlichem
  oder jährlichem Rhythmus legt die Übernahme in die Zahlungspläne einen passenden Zahlungsplan
  je Vertrag an; der Plan beginnt dafür zum Monatsersten. Die Vorschau zeigt den Betrag je Periode.
* Gesamtabrechnung als PDF: Die Schnittstelle liefert sie auf dem Briefbogen des Mandanten, nur
  mit geöffneter Freigabestufe G4 und nach interner Freigabe. Die Ausgabe ist ein Entwurf.
* Einsichtsanfragen: Beim Erzeugen des Pakets geben Sie die Gültigkeit in Tagen an (leer: ohne
  Ablauf). Die Frist ist eine Produktvorgabe und wird mit dem Rechtsanwalt geklärt. Die Seite
  zeigt das Ablaufdatum und erlaubt den Widerruf mit Grund. Nach der Bereitstellung steht die
  Benachrichtigung im Verlauf. Mit Eigentümerstellung prüfen sehen Sie, ob der Antragsteller
  seit dem Antragstag Eigentümer geblieben ist; über einen Widerruf entscheiden Sie.
* Prüfauftrag: In der Positionsliste öffnet Verlauf anzeigen alle Änderungen einer Position mit
  altem und neuem Wert. Unter den Prüfberichten bestätigen Sie eine Version mit Namen und Vermerk.
  Die Bestätigung ist kein Beschluss und kann nicht zurückgenommen werden. Der Prüfzugang des
  Beirats erlaubt nur Lesen und Anmerken, keine Buchung.

## Rücklagen (Version 1.49.0)

Seite `/weg/[id]/ruecklagen` je Objekt. Zweck: zweckgebundene Rücklagen der Gemeinschaft führen und
ihre Entwicklung ansehen. Voraussetzung ist ein Buchungskreis der Gemeinschaft für das Objekt, sonst
zeigt die Seite einen Hinweis.

* Rücklage anlegen mit Bezeichnung und Zweck. Zahlungen werden einer Rücklage zugeordnet, wenn der
  Sollbetrag der Eigentümer an diese Rücklage gebunden ist; sonst bleibt der gezahlte Betrag ein
  Gesamtwert.
* Entwicklung der Rücklagen: auf Basis der berechneten Abrechnung mit Rücklagenblock (Jahr und
  Version werden angezeigt). Je Rücklage Anfangsbestand, beschlossene Zuführungen (Soll), Gezahlt
  (Ist), Entnahmen, Zinsen, Endbestand sowie Bankbestand und Differenz zum Endbestand.
* Mittelverwendung erfassen: Art (Entnahme, Steuer, Gebühr, Zins), Betrag und Zweck. Die Erfassung
  ist eine Information für die Abrechnung und bucht nichts; Belege werden an der Abrechnung verknüpft.

## Gesamtabrechnung als PDF

In der Abrechnung einer WEG lädt "Gesamtabrechnung als PDF" die Gesamtabrechnung auf dem Briefbogen herunter. Das PDF ist ein Entwurf und steht erst nach interner Freigabe der Abrechnung und bei offener Freigabestufe G4 zur Verfügung; andernfalls erscheint eine Meldung.

## Rücklagen je Position: Anfangsbestand und Entwicklung je Jahr (Stand 01.10.2026)

Auf der Seite Rücklagen der Gemeinschaft hat jede Rücklage die Schaltflächen Ändern und Entwicklung anzeigen.

* Ändern: Bezeichnung, erfasster Anfangsbestand und das Jahr, ab dem er gilt. Ein Bankkonto kann über die Schnittstelle hinterlegt werden; zulässig ist nur ein Konto des Rechtsträgers der Gemeinschaft.
* Entwicklung anzeigen: je Jahr Anfang, Zuführung, Entnahmen, Steuern, Gebühren, Zinsen und Ende. Der Anfang ist das Ende des Vorjahres, im ersten Jahr der erfasste Anfangsbestand. Die Spalte Grundlage zeigt, ob die Werte aus einer Abrechnung (gezahlt oder Soll) oder aus dem beschlossenen Wirtschaftsplan stammen.
* Erfasste Mittelverwendung: Einträge anzeigen listet die Bewegungen der Abrechnung mit Belegstatus. Entfernen ist nur im Entwurf möglich.

Die Angaben sind Information für Abrechnung und Vermögensbericht. Es wird nichts gebucht.

## Rücklagenabrechnung

Auf der Seite WEG, Rücklagen legt der Bearbeiter je Jahr eine Rücklagenabrechnung aus der jüngsten Hausgeldabrechnung an und erzeugt sie aus deren Rücklagendaten (Anfangsbestand, Zuführung, Entnahmen, Zinsen, Endbestand, Bankbestand und die Stammdaten je Rücklage). Die Statusschritte entsprechen der Hausgeldabrechnung: interne Freigabe durch eine zweite Person, Beiratsprüfung, Beschluss, ausgeben, fällig, gebucht, gesperrt. Ausgeben ist erst nach dem Beschluss möglich; ausgeben, fällig und gebucht setzen die Freigabestufe G4 voraus. Wird die Hausgeldabrechnung neu berechnet, ist die Rücklagenabrechnung neu zu erzeugen, bevor sie freigegeben wird.

## Rücklagen: Kontoauswahl und Entwicklung in der Abrechnung

Beim Anlegen und Ändern einer Rücklage (WEG, Rücklagen) wählt der Bearbeiter das Bankkonto und das Buchungskonto aus Auswahllisten. Angeboten werden nur Bankkonten des Rechtsträgers der Gemeinschaft und die aktiven Konten des Buchungskreises; die API prüft beides erneut. Die Auswahl bucht nichts. In der Hausgeldabrechnung (WEG, Abrechnung) zeigt der Abschnitt "Entwicklung je Rücklage und Jahr" Anfang, Zuführung, Entnahmen, Steuern, Gebühren, Zinsen und Ende bis zum Abrechnungsjahr. Die Eigentümer- und die Rücklagenabrechnung zeigen den Statusverlauf als Liste, ohne Eintrag mit dem Hinweis "Noch kein Statuswechsel."

## Rücklage: Sperre des Anfangsbestands (Stand 01.10.2026)

Sobald die Abrechnung des Anfangsjahres berechnet oder freigegeben ist, lassen sich Anfangsbestand und Anfangsjahr einer Rücklage nicht mehr ändern. Korrekturen erfassen Sie als neue Bewegung. Ein beendetes Bankkonto oder ein inaktives Buchungskonto lehnt das System auch dann ab, wenn es nicht über das Formular gewählt wurde.

## Protokollabschluss: Dokument auswählen

Beim Protokollabschluss wird das unterschriebene Protokoll nicht mehr als ID eingetippt. Über die Suche (mindestens 2 Zeichen) wird ein vorhandenes Dokument gewählt. Ein neues Protokoll wird zuvor im Dokumentenbereich hochgeladen. Beim Bestätigen durch die zweite Person ist die Auswahl gesperrt. Der Status einer Versammlung kann auch "gestört" lauten; dann sind Abschluss und Beschlussfassung nicht möglich.

## Vermögensbericht im Eigentümerportal und Bereitstellungsprotokoll

Ein ausgestellter Vermögensbericht (Status "ausgestellt") erscheint im Eigentümerportal unter Abrechnungen. Das PDF ist erst nach Freigabestufe G4 abrufbar. Jeder Abruf wird je Einheit vermerkt. In der Berichtsansicht zeigt der Abschnitt "Bereitstellungsprotokoll je Eigentümer" ersten und letzten Abruf und die Anzahl. Der Vermerk ist ein Indiz und keine Zustellung; Eigentümer ohne Abruf erhalten den Bericht auf anderem Weg (Brief). Ob der Portalabruf rechtlich genügt, ist offen (AA07-02).

## Sondererwerb im Abrechnungsjahr freigeben

Hat im Abrechnungsjahr ein Eigentümer durch Ersterwerb, Erbfall, Zwangsversteigerung, Schenkung oder sonstigen Erwerb übernommen, oder ist Sondernachfolgehaftung gekennzeichnet, sperrt das Abrechnungspaket mit dem Hinweis "Erwerbsart im Abrechnungsjahr". In der Hausgeldabrechnung erscheint der Abschnitt "Sondererwerb im Abrechnungsjahr" mit einem Zuordnungsvorschlag zur Prüfung. Eine Person beantragt die Freigabe, eine andere Person gibt sie mit Begründung frei. Der Vorschlag ist keine Rechtsregel; die Berechnung ändert sich nicht (offen: AA07-01). Bei einer neuen Abrechnungsversion ist die Freigabe erneut nötig.

## Versammlungsart, Ergebnis je TOP und Beschluss-Sammlung (Stand 01.10.2026)

Beim Anlegen einer Versammlung wählen Sie die Art (ordentlich, außerordentlich, Teilversammlung,
Umlaufverfahren); Wiederholung und Fortsetzung werden mit Bezug auf die Ursprungsversammlung
über die Schnittstelle angelegt. In der Versammlung erfassen Sie unter "Art, Dauer, Vorlagen
und Beschreibung" das Ende, die Vorlagen sowie eine öffentliche Beschreibung, die Eigentümer im
Portal sehen, und eine interne Beschreibung, die nur die Verwaltung sieht. Für einen TOP wählen
Sie die Beschlussregel "Zustimmung aller Eigentümer", wenn alle stimmberechtigten Eigentümer
zustimmen müssen, nicht nur die anwesenden. Nach der Einladung setzen Sie je TOP das Ergebnis
"vertagt" oder "ohne Abstimmung" und hinterlegen den Protokolltext; angenommen und abgelehnt
ergeben sich aus der Verkündung. Jede Stimme trägt ihren Kanal (Präsenz, online, Umlauf). Die
Beschluss-Sammlung zeigt Ort, Eintragungszeit und gerichtliche Vermerke; "gelöscht" und
"gegenstandslos" sind Vermerke, der Eintrag bleibt erhalten. In den Versammlungseinstellungen
schalten Sie optional die Sperre bei einer Geltungsdauer des Grundlagenbeschlusses über drei
Jahre ein; ohne Schalter erscheint nur ein Hinweis (rechtlich zu prüfen).

### Wiederholungs- und Fortsetzungsversammlung anlegen

Beim Anlegen einer Versammlung die Art Wiederholungsversammlung oder Fortsetzung wählen und die Ursprungsversammlung derselben Gemeinschaft auswählen (Pflichtangabe). Vorlagen für Einladung, Vollmacht und Stimmzettel wählen Sie in der Versammlung unter Art, Dauer, Vorlagen und Beschreibung aus einer Liste. Die öffentliche Beschreibung sehen Eigentümer im Portal, die interne Beschreibung nicht. Liegt das Gültigkeitsende des zulassenden Beschlusses mehr als drei Jahre nach dem Beschlussdatum, zeigt die Versammlung dauerhaft einen Hinweis. Eine Sperre besteht nur, wenn der Mandantenschalter aktiv ist (Standard aus).

### Vermögensbericht per Brief versenden

In der Ansicht des ausgegebenen Vermögensberichts zeigt das Bereitstellungsprotokoll je Einheit die Portalabrufe und die Briefe. Die Schaltfläche "Bericht per Brief versenden" bereitet für alle Eigentümer ohne Portalabruf einen Brief vor; mit dem Haken "Auch an Eigentümer mit Portalabruf versenden" erhalten alle Eigentümer einen Brief. Der Zustellweg folgt dem Kontakt, sonst dem Mandantenstandard. Briefe gehen über den Versand (Postauftrag, E-Mail-Entwurf oder Portal) und verlassen das Haus erst nach den dortigen Freigaben. Die Funktion setzt Freigabestufe G4 voraus.

### Sonderfälle des Eigentümerwechsels

Ersterwerb, Zwangsversteigerung, Erbfall, Schenkung, sonstiger Erwerb und Sonderrechtsnachfolge im Abrechnungsjahr sperren das Abrechnungspaket, bis eine erste Person die Freigabe beantragt und eine zweite Person sie erteilt hat. Der Zuordnungsvorschlag ist ein Prüfhinweis, keine Rechtsregel.

Der Versandstatus im Bereitstellungsprotokoll erscheint auf Deutsch (vorbereitet, versendet, zugegangen, fehlgeschlagen). Mit dem Brief erzeugte Dokumente sind direkt mit dem Vermögensbericht verknüpft.

## Online-Teilnahme an der Versammlung (AD06, Stand 01.10.2026)

Technisch vorbereitet, Standard aus. Der Schalter wird über `PUT /hoa/online-meeting-settings` gesetzt, erst nach Klärung durch die Rechtsberatung (AD06-01). Vollmacht und Stimmabgabe im Portal brauchen zusätzlich die Freigabestufe G4.

1. Hybride oder virtuelle Versammlung anlegen, Konferenzlink der externen Videolösung unter Zugangsdaten hinterlegen und einladen.
2. Auf der Versammlungsseite zeigt der Bereich "Online-Teilnahme (Portal)" die Zusagen, die Vollmachten mit Zeitraum und Widerruf und die Wortmeldungen mit Zeitstempel.
3. Wortmeldungen in der Reihenfolge des Eingangs aufrufen und mit "Erledigt" abarbeiten.
4. Je TOP "Abstimmung öffnen", nach Ende der Stimmabgabe "Abstimmung schließen". Online-Stimmen erscheinen in der Auszählung mit Kanal online.
5. Ergebnis wie bisher verkünden; erst danach sehen die Eigentümer das Ergebnis im Portal.

Ob eine rein virtuelle Versammlung zulässig ist, prüft das System nicht.

## Korrektur einer Abrechnung (neue Version mit Differenzbericht)

Wird ein Beschluss geändert oder für ungültig erklärt, legen Sie über "Neue Version" eine Korrekturfassung an (Grund, Bezug, optional Beschluss). Die alte Fassung bleibt unverändert. Nach der Berechnung beider Fassungen zeigt der Versionsvergleich je Eigentümer vorher, nachher und Differenz sowie die Heizkostenüberleitung (Zahlung, verteilte Kosten, erklärte Abgrenzung, unerklärter Rest). Der Bericht bucht und fordert nichts; die Rechtsfolge ist offen und braucht die Freigabe der Geschäftsführung.

## Virtuelle Versammlung: Stichtag und Online-Schalter (AE12)

Im Objekt unter WEG, Bereich Versammlungen, tragen Sie in den Einstellungen optional den Stichtag der Übergangsregel ein. Das Datum ist ein Merkposten ohne Rechtswirkung und löst keine Sperre aus; Inhalt und Anwendbarkeit der Regel sind mit der Rechtsberatung zu klären (AA06-02). Dort steht auch der Schalter "Online-Teilnahme im Portal zulassen" (Standard aus, Klärung AD06-01). In der Versammlung zeigt der Block "Fristhinweise Grundlagenbeschluss" Beschlussdatum, Dreijahresgrenze, Gültigkeitsende und Resttage als Orientierung, zu verifizieren.

## Zahlungen je Rücklage (AE08)

In der Jahresabrechnung zeigt der Abschnitt „Zahlungen je Rücklage“ je Zweckrücklage das Soll laut beschlossenem Wirtschaftsplan und das Ist der an die Rücklage gebundenen Zahlungen. Eine Zahlung ist gebunden, wenn die Sollstellung im Vertrag mit einer Rücklage erfasst wurde; dafür braucht jede Rücklage eine eigene Zahlungsart. In den Mandanteneinstellungen (`/hoa/reserve-payment-settings`) lässt sich die Variante „Vorschlag nach Planverhältnis“ wählen. Dann wird der nicht zugeordnete Rest rechnerisch nach Planverhältnis aufgeteilt. Das ist ein Vorschlag zur Information, er wird nicht gebucht und ändert keine Posten. Standard ist „nur gebundene Zahlungen“.

## Unterjährige Planänderung: Differenz gebuchter Monate (Stand 01.10.2026)

Liegt der Wirksamkeitsbeginn eines neuen Wirtschaftsplans vor bereits gebuchten Monaten, zeigt
die Vorschau der Übernahme den Abschnitt "Differenz gebuchter Monate". Je Einheit und Monat
stehen gebuchter Betrag, neuer Betrag und Differenz (Nachforderung oder Gutschrift).

* Variante wählen: "Nur Hinweis" (Standard), "Differenz sofort fällig" oder "Verrechnung mit der
  nächsten Rate". Welche Variante rechtlich gilt, ist noch offen (M12-L2).
* Bei den Varianten mit Entwurf legt "Differenzen als Entwurf anlegen" je Einheit und Monat
  einen Entwurf an, erst nach dem Beschluss des Plans.
* Freigeben oder Verwerfen darf nur eine zweite Person und nur mit Freigabestufe G4. Gebucht
  wird dabei nichts; die Buchung folgt erst mit G1.

## Zuordnungsregel bei Eigentümerwechsel

In der Abrechnungsansicht erscheint bei Sondererwerben der Block "Zuordnung des Abrechnungsergebnisses bei Eigentümerwechsel". Je Erwerbsart wählen Sie die Variante (manuelle Freigabe als Standard, Zuordnung nach Fälligkeit, Zuordnung nach Abrechnungsbeschluss) und vermerken die Quelle. Die Variante ist eine Konfiguration zur fachlichen Prüfung, keine Rechtsregel; die Rechtsfrage ist mit dem Rechtsanwalt zu klären.

## Rücklagenplan je Jahr (Welle 16)

Unter WEG, Rücklagen steht je Rücklage der Rücklagenplan: Jahr, Soll-Zuführung, Abweichung
zum Wirtschaftsplan, Status und steuerliche Einordnung (Platzhalter, nicht freigegeben). Ein
Entwurf wird mit Jahr und Betrag angelegt oder per API aus dem Wirtschaftsplan abgeleitet und
mit dem gewählten Beschluss als beschlossen gekennzeichnet. Ein beschlossener Plan ist nicht
mehr änderbar; ein neuer beschlossener Plan desselben Jahres ersetzt ihn. Änderungen des
Anfangsbestands nach berechneter Abrechnung sind standardmäßig gesperrt; der Mandantenschalter
erlaubt alternativ eine protokollierte Änderung oder eine Freigabe durch eine zweite Person.
Es wird nichts gebucht.

## Online-Versammlung: Vollmacht gegen eigene Stimme, Prüfpunkte, Protokollentwurf (AE31)

Unter WEG, Bereich Versammlungen, steht beim Schalter "Online-Teilnahme im Portal zulassen" die Regel für den Fall, dass für eine Einheit eine Stimme des Eigentümers und eine Stimme des Bevollmächtigten vorliegen. Standard ist "Konflikt als Prüfhinweis markieren": Die erste Stimme bleibt gezählt, die zweite wird gespeichert, aber nicht gezählt, und die Versammlungsleitung prüft den Fall. Es wird keine Stimme verworfen. Die weiteren Varianten sind "Zuerst abgegebene Stimme zählt", "Vollmacht hat Vorrang" und "Eigene Stimme hat Vorrang". Die Regel ist eine Einstellung des Betreibers und keine Rechtsauskunft; die rechtliche Wirkung klärt die Rechtsberatung (AD06-02).

Auf der Versammlungsseite führt der Bereich "Online-Teilnahme (Portal)" die Stimmkonflikte mit Einheit, TOP und beiden Stimmen. Mit "Erste Stimme bestätigen" oder "Zweite Stimme zählen" (nur vor der Verkündung) entscheidet die Versammlungsleitung, optional mit Notiz. Beide Stimmen bleiben im Vorgang erhalten. Darüber zeigen die "Prüfpunkte zur Versammlungsform" die erfassten Angaben (Schalter, zulassender Beschluss mit Status und Gültigkeitsende, Dreijahresgrenze als Orientierung, Konferenzlink). Die Liste ist eine Übersicht und stellt keine Zulässigkeit fest (AD06-01).

Der Protokollentwurf übernimmt bei hybrider oder virtueller Form die Zusagen, die Portalvollmachten, die Wortmeldungen mit Uhrzeit und Einheit, je TOP die online abgegebenen Stimmen und die Prüfhinweise zu Stimmkonflikten. Offene Konflikte stehen im Hinweis des Entwurfs und sind vor der Unterschrift zu klären.

## Eigentümerwechsel und offene Einsichtsanfragen; Korrekturbericht (Welle 17, AF08)

Wird ein Eigentümerwechsel erfasst, erhält jede offene Einsichtsanfrage der bisherigen
Eigentümerseite derselben Liegenschaft innerhalb einer Stunde einen Prüfhinweis im Verlauf
(Eigentümerprüfung). Die Anfrage bleibt offen; ob eine Bereitstellung widerrufen wird, entscheidet
der Verwalter. Der Korrekturbericht zwischen zwei Abrechnungsversionen erscheint erst, wenn der
Schalter Korrekturbericht je Eigentümer unter Einstellungen, Fachliche Regeln eingeschaltet ist
(Standard aus).

### Ablage der Abrechnungs-PDFs

Beim Bereitstellen einer Hausgeldabrechnung (Status ausgegeben oder fällig) legt die Plattform jede Einzelabrechnung einmalig im Dokumentenarchiv ab und verknüpft sie mit Abrechnung, Objekt, Gemeinschaft, Einheit und Eigentümer. Die Gesamtabrechnung wird bei der ersten Ausgabe abgelegt. Jeder spätere Abruf im CRM und im Eigentümerportal liefert genau die abgelegte Datei, auch Briefdatum und Layout bleiben unverändert. Eine neue Version der Abrechnung erzeugt ein neues Dokument, das alte bleibt erhalten. Voraussetzung bleibt die Freigabestufe G4.

## Zuordnungsvorschlag bei Eigentümerwechsel (Welle 18, AG20)

Unter Einstellungen, Fachliche Regeln, schaltet der Schalter "Zuordnungsvorschlag bei Eigentümerwechsel" (Standard aus) einen Hinweis frei: Die Vorschau der Planübernahme zeigt je Zeile den Eigentümer, den die Regel je Erwerbsart vorschlagen würde, und markiert Abweichungen vom verwendeten Eigentümer. Für eine Abrechnung mit Beschluss liefert die Schnittstelle dieselbe Gegenüberstellung je Einheit. Übernommen und gebucht wird weiterhin beim bisherigen Eigentümer; der Vorschlag bucht nichts und versendet nichts. Die Rechtsfrage bleibt offen (W07, P01).

### Neue Version einer Jahresabrechnung mit Korrekturbeschluss

Die Schaltfläche "Neue Version" öffnet einen Dialog. Dort wählen Sie optional den Korrekturgrund, beschreiben die Grundlage und wählen einen Korrekturbeschluss derselben Gemeinschaft. Nach dem Anlegen zeigt die Maske die Mehrheitsprüfung des Beschlusses an. Die Prüfung ist nur ein Vermerk und ändert keinen Status. Ein Beschluss einer anderen Gemeinschaft wird abgelehnt (Fehler MHVP-HOA-0038).

## Eigentümerwechsel prüfen und Mehrheit je Beschluss (GAI-412, GAI-413, Welle 21)

Auf der Seite Einsichtsanfragen einer Gemeinschaft prüft die Schaltfläche "Eigentümerwechsel prüfen" (Recht WEG bearbeiten), ob bei offenen Anfragen der Eigentümer seit der Anfrage gewechselt hat. Es entsteht nur ein Prüfvermerk, keine Anfrage wird geschlossen und kein Paket widerrufen. In der Beschlusssammlung zeigt "Mehrheit prüfen" je Beschluss das gespeicherte und das aktuelle Ergebnis der Mehrheitsprüfung. Die Anzeige ändert den Beschlussstatus nicht und ersetzt keine rechtliche Würdigung.

## Einzelabrechnung als PDF und Zuordnungsvorschlag (GAJ-201, GAJ-203, Welle 23)

Auf der Abrechnungsseite einer Gemeinschaft erscheint je Einheit die Schaltfläche "Einheit ..." für die Einzelabrechnung als PDF-Entwurf. Sie bleibt gesperrt, solange die Freigabestufe G4 geschlossen ist oder die Abrechnung nicht intern freigegeben wurde. Der Abschnitt "Zuordnungsvorschlag bei Eigentümerwechsel" lädt auf Klick den Vorschlag, wer das Ergebnis je Einheit trägt, und zeigt Abweichungen zur verwendeten Zuordnung. Der Vorschlag hat keine Buchungswirkung und ist nur bei eingeschaltetem Mandantenschalter abrufbar.
