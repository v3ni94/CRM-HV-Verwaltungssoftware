# M3-02 SEPA-Mandat auf der Bankverbindung des Kontakts

| Field | Content |
| --- | --- |
| ID | `M3-02` |
| Title | SEPA-Mandat auf der Bankverbindung des Kontakts: Erfassung, Nachweis, Widerruf |
| Scope | Tabelle `contact_bank_account` (Domäne `contacts`), Mandanten mit den Rechten `contacts:read`, `contacts:update`; keine Zahlungsfunktion (Freigabetor G2 unberührt) |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) für diese Regel selbst eingehalten; Fachliche Umsetzung. Die inhaltlichen Anforderungen an Mandatstexte, Vorabankündigungsfristen (Pre-Notification) und die tatsächliche Einreichung von SEPA-Lastschriften sind offene, rechtlich zu klärende Punkte, siehe M15 (Zahlungsmodul, gesperrt bis G2) und `docs/OPEN_QUESTIONS.md` |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m3_contacts_sepa_mandate.py` |
| Implementation | `mhvp.contacts.models.ContactBankAccount` (Felder `sepa_enabled`, `mandate_reference`, `mandate_signed_on`, `mandate_granted_via`, `mandate_note`, `mandate_document_id`, `mandate_scheme`, `mandate_status`, `mandate_revoked_on`), `mhvp.contacts.schemas.BankAccountIn/Out`, `mhvp.contacts.schemas.SepaMandateOut`, `mhvp.contacts.routers` (`GET /contacts/{id}/sepa-mandates`, `POST /contacts/{id}/bank-accounts/{account_id}/mandate/revoke`), Migration 0047 |
| Change reason | Operator-Anforderung: Mandatsnachweis pro Bankverbindung führen, bevor das Zahlungsmodul (M15) SEPA-Lastschriften tatsächlich einreicht, 25.09.2026 |

## Regeln

- `sepa_enabled = true` verlangt zwingend `mandate_signed_on` und `mandate_granted_via`
  sowie entweder ein verknüpftes Dokument (`mandate_document_id`, PDF-Upload über den
  bestehenden Dokumenten-Upload) oder einen Vermerk (`mandate_note`); fehlt beides, wird
  die Anfrage mit 422 abgelehnt.
- Die IBAN wird nach ISO 13616 geprüft (bestehende Validierung, `mhvp.contacts.validation`).
- Die Mandatsreferenz (`mandate_reference`) ist je Mandant eindeutig, sofern gesetzt
  (partieller eindeutiger Index `ux_contact_bank_account_tenant_mandate_reference`).
- Ändert sich bei einer vollständigen Kontaktänderung (`PUT /contacts/{id}`) die IBAN einer
  Bankverbindung, deren Mandat unter derselben Referenz aktiv war, wird das Mandat **nicht**
  automatisch widerrufen. Stattdessen legt der Dienst eine angeheftete Notiz
  (`contact_note`, Kategorie `sepa_mandate`) an und löst das Ereignis
  `contact.mandate_iban_changed` aus, damit ein Sachbearbeiter prüft, ob ein neues Mandat
  erforderlich ist.
- Ein Widerruf erfolgt ausschließlich über `POST
  /contacts/{id}/bank-accounts/{account_id}/mandate/revoke` (Recht `contacts:update`),
  setzt `mandate_status = revoked` und `mandate_revoked_on` auf das Tagesdatum und löst das
  Ereignis `contact.mandate_revoked` aus. Ein bereits widerrufenes oder nicht aktiviertes
  Mandat kann nicht erneut widerrufen werden (422).
- `GET /contacts/{id}/sepa-mandates` liefert eine kompakte, maskierte Liste (IBAN nur mit
  `mask_iban`, keine Entschlüsselung) für die Kontaktakte.
- Diese Regel begründet keine Zahlungsfunktion: Weder werden Lastschriften erzeugt noch
  eingereicht. Das ist ausdrücklich Aufgabe von `mhvp.contracts.models.SepaMandate`
  (Partei- und Rechtsträger-gebundenes Mandat samt Gläubiger-ID für den tatsächlichen
  Lastschrifteinzug), das hinter Freigabetor G2 verbleibt. Beide Modelle sind bewusst
  getrennt: `contact_bank_account` hält den Mandatsnachweis in der Kontaktakte, unabhängig
  davon, für welchen Vertrag oder Rechtsträger das Mandat später tatsächlich verwendet
  wird. Eine spätere Verknüpfung oder Konsolidierung beider Konzepte ist eine offene
  Entscheidung (siehe `docs/OPEN_QUESTIONS.md`, Eigentümer Betreiber, betroffenes Tor G2).

## Vier-Augen-Freigabe der Bankverbindung (M5-01)

Typ: Produktschutz (Regel 0.1.6, Rechnungseingang PÜ04 als Vorbild). Änderungsgrund: offene
Frage M5-01, Umsetzung vor G2.

- Jede neue oder geänderte IBAN eines Kontakts (`contact_bank_account`) erhält beim Anlegen
  oder vollständigen Ändern den Status `pending` (zur Freigabe) mit der erfassenden Person in
  `requested_by` und löst `bank_account.pending` aus. Eine IBAN, die unverändert erneut
  gespeichert wird (gleicher Fingerabdruck), behält ihren bisherigen Freigabestand.
- `POST /contacts/{id}/bank-accounts/{account_id}/approve` und `/reject` (Recht
  `contacts:approve`) setzen `approved` oder `rejected` samt `decided_by` und `decided_at`
  und lösen `bank_account.approved` oder `bank_account.rejected` aus. Die erfassende Person,
  ein Plattformzugriff und ein Aufruf ohne Benutzer dürfen nicht entscheiden
  (`GATE_FOUR_EYES`); entschieden werden kann nur ein Konto im Status `pending` (409).
- Nur `approved` Konten werden verwendet: Lastschriftlauf (`mandate_block_reason`),
  Erfassung eines SEPA-Mandats (`POST /sepa-mandates`), IBAN-Änderung eines Zahlungsauftrags
  (PÜ04) und der Stammdatenabgleich im Rechnungseingang.
- Bestandskonten aus der Zeit vor Migration 0121 stehen ebenfalls auf `pending` und müssen
  einmalig freigegeben werden.
- Die KI darf keine Freigabe erteilen; KI-Importe und Ticketvorschläge legen Konten nur als
  `pending` an.


## Portalstufe: digitales Mandat als Vorschlag (Nachtrag 27.09.2026)

Typ: Fachliche Umsetzung (Abschnitt 14 Portale) und Produktschutz (Regel 0.1.6, G2). Der
Mandatstext ist ein **Entwurf** ohne Quellenstatus im Anhang C; Wortlaut, Vorabankündigung und
Einreichung bleiben offene Entscheidung (`docs/OPEN_QUESTIONS.md` M3-03). Tests
`apps/api/tests/integration/test_m21_portal_mandate_address.py`, Portal
`apps/web-portal/src/components/portal/SepaMandateForm.test.tsx`, CRM
`apps/web-crm/src/components/contacts/PortalProposalsPanel.test.tsx`. Migration 0174.

- `GET /api/v1/portal/sepa-mandates/preview?contract_id=` liefert für einen eigenen Vertrag
  (Zugriffsmatrix, sonst 404) den Mandatstext mit Gläubiger-Identifikationsnummer des
  Rechtsträgers (`legal_entity.sepa_creditor_id`, Rückfall Mandanteneinstellung wie im
  Lastschriftlauf, `mhvp.accounting.direct_debit.creditor_identifier`), Mandatsreferenz
  (Vertragsnummer, Datum, Zufallssuffix, höchstens 35 Zeichen) und Zahlungsart
  `wiederkehrende Zahlung` (SEPA-Basislastschrift). Fehlt die Gläubiger-ID, wird mit 422
  abgelehnt; die Verwaltung trägt sie im CRM ein.
- `POST /api/v1/portal/sepa-mandates` verlangt `confirmed = true`, prüft die IBAN nach ISO
  13616 (`mhvp.contacts.validation.normalise_iban`) und speichert den bestätigten Text,
  Zeitstempel, IP-Adresse und Client als Textform-Nachweis: Tabelle
  `portal_sepa_mandate_proposal` (IBAN verschlüsselt) und ein erzeugtes PDF
  (`DocumentSource.GENERATED`, verknüpft mit Kontakt und Vertrag, für die Rolle des Vertrags
  sichtbar). Ereignis `portal.sepa_mandate.proposed`.
- Der Vorschlag wird **nie** von selbst aktiv. `POST
  /api/v1/portal-admin/sepa-mandate-proposals/{id}/decide` (Recht `contacts:update`) übernimmt
  oder lehnt ab (`portal.sepa_mandate.accepted` oder `.rejected`, zweite Entscheidung 409).
  Übernahme legt nur eine `contact_bank_account`-Zeile mit Mandatsnachweis an (`sepa_enabled`,
  `mandate_reference`, `mandate_signed_on`, `mandate_granted_via = portal`,
  `mandate_document_id`); die IBAN bleibt `pending` bis zur Vier-Augen-Freigabe (M5-01). Ein
  `sepa_mandate` (Einzugsmandat) entsteht hier nicht; es wird weiterhin nur über den
  freigegebenen CRM-Pfad und erst nach G2 verwendet. Die KI entscheidet nie.
- Portalnutzer sehen ausschließlich ihre eigenen Vorschläge (`GET /api/v1/portal/sepa-mandates`);
  ein anderer Mandant sieht und entscheidet nichts (RLS, 404).
