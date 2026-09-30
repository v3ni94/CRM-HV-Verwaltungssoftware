# Barrierefreiheit (Accessibility)

## Zweck

Die MH Verwaltungsplattform soll für alle Benutzer, einschließlich Menschen mit Behinderungen, bedienbar sein. Dieses Kapitel beschreibt die Barrierefreiheitsfeatures und -richtlinien der Plattform sowie Hinweise zur Bedienung mit Hilfsmitteln.

Die Plattform wird entwickelt, um die Richtlinien Web Content Accessibility Guidelines (WCAG) 2.1 Level AA einzuhalten. Dies ist eine fortlaufende Arbeit; Verbesserungen und Feedback sind willkommen (siehe Abschnitt Probleme melden unten).

## Tastaturnavigation

Die Plattform ist vollständig mit der Tastatur bedienbar:

- **Tab / Shift+Tab**: Navigieren zwischen Elementen (Eingabefelder, Schaltflächen, Links).
- **Enter**: Aktivieren eines Buttons oder eines Links.
- **Space**: Umschalten einer Checkbox oder Radio-Button.
- **Pfeiltasten**: Navigieren in Listenfeldern, Tabellen oder Menüs (wenn aktiviert).
- **Escape**: Modal oder Popup schließen.
- **Alt+Shift+A**: Barrierefreiheit Menü öffnen (auf Portalseiten; im CRM nicht aktiviert).

Die Reihenfolge der Tab-Navigation folgt der logischen Leseordnung von oben nach unten, von links nach rechts.

### Kontrollliste Tastaturbedienung CRM (S16-09)

- Sprunglink Zum Inhalt als erstes fokussierbares Element, Ziel `main#inhalt`.
- Anmeldung, zweiter Faktor, Mandantenwahl und Meine Daten vollständig mit Tab, Umschalt+Tab,
  Eingabe und Leertaste bedienbar, sichtbarer Fokusrahmen.
- Navigation, Befehlspalette und Dialoge: Escape schließt, der Fokus kehrt zum Auslöser zurück.
- Automatische Prüfung: axe-core in Vitest (`apps/web-crm/src/components/a11y/Accessibility.axe.test.tsx`)
  und die jsx-a11y-Regeln in ESLint. Sechs Regeln sind wegen bestehender Befunde noch
  abgeschaltet (docs/OPEN_QUESTIONS.md P14-04).

## Bildschirmleser und semantisches HTML

Die Plattform ist für Bildschirmleser optimiert:

- Alle Eingabefelder haben Labels (Beschriftungen); Labels sind programmatisch mit den Eingabeelementen verknüpft.
- Überschriften sind korrekt strukturiert (H1, H2, H3, ...), nicht nur visuell formatiert.
- Tabellen haben Header-Zeilen; Tabellenüberschriften sind als `<th>`-Elemente gekennzeichnet.
- Bilder haben Alt-Texte, die den Inhalt oder Zweck beschreiben (z. B. Logo der MH AG, Statusicon, Diagramm: Leistungs-KPIs).
- Formulare haben Fehlermeldungen, die mit den betroffenen Feldern verknüpft sind.
- Links und Schaltflächen haben aussagekräftige Labels, nicht nur „Klick hier".

## Farbkontrast und Lesbarkeit

- **Kontrastverhältnisse**: Minimum 4,5:1 für Fließtext, 3:1 für große Texte und UI-Komponenten (WCAG AA).
- **Schriftgröße**: Basisgröße 16px; Skalierung bis 200 % ist möglich, ohne dass die Bedienung verlorengeht (keine horizontale Verschiebung bei mobilen Geräten).
- **Zeilenabstand**: Minimum 1,5x die Schriftgröße, um Lesbarkeit zu verbessern.
- **Farbe allein als Information**: Informationen werden nicht nur durch Farbe vermittelt (z. B. Status auch durch Icon oder Text, nicht nur Ampelfarbe).

## Darstellungsmodus

Die Plattform unterstützt Hell- und Dunkeldarstellung:

- **Systemvorgabe**: Die Plattform passt sich der Systemeinstellung an (Betriebssystem oder Browser).
- **Manuell**: Wählen unter dem Menü Konto (Kürzel oben rechts) oder Einstellungen, Darstellung.
- **Dunkelmodus**: Farben sind auf Kontrast optimiert und reduzieren Blaulichtlast für langfristige Arbeit.

## Tastaturkürzel und Befehlspalette

