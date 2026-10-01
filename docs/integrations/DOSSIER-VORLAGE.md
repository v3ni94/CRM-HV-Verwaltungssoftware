# Vorlage: Integrationsdossier eines Bestandstools (Anhang B, V1, AA16-03)

Stand 01.10.2026. Diese Vorlage macht den Erhebungslauf nach Anhang B des Master-Prompts
(`docs/MASTER-PROMPT.md`, Abschnitt 13 und Anhang B) wiederholbar und prüfbar. Sie ersetzt den
Prompt nicht: Der Betreiber führt den Prompt aus Anhang B unverändert im jeweiligen
Claude-Code-Projekt aus und überträgt das Ergebnis in diese Gliederung. Beispiele für fertige
Dossiers: `mail-optimierung.md`, `immoware-hub.md`; Dossiers mit Lücken:
`dossier-flow.md`, `dossier-uebergabeprotokoll.md`, `dossier-smart-einzug.md`,
`dossier-objektakte.md`. Den Stand je Tool zeigt `CHECKLISTE-BESTANDSTOOLS.md`.

## Regeln für jedes Dossier

1. Nur belegte Angaben. Jede Aussage nennt ihre Quelle (Datei und Zeile im Bestandsprojekt,
   Abschnitt im Master-Prompt oder Dokument im Plattform-Repo). Was nicht belegt ist, steht als
   `[zu ergänzen durch Betreiber: konkrete Frage]`. Nichts schätzen, nichts aus dem Namen des
   Tools ableiten, ohne die Ableitung als solche zu kennzeichnen.
2. Nur Strukturen. Keine personenbezogenen Daten aus Datenbeständen, keine Zugangsdaten,
   Schlüssel, Tokens, Passwörter, IBAN, Steuernummern. Konfigurationsvariablen nur mit Namen,
   nie mit Wert.
3. Deutsch, ohne Gedankenstriche, unter 3.000 Wörtern, Datumsformat TT.MM.JJJJ.
4. Eine Datei je Tool: `docs/integrations/<tool>.md` (Namen siehe Tabelle in
   `docs/integrations/README.md`). Nach dem Lauf: Zeile in der Tabelle von
   `docs/integrations/README.md` aktualisieren, Eintrag V1 und AA16-03 in
   `docs/OPEN_QUESTIONS.md` nur durch angehängte Zeile fortschreiben.
5. Ein Dossier entscheidet nichts. Die Empfehlung (anbinden, übernehmen, ablösen) ist ein
   Vorschlag; die Entscheidung trifft der Betreiber und wird mit Datum im Abschnitt 8
   vermerkt.
6. Nachweis der Wissensdatenbank: Anhang B verlangt zusätzlich einen WDB-Eintrag je Dossier.
   Im Dossier steht dazu eine Zeile mit Datum und Fundstelle (Titel oder Kennung des Eintrags).
   Fehlt der Eintrag, steht dort `[zu ergänzen durch Betreiber]`; er wird nicht behauptet.

## Kopf des Dossiers

```
# Integrationsdossier <Tool>

Stand <TT.MM.JJJJ>. Erhebung nach Anhang B (Abschnitt 13.<n>).
Quelle: <Repo, Branch, Commit> oder "Quelltext liegt nicht vor; ausgewertet sind nur <Dokumente>".
Erhebungslauf im Bestandsprojekt: <ausgeführt am TT.MM.JJJJ | steht aus (V1, AA16-03)>.
Wissensdatenbank: <Eintrag und Datum | [zu ergänzen durch Betreiber]>.
```

## Gliederung und Prüffragen

Die Abschnitte 1 bis 8 entsprechen Anhang B. Die Prüffragen sind der Rahmen für das
Ausfüllen; jede Frage endet in einer belegten Angabe oder in einer Lücke mit Fragestellung.

### 1. Zweck und Nutzer

* Was tut die Software, welche Geschäftsprozesse deckt sie ab, in welcher Gesellschaft
  (Hausverwaltung Müller GmbH, Müller Holding AG, Timo Müller Einzelunternehmen) läuft sie?
* Wer nutzt sie (Rollen, keine Namen)?
* Produktivstatus: Läuft sie produktiv, mit welchen Schaltern (Schreiben, Senden, KI)? Stand
  und Datum.

### 2. Technik

* Sprache, Frameworks, Datenbank, Hosting (Server, Container, Domains), Warteschlangen.
* Abhängigkeiten zu externen Diensten (Google, Immoware24, lexoffice, KI-Anbieter, Paperless,
  Drive) mit Art des Zugriffs (lesen, schreiben, senden).
