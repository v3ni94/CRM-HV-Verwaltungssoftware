# Plattform

Stand: 27.09.2026. Dieses Kapitel richtet sich an Plattformadministratoren der Müller
Holding AG. Alle Seiten liegen unter Plattform und sind für Mandantenrollen nicht sichtbar.

## Zweck und Voraussetzungen

Die Plattformseiten verwalten Mandanten, Lizenzen und die Voraussetzungen für Drittmandanten
(Freigabestufe G5). Voraussetzung ist ein Benutzerkonto mit Plattformrecht; die Freigabe von
G5 setzt zusätzlich das Superadmin-Kennzeichen voraus. Keine dieser Seiten öffnet eine
Freigabestufe, versendet E-Mails oder erzeugt Geldwirkung.

## Übersicht

Die Startseite Plattform zeigt je Mandant Nutzung (Einheiten, Benutzer, Kontingent), den
Stand der Freigabestufen G1 bis G5 und die G5-Nachweise. Von hier führen Verweise zu
Mietrecht, Preisstruktur und Angebot, Freigabe G5 und Onboarding Drittmandanten.

## Preisstruktur und Angebot

Das Preismodell ist eine Struktur aus Stufen nach Einheiten (S bis XL), Zusatzmodulen (WEG,
Buchhaltung, Banking, Portal, KI) und einer Testphase. Beträge sind bewusst leer: Der
Betreiber trägt sie je Zeile ein (Betrag netto, Speichern) oder löscht sie wieder; Zeilen
lassen sich deaktivieren. Solange eine aktive Zeile ohne Betrag ist, meldet die Seite die
Anzahl der fehlenden Beträge.

Angebot als PDF-Entwurf: Interessent und Einheiten eingeben, Angebotsentwurf herunterladen.
Das PDF trägt das Wasserzeichen ENTWURF, nennt fehlende Beträge als offen und weist alle
Beträge netto ohne Umsatzsteuer aus. Versand und Freigabe eines Angebots erfolgen außerhalb
der Plattform durch die Geschäftsführung (offene Entscheidung M27-01).

## Freigabe G5: Nachweisliste

Je Mandant sind acht Nachweise zu führen: Pentest-Bericht, Verfahrensdokumentation,
AVV-Vorlage, Aufbewahrungsmatrix freigegeben, Restore-Übung protokolliert,
Barrierefreiheitserklärung, Datenschutzinformation Portal, Rollen- und Rechtematrix (Export).
Jeder Nachweis hat den Status offen oder erledigt; erledigt ist nur mit der Dokument-ID
eines Dokuments des Mandanten möglich (Dokument zuvor im Mandanten hochladen, ID aus der
Dokumentansicht). Eine Notiz ist optional.

Ablauf der Freigabe: Ein Mandantenadministrator stellt im Mandanten den Freigabeantrag G5
(Einstellungen, Freigabestufen). Die Genehmigung durch den Superadmin ist nur möglich, wenn
alle acht Nachweise erledigt sind; sonst weist die Plattform den Versuch mit dem Hinweis auf
die offenen Nachweise ab und der Antrag bleibt offen. Die Nachweisliste selbst öffnet und
schließt kein Gate. Ein Widerruf läuft über den Antrag.

Grenzen: Die Plattform prüft nicht den Inhalt der Nachweise. Ob ein KI-gestützter
Penetrationstest genügt oder eine unabhängige Prüfung erforderlich ist, entscheidet der
Betreiber (offene Entscheidung M27-02).

## Onboarding Drittmandanten

Der Assistent legt in fünf Schritten einen neuen Mandanten an:

1. Mandant: Kürzel (Kleinbuchstaben, Ziffern, Bindestrich), Name, Firma, Ort.
2. Rechtsträger: Verwalter, Eigentümer Mietverwaltung oder Eigentümer SEV mit Namen.
   WEG-Rechtsträger entstehen später mit dem Objekt.
3. Administrator: E-Mail, Anzeigename, Startpasswort (mindestens 12 Zeichen). Der
   Administrator erhält die Rolle Mandantenadministrator und ändert das Passwort beim ersten
   Anmelden. Existiert die E-Mail bereits, wird das vorhandene Konto Mitglied.
4. CI: Primärfarbe und Logo (Dokument-ID) aus dem CI-Modul; alles später unter
   Einstellungen änderbar.
5. Zusammenfassung und Mandant anlegen.

