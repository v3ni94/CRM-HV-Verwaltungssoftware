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
mit dem Reiter WEG. Die Seite einer Gemeinschaft zeigt vier Listen (Wirtschaftspläne,
Hausgeldabrechnungen, Versammlungen, Sonderumlagen) mit jeweils einer Schaltfläche zum
Anlegen sowie darunter die Beschluss-Sammlung. Voraussetzung ist ein Buchungskreis der
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
  mit Nummer in die Beschluss-Sammlung.

Status der Versammlung: geplant, eingeladen, eröffnet, geschlossen. Über die Schnittstelle
stehen außerdem bereit: Umlaufbeschluss in Textform, Vermerk einer technischen Störung bei
Online-Teilnahme und ein Protokollentwurf als PDF (Entwurf ohne Rechtsfolge).

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

## Prüfauftrag (Beirat)

Die Belegprüfung durch den Verwaltungsbeirat wird als Prüfauftrag je Hausgeldabrechnung
geführt: Prüfpositionen mit Belegen, Vermerke, Rückfragen des Beirats und Antworten der
Verwaltung sowie der Prüfbericht. Beiratsmitglieder erhalten dafür einen eigenen
Beiratszugang (Einladung wie bei Eigentümern); der Abruf eines Belegs wird als Indiz
vermerkt. Das Ergebnis der Beiratsprüfung entspricht dem Status Beirat geprüft der
Hausgeldabrechnung. Derzeit stehen Prüfauftrag, Prüfpositionen, Vermerke, Rückfragen und Prüfbericht
über die Schnittstelle bereit; eine eigene Maske im CRM und im Portal gibt es noch nicht.

Dazu gehört das Abrechnungspaket (W12): Eine Hausgeldabrechnung wird nur freigegeben, wenn
jede Kostenposition einem Kostenkonto zugeordnet ist und die Belege zuordenbar sind.

## Häufige Fehler

- Für die Gemeinschaft ist noch kein Buchungskreis angelegt: Buchungskreis der GdWE
  anlegen (Kapitel Buchhaltung).
- Keine Einzelbeträge nach Berechnen: Miteigentumsanteile (MEA) der Einheiten fehlen oder
  gelten nicht für den Zeitraum.
- Intern freigeben abgewiesen: Ersteller und Freigebende müssen verschiedene Personen sein.
- Ausgeben oder Ergebnis buchen abgewiesen: Freigabestufe G4 ist geschlossen.
