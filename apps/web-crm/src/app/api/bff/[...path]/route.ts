/**
 * Backend-for-frontend proxy for the CRM screens (contacts, AI, imports, accounting, bank, HOA, letting, tickets). Only the listed API operations are
 * reachable; the bearer token is added server side from the httpOnly cookie. Mutating methods
 * require a same-origin Origin header (CSRF, together with SameSite=Strict cookies).
 */
import { serverFetch } from "@/lib/api-server";
import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";

const ID = "[0-9a-fA-F-]{36}";
const ALLOWED: { method: string; pattern: RegExp }[] = [
  { method: "GET", pattern: /^search$/ },
  { method: "GET", pattern: /^mail\/oauth\/google$/ },
  { method: "PUT", pattern: /^mail\/oauth\/google$/ },
  { method: "POST", pattern: /^mail\/oauth\/google\/start$/ },
  { method: "PATCH", pattern: new RegExp(`^mail/mailboxes/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^mail/mailboxes/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^mail/mailboxes/${ID}/users$`) },
  { method: "POST", pattern: new RegExp(`^mail/mailboxes/${ID}/sync$`) },
  { method: "GET", pattern: /^mail\/mailboxes$/ },
  // Mail (M20): message list, thread view, reply drafts and the four-eyes approval flow.
  { method: "GET", pattern: /^mail\/messages$/ },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/thread$`) },
  { method: "PATCH", pattern: new RegExp(`^mail/messages/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^mail/messages/${ID}/draft$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/(reply-draft|submit|approve|reject|ticket|forward-invoice)$`) },
  // Rechnung aus E-Mail-Anhang erfassen (M14 KI-Extraktion).
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/attachments/${ID}/invoice-extraction$`) },
  { method: "GET", pattern: /^mail\/invoice-forwarding$/ },
  { method: "PUT", pattern: /^mail\/invoice-forwarding$/ },
  // KI-Vorschläge und Playbooks (M20 Übernahme aus dem Immoware Hub).
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/suggest$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/apply-playbook$`) },
  { method: "GET", pattern: /^mail\/playbooks$/ },
  { method: "POST", pattern: /^mail\/playbooks$/ },
  { method: "PATCH", pattern: new RegExp(`^mail/playbooks/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^mail/playbooks/${ID}$`) },
  { method: "GET", pattern: /^workspace\/(search|notifications|calendar|filters|dashboard\/stats)$/ },
  { method: "POST", pattern: /^workspace\/(notifications\/read|calendar|calendar\/refresh|bulk)$/ },
  { method: "PUT", pattern: /^workspace\/filters$/ },
  // Tagesübersicht, Fristenliste und Schalter der Tagesjobs (A40, A41).
  { method: "GET", pattern: /^workspace\/(digest|deadlines|job-settings)$/ },
  { method: "PUT", pattern: /^workspace\/job-settings$/ },
  { method: "DELETE", pattern: /^workspace\/(calendar|filters)\/[0-9a-f-]{36}$/ },
  // Google-Kalender-Termine (M23-02 bidirektional): ändern/löschen des verknüpften Google-Events
  // und, nur nach ausdrücklicher Bestätigung, Einladung an externe Teilnehmer (M23-05).
  { method: "PATCH", pattern: /^workspace\/calendar\/google\/(default|own)\/[^/]+$/ },
  { method: "DELETE", pattern: /^workspace\/calendar\/google\/(default|own)\/[^/]+$/ },
  { method: "POST", pattern: /^workspace\/calendar\/google\/(default|own)\/[^/]+\/invite$/ },
  { method: "GET", pattern: /^contacts$/ },
  { method: "POST", pattern: /^contacts$/ },
  { method: "GET", pattern: /^contacts\/duplicates$/ },
  { method: "GET", pattern: new RegExp(`^contacts/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^contacts/${ID}/name$`) },
  { method: "PUT", pattern: new RegExp(`^contacts/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^contacts/${ID}$`) },
  {
    method: "GET",
    pattern: new RegExp(`^contacts/${ID}/(export|notes|consents|duplicates|sepa-mandates)$`),
  },
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/(notes|consents)$`) },
  { method: "POST", pattern: new RegExp(`^consents/${ID}/revoke$`) },
  {
    method: "POST",
    pattern: new RegExp(`^contacts/${ID}/bank-accounts/${ID}/mandate/revoke$`),
  },
  // AI assistant (M7): conversations, runs, proposals, import runs, provider settings.
  { method: "GET", pattern: /^ai\/conversations$/ },
  // Tenant members, roles and settings (settings area).
  { method: "GET", pattern: /^tenant\/members$/ },
  { method: "POST", pattern: /^tenant\/members$/ },
  { method: "PATCH", pattern: new RegExp(`^tenant/members/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^tenant/members/${ID}/reset-password$`) },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/roles$`) },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/competences$`) },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/mobile-phone$`) },
  // A37: Zugriffsbereich je Rechtsträger (Steuerberater).
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/legal-entities$`) },
  { method: "GET", pattern: /^tenant\/legal-entities$/ },
  { method: "GET", pattern: /^tenant\/competence-catalogue$/ },
  { method: "GET", pattern: /^tenant\/roles$/ },
  { method: "POST", pattern: /^tenant\/roles$/ },
  { method: "PUT", pattern: new RegExp(`^tenant/roles/${ID}/permissions$`) },
  // Portalrechte je Rolle (M2-08 entschieden, docs/rules/M2-07.md).
  { method: "GET", pattern: /^tenant\/portal-role-permissions$/ },
  { method: "PUT", pattern: /^tenant\/portal-role-permissions$/ },
  { method: "POST", pattern: /^tenant\/portal-role-permissions\/resync$/ },
  { method: "GET", pattern: /^tenant\/settings$/ },
  { method: "PATCH", pattern: /^tenant\/settings$/ },
  // Rechnungsstellung und Steuer (M13-04/M18-01, operator decision 25.09.2026).
  { method: "GET", pattern: /^tenant\/billing-settings$/ },
  { method: "PATCH", pattern: /^tenant\/billing-settings$/ },
  // Own account: password change and session list (Meine Daten).
  { method: "POST", pattern: /^auth\/password$/ },
  { method: "GET", pattern: /^auth\/sessions$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/sessions/${ID}$`) },
  { method: "GET", pattern: /^auth\/trusted-devices$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/trusted-devices/${ID}$`) },
  // Platform: tenant and tenant administrator creation (platform admins only, checked by the API).
  { method: "POST", pattern: /^platform\/tenants$/ },
  { method: "POST", pattern: /^platform\/users$/ },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/members$`) },
  { method: "POST", pattern: /^ai\/conversations$/ },
  { method: "GET", pattern: new RegExp(`^ai/conversations/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^ai/conversations/${ID}/messages$`) },
  { method: "GET", pattern: new RegExp(`^ai/runs/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^ai/proposals/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^ai/proposals/${ID}/(apply|reject)$`) },
  { method: "GET", pattern: /^ai\/usage$/ },
  { method: "GET", pattern: /^ai\/providers$/ },
  { method: "PUT", pattern: /^ai\/routing$/ },
  { method: "PUT", pattern: /^ai\/invoice-intake-auto$/ },
  { method: "PUT", pattern: /^ai\/providers\/(anthropic|openai)$/ },
  { method: "POST", pattern: /^ai\/providers\/(anthropic|openai)\/release$/ },
  // Verbindungstest je Stufe (Einstellungen, KI-Anbieter); erteilt keine Freigabe.
  { method: "POST", pattern: /^ai\/providers\/(anthropic|openai)\/test$/ },
  // Wissensbasis je Mandant und Objekt (Welle 3 Punkt 14, M34).
  { method: "GET", pattern: /^ai\/knowledge$/ },
  { method: "POST", pattern: /^ai\/knowledge$/ },
  { method: "PUT", pattern: new RegExp(`^ai/knowledge/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^ai/knowledge/${ID}$`) },
  // Mail-Vorbereitung (M34).
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/preparation$`) },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/preparation$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/preparation/correct$`) },
  { method: "GET", pattern: /^imports$/ },
  { method: "GET", pattern: new RegExp(`^imports/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^imports/${ID}/undo$`) },
  // Immoware24 import assistant (M8, 13.1).
  { method: "GET", pattern: /^imports\/immoware24\/(fields|mappings|overview)$/ },
  { method: "POST", pattern: /^imports\/immoware24\/(mappings|files)$/ },
  { method: "GET", pattern: new RegExp(`^imports/immoware24/files/${ID}(/rows|/reconciliation)?$`) },
  { method: "POST", pattern: new RegExp(`^imports/immoware24/files/${ID}/(validate|test-run|apply)$`) },
  // Immoware24-Listen (Objektdaten, Kontakte) als CSV-Upload, Testlauf oder Übernahme.
  { method: "POST", pattern: /^imports\/immoware24\/lists\/(objektdaten|kontakte)$/ },
  // Evaluations (M18, 7.5): liquidity, payments by debtor, revenue; read only.
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/liquidity$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/payments-by-debtor$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/revenue$`) },
  // DATEV account mapping (A36, M18-01): list, create, change, delete, CSV import, report.
  { method: "GET", pattern: /^accounting\/datev-mappings$/ },
  { method: "POST", pattern: /^accounting\/datev-mappings$/ },
  { method: "POST", pattern: /^accounting\/datev-mappings\/import$/ },
  { method: "GET", pattern: /^accounting\/datev-mappings\/report$/ },
  { method: "PATCH", pattern: new RegExp(`^accounting/datev-mappings/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^accounting/datev-mappings/${ID}$`) },
  // Audit export per legal entity and period (A26, 7.7, D55): create, status, list, ZIP download.
  { method: "POST", pattern: /^accounting\/audit-exports$/ },
  { method: "GET", pattern: /^accounting\/audit-exports$/ },
  { method: "GET", pattern: new RegExp(`^accounting/audit-exports/${ID}(/download)?$`) },
  // Receivable runs (M13): preview and posting; postings stay non leading until G1.
  { method: "POST", pattern: /^accounting\/receivable-runs$/ },
  { method: "GET", pattern: new RegExp(`^accounting/receivable-runs/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/receivable-runs/${ID}/post$`) },
  // Bank (M11, M12): statement import, proposals, confirmed booking, ignore with reason.
  { method: "POST", pattern: /^banking\/imports$/ },
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/candidates$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/(book|ignore)$`) },
  // Payment orders (M15): approval and cancel only; the payment file needs G2.
  { method: "POST", pattern: new RegExp(`^banking/payment-orders/${ID}/(approve|cancel)$`) },
  { method: "GET", pattern: /^banking\/payment-orders$/ },
  // finAPI (M11-finapi): read only aggregator onboarding, consent, fetch (Stufen 1-3).
  { method: "GET", pattern: /^banking\/finapi\/config$/ },
  { method: "PUT", pattern: /^banking\/finapi\/config$/ },
  { method: "GET", pattern: /^banking\/finapi\/connections$/ },
  { method: "POST", pattern: /^banking\/finapi\/connections$/ },
  { method: "POST", pattern: new RegExp(`^banking/finapi/connections/${ID}/(check|reauthorize|disconnect|fetch)$`) },
  { method: "POST", pattern: new RegExp(`^banking/finapi/accounts/${ID}/(assign|fetch)$`) },
  // Bankkontenauswahl: Kontenliste je Objekt und Rechtsträger, Zuordnung und Standardkonto.
  // Nur lesend und organisatorisch, kein Zahlungsverkehr (G2 bleibt geschlossen).
  { method: "GET", pattern: /^banking\/accounts$/ },
  { method: "PUT", pattern: new RegExp(`^banking/accounts/${ID}/assignments$`) },
  { method: "DELETE", pattern: new RegExp(`^banking/accounts/${ID}/assignments/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^banking/accounts/${ID}/legal-entity-default$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/bank-account-options$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/legal-entities$`) },
  // Rechnung zu Bankumsatz abgleichen und Zahlungsvorschlag (M11-finapi Stage 3, G2 gesperrt).
  { method: "GET", pattern: new RegExp(`^banking/invoice-matching/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^banking/invoice-matching/${ID}/match$`) },
  // Dunning (M16): preview and approval by a second person; fee amount and Basiszinssatz are
  // only active once the operator has entered them (V7).
  { method: "GET", pattern: /^accounting\/dunning-settings$/ },
  { method: "PUT", pattern: /^accounting\/dunning-settings$/ },
  { method: "POST", pattern: /^accounting\/dunning-settings\/presets$/ },
  { method: "POST", pattern: /^accounting\/dunning-runs$/ },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-runs/${ID}/approve$`) },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/mark-sent$`) },
  // Dunning letters and Mahnbescheid preparation as PDF drafts (M16-02, A31, A33): preview
  // returns the PDF, the second endpoint files it; nothing is sent, no application is filed.
  { method: "POST", pattern: /^accounting\/dunning-settings\/letter-preview$/ },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/letter(-preview)?$`) },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/mahnbescheid(-preview)?$`) },
  {
    method: "POST",
    pattern: new RegExp(`^accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung$`),
  },
  {
    method: "GET",
    pattern: new RegExp(`^accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung$`),
  },
  // Operating cost statements (M17): drafting and status steps; issuing needs G3 (API).
  { method: "POST", pattern: /^statements$/ },
  { method: "POST", pattern: new RegExp(`^statements/${ID}/(cost-items|calculate|transition|new-version)$`) },
  // KI-Plausibilität eines Abrechnungsentwurfs (A35): Hinweise als Vorschlag, keine Wirkung.
  { method: "GET", pattern: new RegExp(`^(hoa/)?statements/${ID}/ai-check$`) },
  { method: "POST", pattern: new RegExp(`^(hoa/)?statements/${ID}/ai-check$`) },
  // Owner statements (M17, A06): drafts; the PDF needs G3 (API).
  { method: "GET", pattern: /^billing\/owner-statements$/ },
  { method: "GET", pattern: new RegExp(`^billing/owner-statements/${ID}$`) },
  { method: "POST", pattern: /^billing\/owner-statements$/ },
  { method: "POST", pattern: new RegExp(`^billing/owner-statements/${ID}/(calculate|approve)$`) },
  // HOA (M24, M25): drafts, calculation, resolution bound to the snapshot, meeting steps.
  // Issuing, due and posting of statements need G4 (checked by the API).
  { method: "POST", pattern: /^hoa\/(plans|statements|meetings|resolutions|special-levies)$/ },
  { method: "POST", pattern: new RegExp(`^hoa/special-levies/${ID}/(calculate|resolve|apply|amend)$`) },
  { method: "POST", pattern: /^hoa\/majority-rules$/ },
  { method: "POST", pattern: new RegExp(`^hoa/plans/${ID}/(items|calculate|transition|apply)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/statements/${ID}/(costs|calculate|transition|post|new-version)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/(agenda|invite|attendance)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/agenda/${ID}/votes$`) },
  { method: "GET", pattern: new RegExp(`^hoa/agenda/${ID}/tally$`) },
  { method: "POST", pattern: new RegExp(`^hoa/agenda/${ID}/announce$`) },
  // Letting (M26): rent increase process (sending needs G3, checked by the API), prospects.
  { method: "POST", pattern: /^letting\/(rent-increases|prospects)$/ },
  { method: "POST", pattern: new RegExp(`^letting/rent-increases/${ID}/actions$`) },
  { method: "PATCH", pattern: new RegExp(`^letting/prospects/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^letting/prospects/${ID}$`) },
  // Makler (M28-01): listings for rent and sale. No FLOWFACT connection.
  { method: "GET", pattern: /^letting\/listings$/ },
  { method: "GET", pattern: /^letting\/listings\/prefill$/ },
  { method: "GET", pattern: new RegExp(`^letting/listings/${ID}$`) },
  { method: "POST", pattern: /^letting\/listings$/ },
  { method: "PATCH", pattern: new RegExp(`^letting/listings/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^letting/listings/${ID}$`) },
  // OpenImmo-Export (M26-02): read only, no portal upload.
  { method: "GET", pattern: new RegExp(`^letting/listings/${ID}/openimmo-check$`) },
  { method: "GET", pattern: new RegExp(`^letting/listings/${ID}/openimmo\\.xml$`) },
  { method: "GET", pattern: new RegExp(`^letting/listings/${ID}/openimmo\\.zip$`) },
  { method: "GET", pattern: /^letting\/listings\/openimmo\.zip$/ },
  // Bilder je Anzeige (M26-02): Liste, Upload (multipart), Verknüpfen, Lösen, Anzeige.
  { method: "GET", pattern: new RegExp(`^letting/listings/${ID}/images$`) },
  { method: "POST", pattern: new RegExp(`^letting/listings/${ID}/images$`) },
  { method: "POST", pattern: new RegExp(`^letting/listings/${ID}/images/link$`) },
  { method: "DELETE", pattern: new RegExp(`^letting/listings/${ID}/images/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^letting/listings/${ID}/images/${ID}/content$`) },
  // Makler (M28-01): property and unit pickers for the listing creation form.
  // Übergabeprotokolle (M30): protocol, sub records, photos, signatures, completion, versions.
  { method: "GET", pattern: /^handover\/protocols$/ },
  { method: "GET", pattern: /^handover\/protocols\/prefill$/ },
  { method: "POST", pattern: /^handover\/protocols$/ },
  { method: "GET", pattern: new RegExp(`^handover/protocols/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^handover/protocols/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^handover/protocols/${ID}/hints$`) },
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/(documents|signatures|complete|versions|status|dispatches)$`) },
  { method: "DELETE", pattern: new RegExp(`^handover/protocols/${ID}/(documents|signatures)/${ID}$`) },
  // Portalzugang eines Beteiligten (M30 Stufe 3): einrichten und beenden.
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/participants/${ID}/portal-access$`) },
  { method: "DELETE", pattern: new RegExp(`^handover/protocols/${ID}/participants/${ID}/portal-access$`) },
  // Gehilfenzugänge (M30, ported from U-Protokoll): list, create, revoke, resend.
  { method: "GET", pattern: new RegExp(`^handover/protocols/${ID}/helper-access$`) },
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/helper-access$`) },
  { method: "DELETE", pattern: new RegExp(`^handover/protocols/${ID}/helper-access/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/helper-access/${ID}/resend$`) },
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/helper-access/${ID}/invitation-draft$`) },
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/helper-access/${ID}/invitation-letter$`) },
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/(participants|meters|rooms|defects|keys|items|notes)(/order)?$`) },
  { method: "PATCH", pattern: new RegExp(`^handover/protocols/${ID}/(participants|meters|rooms|defects|keys|items|notes)/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^handover/protocols/${ID}/(participants|meters|rooms|defects|keys|items|notes)/${ID}$`) },
  { method: "GET", pattern: /^properties$/ },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/units$`) },
  // Makler (M28 stage 4, docs/rules/M28-01.md): FLOW SQL dump import preview and apply.
  { method: "POST", pattern: /^letting\/flow-import\/preview$/ },
  { method: "GET", pattern: new RegExp(`^letting/flow-import/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^letting/flow-import/${ID}/apply$`) },
  // Rent law rule set (M26-01): platform administrators only (checked by the API).
  { method: "PUT", pattern: /^platform\/rent-law\/rules\/[a-z_]{2,40}$/ },
  { method: "POST", pattern: /^platform\/rent-law\/cap-areas$/ },
  { method: "PUT", pattern: new RegExp(`^platform/rent-law/cap-areas/${ID}$`) },
  // Properties (M4): creation only; reads go through the server components.
  { method: "POST", pattern: /^properties$/ },
  // Tickets (M19).
  { method: "POST", pattern: /^tickets$/ },
  { method: "PATCH", pattern: new RegExp(`^tickets/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/comments$`) },
  // Ticketvorlagen (Checkliste, Zusatzfelder inkl. IBAN) und Sammelstatuswechsel (M19-02).
  { method: "GET", pattern: /^tickets\/templates$/ },
  { method: "POST", pattern: /^tickets\/templates$/ },
  { method: "GET", pattern: new RegExp(`^tickets/templates/${ID}$`) },
  // Regel-Engine Stufe 1 (A38): Regeln, Aktivierung, Testlauf ohne Wirkung, Protokoll.
  { method: "GET", pattern: /^automation\/(meta|rules|runs)$/ },
  { method: "POST", pattern: /^automation\/rules$/ },
  { method: "GET", pattern: new RegExp(`^automation/rules/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^automation/rules/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^automation/rules/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^automation/rules/${ID}/(activate|test)$`) },
  { method: "PATCH", pattern: new RegExp(`^tickets/templates/${ID}$`) },
  // Antwortvorlagen (operator 26.09.2026): CRUD, Platzhalter, Vorschau je Ticket und Antwort
  // aus dem Ticket (nur nach Bestätigung, über den bestehenden Freigabeweg).
  { method: "GET", pattern: /^tickets\/reply-templates(\/placeholders)?$/ },
  { method: "POST", pattern: /^tickets\/reply-templates$/ },
  { method: "GET", pattern: new RegExp(`^tickets/reply-templates/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^tickets/reply-templates/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^tickets/reply-templates/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/reply-templates/${ID}/preview$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/reply$`) },
  { method: "PATCH", pattern: new RegExp(`^tickets/${ID}/checklist/[a-zA-Z0-9_-]{1,64}$`) },
  { method: "POST", pattern: /^tickets\/bulk-status$/ },
  // Tickets zusammenführen (M36): Zielsuche über die Liste (q), Vorschau über das Detail.
  { method: "GET", pattern: /^tickets$/ },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}$`) },
  // Stammdatenänderung aus der Ticket-Mail (Vorschlag, Entscheidung, Antwortentwurf; 26.09.2026).
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/proposals$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/proposals/(contact-change|${ID}/(accept|correct|reject|reply-draft))$`) },
  { method: "POST", pattern: /^tickets\/merge$/ },
  { method: "GET", pattern: new RegExp(`^properties/${ID}$`) },
  // Zuweiser mit Grund (operator 25.09.2026, mail-optimierung M20).
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/assignees$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/assignees$`) },
  { method: "DELETE", pattern: new RegExp(`^tickets/${ID}/assignees/${ID}$`) },
  // Rechnung zuordnen (M11-finapi Stage 3): Kategorie Rechnung, Jahresablage im Objektordner.
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/attach-invoice$`) },
  // Paperless-Dokumente in Ticket- und Objektansicht (M31).
  { method: "GET", pattern: new RegExp(`^properties/${ID}/dms-documents$`) },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/dms-documents$`) },
  { method: "GET", pattern: /^dms-documents\/[0-9]+\/file$/ },
  // DMS-Anbindung (Einstellungen): Paperless und Google Drive.
  { method: "GET", pattern: /^dms-connections$/ },
  { method: "PUT", pattern: /^dms-connections\/(paperless|google_drive)$/ },
  // Objektakte-Übernahme (M35 Stufe 3): Review-Center, Klassifikationsregeln, Vollständigkeit.
  { method: "GET", pattern: /^objektakte\/review$/ },
  { method: "GET", pattern: new RegExp(`^objektakte/review/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^objektakte/review/${ID}/(decide|ask-ai)$`) },
  { method: "POST", pattern: /^objektakte\/review\/bulk-decide$/ },
  { method: "GET", pattern: /^objektakte\/classification-rules$/ },
  { method: "POST", pattern: /^objektakte\/classification-rules$/ },
  { method: "PATCH", pattern: new RegExp(`^objektakte/classification-rules/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^objektakte/classification-rules/${ID}$`) },
  { method: "GET", pattern: /^objektakte\/required-documents$/ },
  { method: "POST", pattern: /^objektakte\/required-documents$/ },
  { method: "DELETE", pattern: new RegExp(`^objektakte/required-documents/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^objektakte/properties/${ID}/completeness$`) },
  // Listengenerierung (M35 Stufe 4): Anforderungslisten und Dokumentenübersicht, JSON und CSV.
  { method: "GET", pattern: /^objektakte\/lists\/missing-documents(\/export)?$/ },
  // Personenlisten und Ablage einer Liste als Dokument (M35 Stufe 4, Rest).
  { method: "GET", pattern: new RegExp(`^objektakte/properties/${ID}/lists/(owners|tenants)(/export)?$`) },
  {
    method: "POST",
    pattern: new RegExp(`^objektakte/properties/${ID}/lists/(missing-documents|documents|owners|tenants)/store$`),
  },
  {
    method: "GET",
    pattern: new RegExp(`^objektakte/properties/${ID}/lists/(missing-documents|documents)(/export)?$`),
  },
  {
    method: "POST",
    pattern: new RegExp(`^objektakte/properties/${ID}/completeness/nachforderungsschreiben$`),
  },
  // Objektakte-Übernahme, Stufe 4/5 (Synchronisationsstand, Löschmarkierungen, KI-Kosten).
  { method: "GET", pattern: /^objektakte\/sync$/ },
  { method: "PUT", pattern: /^objektakte\/sync$/ },
  { method: "POST", pattern: /^objektakte\/sync\/runs$/ },
  { method: "GET", pattern: /^objektakte\/sync\/deletions$/ },
  { method: "GET", pattern: /^objektakte\/ai-calls\/summary$/ },
  { method: "GET", pattern: /^document-categories$/ },
  // SLA und Bereitschaft (M21 Übernahme aus dem Immoware Hub).
  { method: "GET", pattern: /^sla\/(rules|clocks|on-call|on-call\/current|alerts|calendar)$/ },
  { method: "GET", pattern: new RegExp(`^sla/rules/${ID}/steps$`) },
  { method: "GET", pattern: new RegExp(`^sla/tickets/${ID}/sla$`) },
  { method: "POST", pattern: /^sla\/rules$/ },
  { method: "POST", pattern: /^sla\/rules\/presets$/ },
  { method: "PATCH", pattern: new RegExp(`^sla/rules/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^sla/rules/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^sla/rules/${ID}/steps$`) },
  { method: "DELETE", pattern: new RegExp(`^sla/steps/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^sla/clocks/${ID}/(pause|resume)$`) },
  { method: "POST", pattern: /^sla\/on-call$/ },
  { method: "DELETE", pattern: new RegExp(`^sla/on-call/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^sla/alerts/${ID}/ack$`) },
  { method: "PUT", pattern: /^sla\/calendar$/ },
  { method: "GET", pattern: /^sla\/sms-gateway$/ },
  { method: "PUT", pattern: /^sla\/sms-gateway$/ },
  { method: "POST", pattern: /^sla\/sms-gateway\/test$/ },
  { method: "GET", pattern: /^sla\/whatsapp-config$/ },
  { method: "PUT", pattern: /^sla\/whatsapp-config$/ },
  { method: "POST", pattern: /^sla\/whatsapp-config\/test$/ },
  // Immoware24-Lesezugriff per DAV (M32): Anbindung, Läufe, Dokumente, Kontakte, Termine.
  { method: "GET", pattern: /^immoware\/connection$/ },
  { method: "PUT", pattern: /^immoware\/connection$/ },
  { method: "POST", pattern: /^immoware\/connection\/check$/ },
  { method: "POST", pattern: /^immoware\/connection\/diagnose$/ },
  { method: "POST", pattern: /^immoware\/sync\/(webdav|carddav|caldav)$/ },
  { method: "GET", pattern: /^immoware\/sync\/runs$/ },
  { method: "GET", pattern: /^immoware\/documents$/ },
  { method: "GET", pattern: new RegExp(`^immoware/documents/${ID}/file$`) },
  { method: "POST", pattern: new RegExp(`^immoware/documents/${ID}/take-over$`) },
  { method: "POST", pattern: /^immoware\/documents\/take-over-folder$/ },
  { method: "GET", pattern: /^immoware\/contacts$/ },
  { method: "POST", pattern: new RegExp(`^immoware/contacts/${ID}/match$`) },
  { method: "POST", pattern: new RegExp(`^immoware/contacts/${ID}/create-contact$`) },
  { method: "POST", pattern: /^immoware\/contacts\/take-over$/ },
  { method: "GET", pattern: /^immoware\/events$/ },
  // Lernphase Immoware24 (M33, Uebernahme des Moduls Learning aus dem Immoware Hub).
  { method: "POST", pattern: /^immoware\/learning\/runs$/ },
  { method: "GET", pattern: /^immoware\/learning\/runs$/ },
  { method: "GET", pattern: new RegExp(`^immoware/learning/runs/${ID}$`) },
  // Incoming invoices (M14): capture, review steps, IBAN confirmation, release, posting.
  { method: "POST", pattern: /^accounting\/invoices$/ },
  { method: "POST", pattern: new RegExp(`^accounting/invoices/${ID}/(reviews|confirm-iban|release|post)$`) },
  // Beleg aus Paperless holen und als Rechnung erfassen (M14 KI-Extraktion, manuelle Aktion).
  { method: "POST", pattern: /^invoices\/intake\/paperless$/ },
  // Belegeingang (M14): KI-Entwürfe aus Upload, Mail-Anhang oder Paperless, Feldprüfung, Entscheidung.
  { method: "GET", pattern: /^receipts\/drafts$/ },
  { method: "POST", pattern: /^receipts\/drafts$/ },
  { method: "POST", pattern: /^receipts\/drafts\/paperless$/ },
  { method: "GET", pattern: new RegExp(`^receipts/drafts/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^receipts/drafts/${ID}/(confirm|reject)$`) },
  // Upload only (multipart); document reads stay outside the allowlist.
  { method: "POST", pattern: /^documents$/ },
];

/** Paths whose POST body is forwarded as multipart/form-data instead of JSON. */
const MULTIPART = new RegExp(
  `^(documents|letting/flow-import/preview|handover/protocols/${ID}/documents|imports/immoware24/lists/(objektdaten|kontakte)|letting/listings/${ID}/images)$`,
);
/** Upper bound for proxied uploads; the API enforces its own document_max_bytes. */
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context): Promise<Response> {
  const method = request.method.toUpperCase();
  const path = (await context.params).path.join("/");
  if (!ALLOWED.some((rule) => rule.method === method && rule.pattern.test(path))) {
    return problemJson(404, "Nicht gefunden");
  }
  if (method !== "GET") {
    const rejected = rejectForeignOrigin(request);
    if (rejected) return rejected;
  }
  const headers = new Headers({ accept: "application/json" });
  const ifMatch = request.headers.get("if-match");
  if (ifMatch) headers.set("if-match", ifMatch);
  let body: string | ArrayBuffer | undefined;
  if (method === "POST" && MULTIPART.test(path)) {
    const type = request.headers.get("content-type") ?? "";
    if (!type.toLowerCase().startsWith("multipart/form-data")) {
      return problemJson(415, "Nicht unterstützter Inhaltstyp");
    }
    const length = Number(request.headers.get("content-length") ?? "0");
    if (length > MAX_UPLOAD_BYTES) return problemJson(413, "Datei zu groß");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_UPLOAD_BYTES) return problemJson(413, "Datei zu groß");
    // The boundary parameter must be kept, so the original header is forwarded unchanged.
    headers.set("content-type", type);
  } else if (method === "POST" || method === "PUT" || method === "PATCH") {
    body = await request.text();
    headers.set("content-type", "application/json");
  }
  const search = new URL(request.url).search;
  let upstream: Response;
  try {
    upstream = await serverFetch(`/api/v1/${path}${search}`, { method, headers, body });
  } catch {
    return problemJson(
      502,
      "Schnittstelle nicht erreichbar",
      "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
    );
  }
  const out = new Headers({ "cache-control": "no-store" });
  for (const name of ["content-type", "etag", "content-disposition"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  const payload = upstream.status === 204 ? null : await upstream.arrayBuffer();
  return new Response(payload, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
