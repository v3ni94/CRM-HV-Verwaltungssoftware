# AP14: Auskunftsexport je Quelle, Protokolle, Übermittlungen, Pseudonymisierung in Logs

- ID: AP14-auskunft-protokolle
- Geltungsbereich: contacts/access_export, contacts/access_export_sources, contacts/access_log, automation (Webhooks), integrations/schadenstool, core/redaction, documents/defaults
- Quellenstatus (Anhang C): 7.11 S06 (Auskunft, Zugriffe, Übermittlungen), S04 (Aufbewahrung), Abschnitt 16 (Pseudonymisierung in Logs); Fachliche Umsetzung und Produktschutz, keine neue Rechtsregel
- Abnahmefall (Anhang D): Auskunft nach Art. 15 vollständig je Quelle mit Prüfschritt; keine eigenständige Zahl
- Änderungsgrund: Lückenanalyse GAM (GAM-402, 403, 407 bis 411), Welle 26

## Regeln

1. Jede Tabelle mit Fremdschlüssel auf contact.id ist für die Auskunft eingeordnet (weitere Quelle mit Feldliste und bestehendem Schalter, bereits enthalten, oder ausgeschlossen mit Grund). Schalter aus bedeutet: nur Anzahl.
2. Das Verarbeitungsprotokoll umfasst Ereignisse der Entitäten der Person und Ereignisse, deren Nutzdaten die Person nennen, nur mit Art und Zeitpunkt; Feldänderungen nur mit Feldnamen. Übermittlungen an Empfänger stehen in einer eigenen Rubrik.
3. Übergabe und Anhänge an den Schadenbearbeiter verlangen dieselbe Weitergabeentscheidung wie Aufträge an Dienstleister (consent_rules.data_sharing_decision); Ablehnung 409 MHVP-SDT-0007. Die Grundlage steht im Übermittlungsereignis.
4. Jede eingereihte Webhookübermittlung erzeugt automation.webhook_transfer (Zielhost, Personenbezug, Prüfstatus des Ziels im Verarbeitungsverzeichnis). Feldauswahl payload_scope je Aktion; Standard full (heutiges Verhalten), Frage AP14-02.
5. Personenbezogene Schlüssel in Logereignissen (unter anderem address, email, phone, iban, name, to, from_address) werden durch einen gekürzten Hash ersetzt.
6. Zugriffsprotokoll access_log nur bei eingeschaltetem Mandantenschalter, ohne Inhalte; Umfang und Aufbewahrung offen (AP14-01).
7. Aufbewahrungsklasse booking_vouchers getrennt von accounting_records, ohne Frist vorbelegt (Platzhalter dauerhaft, Freigabe gesperrt bis Matrix V17).
