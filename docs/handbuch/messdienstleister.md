# Messdienstleister

## Zweck

Das Modul Messdienstleister verbindet die Plattform mit Abrechnungsdienstleistern für Heizung,
Warmwasser, Kaltwasser und Rauchwarnmelder (ista, Techem, KALO, Brunata Minol, BRUNATA-METRONA,
Sonstige). Es verwaltet die Zugänge zentral, ordnet Objekte und Einheiten den externen
Abrechnungseinheiten zu und ruft Verbrauchsdaten, Abrechnungsergebnisse und Dokumente ab.
Stufe 1 enthält keinen Anbieteradapter: alle Verbindungen sind manuell, der Abruf ist
vorbereitet und wird je Funktion erst nach dokumentierter Freischaltung verfügbar. Es wird
nichts gebucht, es werden keine Abrechnungen beauftragt und keine Nutzerdaten übermittelt.

## Freischaltung des Moduls

Das Modul ist je Mandant ausgeschaltet (Mandanteneinstellung `metering_module_enabled`).
Solange es aus ist, zeigen die Seiten einen Hinweis mit Link zu den Mandanteneinstellungen.
Lesen bleibt möglich, Anlegen, Ändern und Abrufen sind gesperrt.

Rechte: Messdienstleister-Daten lesen (`metering_data:read`), Verbindungen verwalten
(`metering_connections:manage`), Zuordnungen bearbeiten (`metering_assignments:update`),
Abruf ausführen (`metering_sync:run`).

## Einstellungen, Schnittstellen, Messdienstleister

### Verbindungen

Je Mandant sind mehrere Verbindungen zum selben Anbieter möglich, etwa je Kundenkonto oder
je Umgebung. Test und Produktion bleiben getrennt: für jede Umgebung wird eine eigene
Verbindung mit eigenen Zugangsdaten angelegt.

Der Einrichtungsassistent führt in fünf Schritten:

1. Anbieter wählen. Je Funktion wird der dokumentierte Stand angezeigt: "Ja, API vorhanden",
   "Dokumentation erforderlich", "Ungeklärt" oder "Nein". "Ja" bedeutet eine dokumentierte
   Schnittstelle, nicht einen freigeschalteten Zugriff. Ohne Adapter gilt "nur manuell".
2. Anzeigename, Umgebung, Kunden- und Vertragsnummern (Text, führende Nullen bleiben
   erhalten), Vertragspartner.
3. Zugangsdaten. Sie werden nur gesetzt, verschlüsselt gespeichert und nie wieder angezeigt.
   Der Schritt kann übersprungen werden.
4. Verbindungstest. Er prüft nur die Anmeldung, beauftragt keine Abrechnung und quittiert
   keine Dokumente. Ergebnis, Zeitpunkt und freigegebene Funktionen werden angezeigt. Nach
   Änderungen an Konfiguration oder Geheimnissen gilt der letzte Test als "veraltet".
5. Freigegebene Funktionen und Sprung zur Objektzuordnung.

In der Liste lassen sich Verbindungen testen, pausieren und aktivieren sowie Geheimnisse
ersetzen (ein leerer Wert entfernt ein Geheimnis). Eine Funktion ist erst verfügbar, wenn
alle vier Bedingungen erfüllt sind: dokumentiert, Adapter vorhanden, Konto freigeschaltet,
Verbindungstest erfolgreich.

### Zuordnungsübersicht

Die zentrale Tabelle zeigt alle Objektzuordnungen des Mandanten: HVM-Nummer, Objektadresse,
Anbieter, Verbindung, externe Nummer, Leistungsbereich, Gültigkeit, zugeordnete und erwartete
Einheiten, Prüfstatus, letzter erfolgreicher Abruf und Hinweis. Suche, Filter nach Status,
Leistungsbereich und Verbindung sowie Seitennavigation laufen serverseitig. Die Tabelle zeigt
dieselben Datensätze wie der Reiter Messdienstleister am Objekt.

Sammelfreigabe: Zeilen auswählen, "Ausgewählte freigeben" öffnet eine Vorschau. Bestätigt
werden nur Zuordnungen im Status "vorgeschlagen"; Konflikte und andere Status werden in der
Vorschau als übersprungen markiert. Jede Zeile wird einzeln mit ihrer Version bestätigt, ein
zwischenzeitlich geänderter Datensatz wird als nicht bestätigt gemeldet.