Nach dem Anlegen zeigt die Seite Rechtsträger, Administrator, Feature-Flags (alle aus),
Freigabestufen (alle geschlossen) und den Entwurf der Willkommens-E-Mail. Die E-Mail wird
nicht versendet; sie ist nach Prüfung über das Postfach zu verschicken.

## Mandanten-Export (DSGVO Auskunft, Portabilität)

Der Export erzeugt ein ZIP mit einer JSON-Datei je Entität (Mandant, Einstellungen ohne
Geheimnisse, Mitgliedschaften, Rechtsträger, Objekte, Einheiten, Kontakte) und einem
Manifest. Ablauf im Vier-Augen-Prinzip: Eine Person beantragt den Export mit Zweck Auskunft
oder Portabilität, eine zweite Person gibt frei oder lehnt ab, danach steht der Download
bereit; jede Ausgabe wird gezählt und protokolliert. Der Export enthält ausschließlich Daten
des gewählten Mandanten.

Grenzen: Der Export ist ein Entwurf ohne Rechtsprüfung. Umfang, Fristen und Rechtsgrundlage
der Auskunft legt der Betreiber mit Rechtsanwalt fest (offene Entscheidung M27-03-01).

Vollexport als Job (seit 30.09.2026): Nach der Freigabe durch die zweite Person erscheint in der
Zeile der Schaltfläche Vollexport als Job starten. Der Job läuft im Hintergrund und packt
zusätzlich Verträge, Buchungssätze und Buchungszeilen, Rechnungen, Tickets und die
Dokumentoriginale in die ZIP-Datei (Daten als JSON Lines im Ordner data, Dokumente im Ordner
documents). Der Status wechselt von Job eingereiht über Job läuft zu Export bereit; erst dann
ist der Download möglich. Fehler je Dokument stehen in der Datei manifest.json. Bei
Fehlschlag kann der Job erneut gestartet werden. Dokumente in externen Speichern
(Paperless, Google Drive) sind nicht enthalten, das Manifest zählt sie.

## Lizenzen, Preisliste, Abrechnungsvorschau und Nutzungsverlauf

Die Seite Lizenzen und Preisliste (Plattform, Verweis Lizenzen und Preisliste) ist nur für
Plattformadministratoren sichtbar. Sie ändert keine Freigabestufe.

* Lizenzen: Mandant wählen, Lizenz mit Modul, Kontingent, Laufzeit und optional vereinbartem
  Preis anlegen. Ohne Preis folgt die Lizenz der Preisstruktur (Stufen für das Kernmodul,
  Zusatzmodule je Zeile). Eine Lizenz wird nicht gelöscht: Enddatum eintragen und Beenden
  wählen. Die Schaltfläche Preis aus Struktur nimmt einen vereinbarten Preis zurück.
* Abrechnungsvorschau: Monat wählen und Berechnen. Die Vorschau ist netto, nennt Stufe,
  Testphase und Überschreitung des Kontingents. Fehlt für eine Lizenz der Betrag in der
  Preisstruktur, ist die Summe unvollständig und die Seite weist darauf hin. Die
  Rechnungsstellung der Lizenzentgelte ist offen (M27-01).
* Nutzungsverlauf: Einheiten, Benutzer, KI-Kosten und Speicher je Monat und je Tag. Die Zählung
  läuft täglich um 02:10 Uhr (UTC) und lässt sich mit Nutzung jetzt zählen anstoßen.
* Preisverlauf je Modul: Einträge ändern (Preis) oder löschen. Der heute gültige Eintrag
  eines Zusatzmoduls schreibt den Betrag der Preisstruktur; bestehende Lizenzen behalten ihren
  vereinbarten Preis.

## Lizenzen und Preisliste (Seite Plattform, Lizenzen)

Nur für Plattformadministratoren. Die Seite verwaltet je Mandant die Lizenzen je Modul mit Kontingent (Einheiten), Gültigkeit, vereinbartem Preis (leer: Preis aus der Preisstruktur) und Mindestbetrag. Lizenzen lassen sich anlegen und beenden.

- Die Abrechnungsvorschau berechnet für einen Monat Einheiten, Betrag und Summe netto, mit Kennzeichen für Testphase und Überschreitung des Kontingents. Fehlt für eine Lizenz der Preis, wird die Summe als unvollständig markiert.
- Der Nutzungsverlauf zeigt je Monat und je Tag Benutzer, KI-Kosten und Speicher; "Nutzung jetzt zählen" löst eine Zählung aus.
- Der Preisverlauf je Modul zeigt die Preislisteneinträge. Es sind keine Preise vorbelegt, die Rechnungsstellung ist offen.