* Konfigurationsvariablen, nur Namen.
* Betrieb: Wer betreibt, wo liegt es (Serverumzug betroffen: ja oder nein), Sicherung.

### 3. Datenmodell

* Tabellen oder Entitäten mit Schlüsseln und Beziehungen, gruppiert wie in
  `mail-optimierung.md`.
* Identifikation von Objekt, Einheit, Kontakt, Vertrag, Dokument: Welche Kennung gilt (zum
  Beispiel Objektnummer)? Wie entspricht sie der Kennung der Plattform (Master-Prompt 6.9)?
* Personenbezogene Datenarten (Kategorien, keine Inhalte) und Aufbewahrung im Tool.

### 4. Schnittstellen

* Vorhandene REST-Endpunkte oder Funktionen mit Ein- und Ausgabe, Authentifizierung.
* Eingehende und ausgehende Webhooks, Dateiformate, Exporte, Zeitpläne.
* Gegenstück in der Plattform: bestehender Vertrag (`webhooks.md` ausgehend,
  `inbound-mail-webhook.md` eingehend für klassifizierte Mails, `objektakte.md`,
  `smart-einzug.md`) oder "keiner".

### 5. Fachlogik, die erhalten bleiben soll

* Klassifikationsregeln, Prompts, Textbausteine, Zuordnungslogik, Workflows, Fristen,
  Prioritäten, jeweils mit Verweis auf die Datei im Bestandsprojekt.
* Je Punkt: im Plattform-Repo schon abgebildet (Verweis auf Regel in `docs/rules/` oder
  Modul), teilweise oder nicht.

### 6. Bekannte Probleme und technische Schulden

* Fehler, Sicherheitslücken, fehlende Tests, Abhängigkeiten ohne Wartung, manuelle Schritte.

### 7. Empfehlung

* Anbinden (eigenständiger Dienst über API und Webhooks), übernehmen (Modul der Plattform) oder
  ablösen, mit Begründung nach Wirtschaftlichkeit, Risiko, Aufwand und Umsetzbarkeit.
* Aufwand grob in Tagen, mit dem Hinweis, ob die Zahl gemessen oder geschätzt ist.
* Reihenfolge der Schritte und zu migrierende Daten.
* Bei "anbinden": welcher Schnittstellenvertrag der Plattform genutzt wird und welche
  Erweiterung im Bestandstool nötig ist (Beispiel: ausgehender Webhook des Tools an
  `POST /api/v1/mail/inbound/sources/{id}/classified-mails`, siehe `inbound-mail-webhook.md`).

### 8. Offene Fragen an den Betreiber

* Nummerierte Fragen mit Eigentümer. Entschiedene Fragen mit Datum der Entscheidung
  markieren, offene bleiben in `docs/OPEN_QUESTIONS.md` mit Kennung (V1, AA16-03,
  Tool-spezifische Kennung).

### Zusammenfassung in zehn Zeilen

Wie in Anhang B verlangt, am Ende des Dossiers.

## Prüfung vor der Übernahme ins Repo

* [ ] Kopf ausgefüllt, Erhebungslauf und Wissensdatenbank benannt oder als Lücke markiert.
* [ ] Jeder Abschnitt 1 bis 8 vorhanden; Lücken stehen als `[zu ergänzen durch Betreiber: ...]`.
* [ ] Keine personenbezogenen Daten, Zugangsdaten, IBAN oder Steuernummern im Text.
* [ ] Keine Gedankenstriche, Datumsformat TT.MM.JJJJ, unter 3.000 Wörtern.
* [ ] Quellenangaben je Aussage; keine Aussage über den Quelltext ohne Dateiverweis.
* [ ] Empfehlung als Vorschlag gekennzeichnet; Entscheidung des Betreibers mit Datum oder offen.
* [ ] `docs/integrations/README.md` (Tabelle und Übersicht) und `docs/OPEN_QUESTIONS.md`
      (angehängte Zeile) fortgeschrieben.
* [ ] `CHECKLISTE-BESTANDSTOOLS.md`: Zeile des Tools aktualisiert.

## Hinweis zur Verwendung durch Claude

Wird ein Dossier ohne Zugriff auf den Quelltext angelegt, entsteht nur der Teil, der aus dem
Master-Prompt und dem Plattform-Repo belegbar ist, mit dem Kopfvermerk "Quelltext liegt nicht
vor". Der Erhebungslauf im Bestandsprojekt bleibt offen und wird nicht durch Vermutungen
ersetzt.
