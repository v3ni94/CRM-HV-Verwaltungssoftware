# Prüfmappe für den Rechtsanwalt (V13), Entwurf

Stand: 02.10.2026. Anlage zu OPEN_QUESTIONS V13 und MASTER-PROMPT 19.1. Die Mappe nennt, welche Funktionen technisch
umgesetzt sind und wo sie beschrieben sind. Sie enthält keine rechtliche Bewertung. Die Bewertung ist Sache des
Rechtsanwalts, das Ergebnis trägt der Betreiber in OPEN_QUESTIONS V13 ein. Alle Funktionen sind je Mandant hinter
Schaltern oder Freigabestufen gesperrt oder standardmäßig aus, soweit unten angegeben.

## 1. Barrierefreiheit des Portals (BFSG-Anwendbarkeit)

| Frage an den Rechtsanwalt | Umgesetzt | Fundstelle |
| --- | --- | --- |
| Ist das Portal ein Angebot im Anwendungsbereich des BFSG, für welche Rechtsträger und Nutzergruppen | Technische Maßnahmen und Prüfprotokoll vorhanden, Anwendbarkeit nicht entschieden | `docs/handbuch/barrierefreiheit.md`, `docs/OPEN_QUESTIONS.md` V13 |
| Reichen Prüfumfang und Nachweis | Automatisierte Prüfung (Barrierefreiheitstest) im CI, manuelle Prüfung offen | `docs/handbuch/barrierefreiheit.md`; Prüfumfang im Handbuch zu verifizieren |

## 2. Virtuelle Versammlung und Umlaufbeschluss

| Frage an den Rechtsanwalt | Umgesetzt | Fundstelle |
| --- | --- | --- |
| Zulässigkeit der virtuellen oder hybriden Versammlung, Grundlage und Beschlussfassung der Gemeinschaft | Technisch umgesetzt, Mandantenschalter Standard aus, Freischaltung nur nach Rechtsprüfung | `docs/rules/M25-03-einladung-virtuell.md`, `docs/rules/AD06-online-versammlung.md` |
| Mehrheitsregeln und Stimmrechte | Prüfung der Mehrheit als Hilfe, keine Rechtsaussage | `docs/rules/M25-01-mehrheitsregeln.md` |
| Umlaufbeschluss in Textform, Fristen, Zustimmungen | Erfassung mit Nachweis, keine Fristberechnung als Rechtsfrist | `docs/rules/M25-02-umlaufbeschluss.md`, `docs/handbuch/weg.md` |
| Einsicht und Prüfrolle Beirat | Umgesetzt, Umfang der Stellungnahme ausgewiesen | `docs/rules/M25-W3-einsicht-pruefrolle.md` |

## 3. GoBD und Verfahrensdokumentation

| Frage an den Steuerberater und Rechtsanwalt | Umgesetzt | Fundstelle |
| --- | --- | --- |
| Genügt der Entwurf der Verfahrensdokumentation als Grundlage | Entwurf als Handbuchkapitel und Dokument, keine Zertifizierung | `docs/handbuch/verfahrensdokumentation.md` |
| Unveränderbarkeit, Storno statt Überschreiben, Festschreibung | Invarianten B02, B03, B04 in der Plattform | `docs/rules/README.md` (B02 bis B04) |
| Aufbewahrung und Löschung | Entwurf Löschkonzept, V17 offen | `docs/datenschutz/LOESCHKONZEPT.md`, `docs/datenschutz/V17-MATRIXVORLAGE.md` |

## 4. Anmerkungen

* Die Plattform behauptet keine Rechtmäßigkeit einer Funktion. Jede Seite und jedes Dokument trägt den Hinweis auf
  Entwurf oder Vorschlag, soweit eine Rechtsfolge betroffen ist.
* V8 (Kontenrahmen): Der Freigabeworkflow je Mandant ist gebaut (Entwurf, zur Prüfung, freigegeben); die Freigabe der
  Kontenrahmenvorlage durch den Betreiber und den Steuerberater steht aus (OPEN_QUESTIONS V8).
