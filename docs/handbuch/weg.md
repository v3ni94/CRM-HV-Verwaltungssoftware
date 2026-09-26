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

Nach dem Beschluss übernimmt Vorschüsse übernehmen die beschlossenen Hausgeld- und
Rücklagenbeträge als Zahlungen in die Eigentumsverhältnisse (Kapitel Verträge); daraus
entstehen die monatlichen Sollstellungen.

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

### Protokollentwurf

Protokollentwurf erzeugen (Recht Buchhaltung anlegen) erstellt aus Tagesordnung, Anwesenheit
mit Stimmrechten, Beschlusstexten, Auszählung, Verkündung und Unterschriftszeilen ein PDF
auf dem Briefbogen des Mandanten und legt es als Entwurfsdokument an der Versammlung ab
(Entwurf herunterladen, Protokollentwurf neu erzeugen). Der Entwurf hat keine Rechtsfolge
und ersetzt nicht das unterschriebene Protokoll; dieses bleibt getrennt verknüpft und wird
nie überschrieben.

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