### CSV-Import und -Export

Vorlage herunterladen, ausfüllen, "Prüfen" zeigt einen Bericht je Zeile (in Ordnung, Fehler,
Dublette) ohne etwas zu speichern. Erst "Übernehmen" legt die fehlerfreien Zeilen an;
Fehlerzeilen und Dubletten werden übersprungen. Nummern bleiben Text, der Export enthält
keine Tabellenformeln.

## Reiter Messdienstleister am Objekt

Der Reiter auf der Objektseite zeigt je Zuordnung HVM-Objektnummer, Anbieter, Kundenkonto,
externe Liegenschafts- oder Abrechnungseinheitsnummer, Leistungsbereich, Gültigkeit,
Prüfstatus und letzten erfolgreichen Abruf. Zugangsdaten werden hier nicht eingegeben.

### Zuordnung anlegen

"Neue Zuordnung" öffnet denselben Assistenten wie zentral. Intern (HVM-Nummer, Name, Adresse)
und extern (Nummer, Bezeichnung, Adresse beim Anbieter) stehen nebeneinander. Da kein Adapter
Liegenschaften auflistet, wird die externe Nummer manuell eingegeben oder per CSV importiert.
Die Kundennummer, die Nutzeinheitsnummer und die Gerätenummer gehören nicht in dieses Feld.
Die Zuordnung wird als "offen" gespeichert.

### Bestätigen

In der Zuordnung werden zwei Bestätigungen getrennt erfasst, jeweils mit Prüfgrundlage
(zum Beispiel geprüfte Abrechnung oder Anbieterantwort): die lokale Bestätigung durch einen
Mitarbeiter und die technische Bestätigung beim Anbieter. Eine lokale Bestätigung ist keine
technische Prüfung. Widersprüchliche Zuordnungen (gleicher Leistungsbereich, überlappender
Zeitraum) erhalten den Status "Konflikt"; Abrufe sind dann gesperrt.

### Einheitenzuordnung

Jede interne Einheit wird der externen Nutzeinheit innerhalb der Abrechnungseinheit
zugeordnet. Die Tabelle zeigt interne und externe Einheitsnummer, Etage, Fläche, Belegungsstatus
(belegt, Leerstand, Eigennutzung, ungeklärt) und die aktuellen Nutzer aus den Verträgen. Es
gibt keine zweite Nutzerkartei. Die Nutzeinheitsnummer ist weder Gerätenummer noch Mietername;
ein Nutzerwechsel ändert die Einheitenzuordnung nicht. Fehlende Einheiten werden als Hinweis
angezeigt, Übertragungen bleiben bis zur vollständigen Zuordnung gesperrt.

### Jetzt abrufen

Je Datenart (Dokumente, Verbrauchsdaten, Abrechnungsergebnis, Stammdaten der
Abrechnungseinheit) steht "Jetzt abrufen" zur Verfügung. Der Knopf ist gesperrt, wenn die
Funktion nicht verfügbar ist, die Verbindung pausiert ist oder die Zuordnung im Konflikt steht;
der Grund wird daneben angezeigt. Ein Abruf ist ein Auftrag mit Status (eingereiht, läuft,
erfolgreich, teilweise, fehlgeschlagen, ungeklärt). Automatische Abrufe sind in Stufe 1 aus.

### Verbrauchsdaten, Abrechnungsergebnisse, Klärung

Verbrauchswerte und Abrechnungsergebnisse werden je Zeitraum, Nutzeinheit und Version
angezeigt und lassen sich nach Zeitraum filtern. Es sind Fremddaten zur Prüfung, es wird nichts
gebucht. Unbekannte Kennungen aus Abrufen landen im Klärungsbereich der Verbindung und werden
dort einer Zuordnung zugewiesen oder verworfen, nie stillschweigend verteilt.

## Offene Punkte

* Anbieteradapter (Stufe 2): Methoden, Zugangsdaten und Versionen erst nach Zugang zur
  offiziellen technischen Dokumentation (OPEN_QUESTIONS M40-01 bis M40-03).
* Schreibende Vorgänge (Nutzer und Rollen übermitteln, Abrechnungsdaten senden,
  Ordnungsbegriffsabgleich) sind nicht Teil der Oberfläche.
* Der Schalter `metering_module_enabled` wird bis zur Ergänzung der Mandantenseite über die
  Schnittstelle `PATCH /tenant/settings` gesetzt.