- **Strg+K** (oder **Cmd+K** auf macOS): Befehlspalette öffnen. Dies ist eine universelle Schnellsuche für Kontakte, Objekte, Verträge, Tickets und Aktionen, ohne dass man mehrere Menüs öffnen muss.
- **Strg+/** (oder **Cmd+/** auf macOS): Hilfe und Tastaturkürzel anzeigen (in Planung).

## Mobilgeräte und Responsive Design

Die Plattform passt sich an verschiedene Bildschirmgrößen an:

- **Telefon**: Einpaltige Ansicht, Menü über Icon links oben, Tabellen als Kartenlayout.
- **Tablet Hochkant**: Einpaltige Ansicht mit voller Breite.
- **Tablet Quer / Desktop**: Mehrspaltiges Layout mit Menü und Inhalt nebeneinander.

Auf allen Geräten bleiben Aktionsschaltflächen in Reichweite der Daumen erreichbar (unten rechts oder oben).

## Sprache und Internationalisierung

Die Plattform ist mehrsprachig:

- **Deutsch**: Hauptsprache für Benutzer der Hausverwaltung Müller GmbH und des Portals.
- **Englisch**: Für Code, API und Entwicklerdokumentation.

Die Inhaltssprache ist in der Kopfzeile gekennzeichnet (`<html lang="de">` oder `lang="en"`).

## Formulare und Validierung

- **Erforderliche Felder**: werden mit Icon und Label gekennzeichnet, nicht nur durch rote Farbe.
- **Inline-Validierung**: Fehler werden beim Verlassen eines Feldes (on blur) erkannt und unterhalb des Felds angezeigt, nicht in einem separaten Popup.
- **Typenspezifische Eingaben**: E-Mail-Felder zeigen das E-Mail-Tastatur-Layout auf mobilen Geräten; Nummernfelder zeigen das Zifferblatt.
- **Bestätigungen**: Destruktive Aktionen (Löschen, Rückgängigmachen) erfordern eine Bestätigungsmeldung, nicht nur ein Klick.

## Textformatierung und Überschriften

- Überschriften und Hervorhebungen sind semantisch gekennzeichnet (`<strong>` für wichtig, `<em>` für Hervorhebung, nicht nur Fettdruck).
- Listen sind als Listen gekennzeichnet (geordnet oder ungeordnet), nicht als Fließtext mit Sonderzeichen.
- Zitate und Blöcke sind richtig genested (nicht nur mit Einrückung formatiert).

## Probleme melden

Benutzer können auf der Portalseite Barrierefreiheit (Portal, Menü Hilfe) oder unter Einstellungen, Hilfe, eine Meldung über Zugangsbarrieren hinterlassen:

- **Beschreibung**: Was ist nicht bedienbar oder nicht verständlich?
- **Browser und Hilfsmittel**: Welches Gerät, Betriebssystem, Browser und Hilfsmittel (z. B. Bildschirmleser NVDA, JAWS) wird verwendet?
- **Schritte zum Reproduzieren**: Wie kann der Support das Problem nachvollziehen?
- **Auswirkung**: Wann und wie oft tritt das Problem auf?

Das Feedback hilft dem Entwicklungsteam, die Plattform zu verbessern.

## Bekannte Einschränkungen

- **Mathematische Formeln**: Komplexe Kalkulationen (z. B. Steuerberechnung) werden in Tabellen nicht vollständig durch Bildschirmleser erfasst; ein Textformular ist eine Alternative.
- **Diagramme**: Diagramme und Charts (z. B. Ticketauswertung, Kostenentwicklung) haben Alt-Texte, aber keine vollständige Datenalternative (Arbeitsauftrag: CSV-Export hinzufügen).
- **Externe Systeme**: Schnittstellen zu externen Anbietern (z. B. Banking, Belegeingang, Postausgang) folgen möglicherweise nicht den WCAG-Richtlinien; die Plattform wird dort nicht korrekt dargestellt (Workaround: über die Plattform oder den externen Anbieter direkt arbeiten).

## Weitere Ressourcen

- [Web Content Accessibility Guidelines (WCAG) 2.1](https://www.w3.org/WAI/WCAG21/quickref/) (englisch)
- [Barrierefreie Websites und WCAG 2.1 Schnelleinstieg](https://www.bih-nrw.de/de/beratung-und-service/barrierefreier-zugang/barrierefreie-webseiten) (deutschsprachig)
- [Tastaturkürzel in der MH Verwaltungsplattform](https://www.youtube.com/watch?v=...) (Video, in Planung)

## Kontakt

Fragen zur Barrierefreiheit oder Verbesserungsvorschläge können an support@muellerhv.de gerichtet werden, mit dem Betreff „Barrierefreiheit" oder dem Stichwort „Accessibility".
