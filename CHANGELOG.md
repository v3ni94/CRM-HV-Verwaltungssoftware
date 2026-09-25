# Versionsverlauf MH-Verwaltungsplattform

Rückwirkend angelegt am 25.09.2026 aus den Meilenstein-Plänen (docs/plans/) und der
Git-Historie; ab jetzt wird jede Auslieferung hier fortgeschrieben. Versionsschema:
0.MINOR.PATCH bis zur Marktreife (M27/G5), Datum TT.MM.JJJJ. Die produktive Umgebung
(crm.mueller-holding.ag) fährt den jeweils zuletzt deployten Stand; ein Eintrag hier
bedeutet „im Repository fertig", nicht automatisch „deployt".

## 0.31.0, 25.09.2026 (Branch claude/webseite-crm-prompt-k29mt8, noch zu deployen)

- Banking über finAPI Access (M31, rein lesend): Bankverbindung per WebForm 2.0, dauerhafte
  Kontenzuordnung zu Objektkonten, Abruf nur auf Klick, idempotenter Umsatzimport nur
  gebuchter Umsätze, Abrufprotokolle, Trennen ohne Datenverlust; 10 Abnahmetests gegen
  Fake-Provider. Live-Voraussetzungen offen, siehe docs/BANKING-FINAPI.md.
- Rechnungs-Weiterleitung (M32): Gesellschaftsrechnungen (z. B. Telekom, AOK) per Klick oder
  automatisch für gelernte Absender an das Rechnungsprogramm (Lexware-Inbox) weiterleiten und
  in Gmail archivieren; Objektrechnungen nie automatisch. Einstellungsseite mit Absenderliste.
- Erledigte Mails und Tickets archivieren die zugehörige Nachricht im Gmail-Postfach
  (erweiterte Google-Freigabe nötig, Postfach einmal neu verbinden).
- Ticketvorlagen: empfohlene SLA-Sätze für die Hausverwaltung per Klick einfügbar (Notfall
  4 Std. mit Bereitschaftshinweis, dringende Reparatur 24 Std., Standard 72 Std., Kaution
  14 Tage mit IBAN-Pflichtfeld), danach frei anpassbar.
- WEG-Verwaltung in die Objektakte integriert: eigener Menüpunkt entfernt, /weg leitet auf den
  Objektfilter, Vorgänge (Wirtschaftsplan, Abrechnung, Sonderumlage, Versammlung) am Objekt.
- Favicon und App-Symbole aus der Bildmarke (anthrazit, Marke weiß, Punkt gold).

## 0.30.2, 25.09.2026

- BFF-Freigaben für Ticketauswertung und Vorlagen, Kontaktimport verarbeitet große CSV-Dateien
  in Stapeln vollständig (Umlaute korrekt, cp1252-Erkennung), Darstellungsdurchgang über alle
  Seiten (Zeilenumbrüche Ticketdetail, Fußzeile).
- KI-Assistent: Zeichen-Obergrenzen konfigurierbar, automatischer Wechsel auf ein Modell mit
  größerem Kontextfenster mit sichtbarem Hinweis; Chat mit Ladebalken und Gold-Akzent.

## 0.30.1, 25.09.2026

- Zwei-Faktor-Pflicht nur noch für Administratoren, vertrauenswürdige Geräte 180 Tage.
- Kontakte nach Art unterscheidbar (Eigentümer, Mieter, Verwalter, Dienstleister, Bank,
  Sonstiges) mit Filter und Badges.
- Fehlerbehebung: 500 (PendingRollbackError) beim Gmail-Postfachabruf.

## 0.30.0, 25.09.2026

- Startseite mit Ticketauswertung (Tag/Woche/Monat/Quartal/Jahr, Nutzervergleich, Grafiken).
- Mail als eigener Menüpunkt unter Übersicht; Navigationsgruppe Makler.
- Tickets: Mehrfachauswahl mit Sammel-Statuswechsel (Mitarbeiter höchstens 10, Admin
  unbegrenzt); Vorlagenverwaltung mit Checklisten und Pflichtfeldern (z. B. IBAN bei Kaution).
- U-Protokoll (Übergabe-/Abnahmeprotokolle) als eigener Dienst im Stack unter
  uprotokoll.mueller-holding.ag, verlinkt aus dem Makler-Bereich.
- „Importassistent Immoware24" heißt jetzt „Importassistent".

## 0.29.x, bis 24.09.2026 (rückwirkend zusammengefasst, vor dieser Arbeitslinie)

- M28 Makler: Müller FLOW (Inseratsverwaltung) in die Plattform überführt.
- M29 DMS: Objektübernahme (objektakte) angebunden.
- M30 (parallel in Arbeit): natives Übergabeprotokoll.
- Betrieb: Produktivdeployment auf eigenem Server (Traefik, Let's Encrypt, Backups mit age).

## 0.1.0 bis 0.27.0, Aufbauphase (rückwirkend, je Meilenstein aus docs/plans/)

- M1 Grundgerüst (Monorepo, CI, Docker), M2 Mandanten und Auth (RLS, Rollen, 2FA),
  M3 Kontakte, M4 Objekte/Einheiten/Rechtsträger, M5 Verträge, M6 Dokumente/DMS-Adapter
  (Paperless, Drive), M7 KI-Gateway mit Freigabe-Workflows, M8 Immoware24-Importassistent,
  M9 Betrieb (Backups, Runbooks, Metriken).
- M10 Buchhaltungskern (nicht führend, Gate G1 zu), M11 Bankimport CAMT.053, M12 Zuordnung
  mit Regeln, M13 Sollstellungen/Verwalterhonorar (XRechnung als Entwurf), M14 Belegeingang
  mit Vier-Augen-Prüfung, M15 Zahlläufe pain.001 (Gate G2 zu), M16 Mahnwesen (Gebühren 0,00,
  Gate zu), M17 Betriebskostenabrechnung (Gate G3 zu), M18 Auswertungen/GoBD-Export.
- M19 Tickets und Aufträge, M20 Postfach (IMAP/Gmail) mit Ticketautomatik, M21/M22 Portal-API
  für Mieter, Eigentümer und Dienstleister (Zugriffsmatrix § 18 Abs. 4 WEG), M23
  Kommunikation/Zustellung, M24 WEG-Wirtschaftsplan und Hausgeld (Gate G4 zu), M25
  Versammlung und Beschlüsse, M26 Vermietung und Mieterhöhung (Entwürfe), M27
  Lizenzierung/Marktreife (Gate G5 zu).

Hinweise: Die Gates G1 bis G5 (führende Buchhaltung, Zahlungsverkehr, Miet- und
WEG-Abrechnung, Fremdmandanten) sind bewusst geschlossen; Öffnung nur dokumentiert per
Vier-Augen-Verfahren. Details je Meilenstein in docs/plans/, offene Punkte in
docs/OPEN_QUESTIONS.md.
