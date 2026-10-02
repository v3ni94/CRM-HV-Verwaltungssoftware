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
  { method: "GET", pattern: /^mail\/messages\/count$/ },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/thread$`) },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/compact$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/compact/summary$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/reply-ai$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/reply-ai/approve$`) },
  // Zuordnungsprüfung mit Rückfrage (Betreiber 27.09.2026): Kontakt, Objekt, Einheit je Mail und Ticket.
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/assignment-review$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/assignment-review/decide$`) },
  { method: "GET", pattern: /^mail\/assignment-reviews\/open$/ },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/assignment-review$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/assignment-review/decide$`) },
  { method: "GET", pattern: /^tickets\/assignment-reviews\/open$/ },
  { method: "PATCH", pattern: new RegExp(`^mail/messages/${ID}$`) },
  { method: "POST", pattern: /^mail\/messages\/bulk$/ },
  { method: "PATCH", pattern: new RegExp(`^mail/messages/${ID}/draft$`) },
  // Anhänge am Antwortentwurf (operator 27.09.2026): Liste, DMS-Verweis, Upload, Entfernen, Suche.
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/attachments$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/attachments$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/attachments/upload$`) },
  { method: "DELETE", pattern: new RegExp(`^mail/messages/${ID}/attachments/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/attachment-candidates$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/(reply-draft|submit|approve|reject|ticket|forward-invoice)$`) },
  // Rechnung aus E-Mail-Anhang erfassen (M14 KI-Extraktion).
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/attachments/${ID}/invoice-extraction$`) },
  { method: "GET", pattern: /^mail\/invoice-forwarding$/ },
  { method: "PUT", pattern: /^mail\/invoice-forwarding$/ },
  { method: "GET", pattern: /^mail\/call-assistant$/ },
  { method: "PUT", pattern: /^mail\/call-assistant$/ },
  // KI-Vorschläge und Playbooks (M20 Übernahme aus dem Immoware Hub).
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/suggest$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/apply-playbook$`) },
  // Prozessflows (Regel M19-11): Vorgangsart aus der Mail übernehmen, Katalog, Flow auf Ticket.
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/apply-process$`) },
  { method: "GET", pattern: /^tickets\/process-catalogue$/ },
  { method: "POST", pattern: /^tickets\/process-catalogue\/seed$/ },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/apply-process$`) },
  // Postausgang und Postdienst (M23-01): Aufträge, manuelle Erfassung, Statusabruf, Einstellungen.
  { method: "GET", pattern: /^postal\/(jobs|jobs\/summary|settings)$/ },
  { method: "GET", pattern: new RegExp(`^postal/jobs/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^postal/dispatches/${ID}/history$`) },
  { method: "POST", pattern: /^postal\/jobs$/ },
  { method: "POST", pattern: new RegExp(`^postal/jobs/${ID}/(manual|refresh|cancel)$`) },
  { method: "PUT", pattern: /^postal\/settings$/ },
  { method: "POST", pattern: /^postal\/settings\/test$/ },
  { method: "GET", pattern: /^mail\/playbooks$/ },
  { method: "POST", pattern: /^mail\/playbooks$/ },
  { method: "PATCH", pattern: new RegExp(`^mail/playbooks/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^mail/playbooks/${ID}$`) },
  { method: "GET", pattern: /^workspace\/(search|notifications|notification-preferences|calendar|filters|dashboard\/stats|ticket-analytics)$/ },
  { method: "POST", pattern: /^workspace\/(notifications\/read|notifications\/mute|calendar|calendar\/refresh|bulk)$/ },
  { method: "PUT", pattern: /^workspace\/filters$/ },
  { method: "PUT", pattern: /^workspace\/notification-preferences$/ },
  // Tagesübersicht, Fristenliste und Schalter der Tagesjobs (A40, A41).
  { method: "GET", pattern: /^workspace\/(digest|deadlines|job-settings)$/ },
  { method: "PUT", pattern: /^workspace\/job-settings$/ },
  // Deadline types, entries, notice period and property checklists (rule WS-01).
  { method: "GET", pattern: /^workspace\/(deadline-types|deadline-entries|deadline-entries\/compute|assignable-users|notice-period|checklists|checklists\/templates)$/ },
  { method: "POST", pattern: /^workspace\/(deadline-types|deadline-entries|checklists)$/ },
  { method: "PATCH", pattern: new RegExp(`^workspace/deadline-types/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^workspace/deadline-entries/${ID}/done$`) },
  { method: "POST", pattern: new RegExp(`^workspace/checklists/${ID}/items/[a-z0-9_]+$`) },
  // Dienstleisterverträge (M9-06): Liste, Anlegen, Ändern, Löschen (contracts:*).
  { method: "GET", pattern: /^service-contracts$/ },
  { method: "POST", pattern: /^service-contracts$/ },
  { method: "GET", pattern: new RegExp(`^service-contracts/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^service-contracts/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^service-contracts/${ID}$`) },
  // Vertragsformular (A88): Anlage, neue Version, Beendigung, Zahlungsplan, Kaution, Mandatsverweis.
  { method: "POST", pattern: /^contracts$/ },
  // Vertragsauswahl (Package F): Verträge je Einheit für Übergabeprotokoll und Dokumentupload (contracts:read).
  { method: "GET", pattern: /^contracts$/ },
  // Freigabe der Importverträge vor der Sollstellung (Betreiberauftrag 26.09.2026).
  { method: "GET", pattern: /^contracts\/pending-approval$/ },
  { method: "POST", pattern: /^contracts\/approve$/ },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/reject-import$`) },
  { method: "GET", pattern: new RegExp(`^contracts/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/(versions|termination|schedules|deposits)$`) },
  // Eigentümerwechsel in der Oberfläche (operator 28.09.2026): Vorschau und Erfassung.
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/ownership-transfer/preview$`) },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/ownership-transfer$`) },
  // Sollbeträge (Miete, Vorauszahlungen, Hausgeld, ...) im CRM erfassen (Paket D, 28.09.2026):
  // Historie über alle Versionen und neuer Betrag ab Datum (schließt den offenen Vorbetrag).
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/payments$`) },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/payments$`) },
  // Vertragsbezogene Umlagewerte (P1, 4.5 Eigenschaften).
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/allocation-values$`) },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/allocation-values$`) },
  // Kautionen und Kautionsabrechnung (M5-02): Liste, Entwurf berechnen und speichern,
  // Referenzzinssatz je Jahr (Einstellungen). Freigabe bleibt hinter G3 und ist hier nicht erreichbar.
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/deposits$`) },
  { method: "GET", pattern: new RegExp(`^deposits/${ID}/settlements$`) },
  { method: "POST", pattern: new RegExp(`^deposits/${ID}/settlements(/preview)?$`) },
  // Kautionsabrechnung als PDF-Entwurf ablegen (offener Restpunkt M5-02, PDF-Ausgabe).
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/deposit-settlements/${ID}/document$`) },
  // PDF-Vorschau der Kautionsabrechnung (GAG-29): nicht abgelegt, kein Versand, keine Buchung.
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/deposit-settlements/${ID}/document-preview$`) },
  // Mietrechnung mit Umsatzsteuerausweis (M13-03 Folgepunkt, Regel M13-04): Liste, Erzeugen,
  // PDF (Entwurf mit Wasserzeichen hinter G1), Storno nur durch Gutschrift.
  { method: "GET", pattern: /^accounting\/rent-invoices\/numbering-mode$/ },
  { method: "PUT", pattern: /^accounting\/rent-invoices\/numbering-mode$/ },
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/rent-invoices$`) },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/rent-invoices$`) },
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/rent-invoices/${ID}/pdf$`) },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/rent-invoices/${ID}/credit-note$`) },
  { method: "GET", pattern: /^deposit-interest-rates$/ },
  { method: "PUT", pattern: /^deposit-interest-rates\/[0-9]{4}$/ },
  { method: "DELETE", pattern: /^deposit-interest-rates\/[0-9]{4}$/ },
  // B15: Zinssatzverlauf je Kautionskonto, Entwürfe der jährlichen Zinsgutschrift.
  { method: "GET", pattern: new RegExp(`^deposits/${ID}/interest-(rates|drafts)$`) },
  { method: "PUT", pattern: new RegExp(`^deposits/${ID}/interest-rates/[0-9]{4}-[0-9]{2}-[0-9]{2}$`) },
  { method: "DELETE", pattern: new RegExp(`^deposits/${ID}/interest-rates/[0-9]{4}-[0-9]{2}-[0-9]{2}$`) },
  { method: "POST", pattern: new RegExp(`^deposits/${ID}/interest-drafts$`) },
  { method: "POST", pattern: new RegExp(`^deposit-interest-drafts/${ID}/(confirm|discard)$`) },
  // AF05 (GAF-27): deposit movements (no posting without G1) and the yearly interest draft run.
  { method: "POST", pattern: new RegExp(`^deposits/${ID}/movements$`) },
  { method: "POST", pattern: /^deposit-interest-drafts\/run$/ },
  { method: "GET", pattern: /^sepa-mandates$/ },
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
  // Inline-Bearbeitung der Stammdaten (AP8, ADR 0012): Teilupdate je Feld mit If-Match.
  { method: "PATCH", pattern: new RegExp(`^contacts/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^properties/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^buildings/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^units/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^contracts/${ID}/notes$`) },
  // Paket P16 (Welle 2): Parteien, Notizen, Tags, Bankkonten, Dienstleister, Vertragskorrekturen, Kaution.
  { method: "PATCH", pattern: new RegExp(`^parties/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^parties/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^contacts/${ID}/notes/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^contacts/${ID}/notes/${ID}$`) },
  { method: "GET", pattern: /^contact-tags$/ },
  { method: "PATCH", pattern: new RegExp(`^contact-tags/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^contact-tags/${ID}$`) },
  { method: "GET", pattern: /^contact-merges$/ },
  { method: "POST", pattern: /^contact-merges$/ },
  { method: "GET", pattern: new RegExp(`^contact-merges/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^contact-merges/${ID}/(reject|execute)$`) },
  { method: "POST", pattern: new RegExp(`^contact-tags/${ID}/merge$`) },
  { method: "PATCH", pattern: new RegExp(`^properties/${ID}/(bank-accounts|service-providers)/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/billing-periods/${ID}/status$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/takeover-checklist$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/takeover-checklist$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/takeover-checklist/tickets$`) },
  { method: "PATCH", pattern: new RegExp(`^properties/${ID}/takeover-checklist/[a-z_]+$`) },
  { method: "POST", pattern: /^onboarding\/person-match$/ },
  { method: "POST", pattern: /^onboarding\/person-match-batch$/ },
  { method: "GET", pattern: /^onboarding\/match-settings$/ },
  { method: "PUT", pattern: /^onboarding\/match-settings$/ },
  { method: "GET", pattern: /^onboarding\/takeover-ticket-defaults$/ },
  { method: "PUT", pattern: /^onboarding\/takeover-ticket-defaults$/ },
  { method: "GET", pattern: new RegExp(`^units/${ID}/vat-options$`) },
  // Paket Q05 (Welle 3): CRM-Oberflächen für Parteien, USt-Optionshistorie, Belegungsliste,
  // Gebäudeauswahl am Ticket und Teamverwaltung (Endpunkte bestehen, nur die Freigabe fehlte).
  { method: "GET", pattern: /^parties$/ },
  { method: "POST", pattern: /^parties$/ },
  { method: "GET", pattern: new RegExp(`^parties/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^units/${ID}/vat-options$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/(buildings|occupancy)$`) },
  { method: "POST", pattern: /^teams$/ },
  { method: "PATCH", pattern: new RegExp(`^teams/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^teams/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^contracts/${ID}/(custom-fields|payments/${ID}|schedules/${ID})$`) },
  { method: "PATCH", pattern: new RegExp(`^deposits/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^contacts/${ID}$`) },
  {
    method: "GET",
    pattern: new RegExp(`^contacts/${ID}/(export|notes|consents|duplicates|sepa-mandates)$`),
  },
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/(notes|consents)$`) },
  // AE34 (GAE-27): Widerspruch erfassen.
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/objections$`) },
  // AC07 (GA08-06): Auskunftsexport mit Prüfschritt.
  { method: "GET", pattern: new RegExp(`^contacts/${ID}/access-exports(/${ID}/(preview|download))?$`) },
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/access-exports(/${ID}/(review|approve|reject))?$`) },
  // AC07 (GA08-08): Löschcheckliste und Nachlauf.
  { method: "GET", pattern: new RegExp(`^documents/deletions/${ID}/checklist$`) },
  { method: "POST", pattern: new RegExp(`^documents/deletions/${ID}/follow-up$`) },
  // AE33 (AC07-03): Papierkorb; (AC07-01): Umfang der Auskunft als Mandantenschalter.
  { method: "GET", pattern: /^documents\/(trash|trash-settings)$/ },
  { method: "PUT", pattern: /^documents\/trash-settings$/ },
  { method: "POST", pattern: new RegExp(`^documents/trash/${ID}/(restore|purge)$`) },
  { method: "GET", pattern: /^contact-access-export-settings$/ },
  { method: "PUT", pattern: /^contact-access-export-settings$/ },
  { method: "GET", pattern: new RegExp(`^contacts/${ID}/relations$`) },
  { method: "POST", pattern: /^contacts\/roles\/recompute$/ },
  { method: "POST", pattern: new RegExp(`^consents/${ID}/revoke$`) },
  { method: "GET", pattern: /^consent-policy$/ },
  { method: "PUT", pattern: /^consent-policy$/ },
  // AE34 (AC06-01): legal basis per processing purpose, shown and changed on "Fachliche Regeln" (AE39).
  { method: "PUT", pattern: /^consent-legal-basis\/(email_delivery|data_sharing|marketing|portal_terms)$/ },
  { method: "DELETE", pattern: /^consent-legal-basis\/(email_delivery|data_sharing|marketing|portal_terms)$/ },
  {
    method: "POST",
    pattern: new RegExp(`^contacts/${ID}/bank-accounts/${ID}/mandate/revoke$`),
  },
  // Four eyes release of contact IBANs (M5-01).
  {
    method: "POST",
    pattern: new RegExp(`^contacts/${ID}/bank-accounts/${ID}/(approve|reject)$`),
  },
  // Bankverbindungen am Kontakt (M5-01 addendum 28.09.2026): add, change as new version,
  // end, and the four eyes decision on a pending change.
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/bank-accounts$`) },
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/bank-accounts/${ID}/(replace|end)$`) },
  {
    method: "POST",
    pattern: new RegExp(`^contacts/${ID}/bank-accounts/${ID}/changes/${ID}/(approve|reject)$`),
  },
  // AI assistant (M7): conversations, runs, proposals, import runs, provider settings.
  { method: "GET", pattern: /^ai\/conversations$/ },
  // Tenant members, roles and settings (settings area).
  { method: "GET", pattern: /^tenant\/members$/ },
  { method: "POST", pattern: /^tenant\/members$/ },
  // Ereignisprotokoll je Datensatz mit CSV-Export (P1 AP6).
  { method: "GET", pattern: /^tenant\/audit-log(\/export)?$/ },
  // Vollständiger Mandantenexport als Job (M2-01), nur Mandantenadministrator.
  { method: "GET", pattern: /^tenant\/export-jobs$/ },
  { method: "POST", pattern: /^tenant\/export-jobs$/ },
  { method: "GET", pattern: new RegExp(`^tenant/export-jobs/${ID}/download$`) },
  { method: "PATCH", pattern: new RegExp(`^tenant/members/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^tenant/members/${ID}/reset-password$`) },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/roles$`) },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/competences$`) },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/mobile-phone$`) },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/reply-approval$`) },
  // A37: Zugriffsbereich je Rechtsträger (Steuerberater).
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/legal-entities$`) },
  // M2-02: Objektzuordnung je Mitglied.
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/properties$`) },
  { method: "GET", pattern: /^tenant\/legal-entities$/ },
  { method: "GET", pattern: /^tenant\/competence-catalogue$/ },
  { method: "GET", pattern: /^tenant\/roles$/ },
  { method: "POST", pattern: /^tenant\/roles$/ },
  { method: "PUT", pattern: new RegExp(`^tenant/roles/${ID}/permissions$`) },
  // Portalrechte je Rolle (M2-08 entschieden, docs/rules/M2-07.md).
  // Portalzugang einladen von der Kontaktakte aus (M21, Lückenliste A86).
  { method: "GET", pattern: /^portal-admin\/accounts$/ },
  { method: "POST", pattern: /^portal-admin\/accounts$/ },
  // GA11-04 (AB12): Verfügbarkeitsfenster und Klassenfreigaben der Dienstleister.
  { method: "GET", pattern: /^portal-admin\/legal-entities$/ },
  { method: "GET", pattern: /^portal-admin\/provider-availability$/ },
  { method: "POST", pattern: /^portal-admin\/provider-availability$/ },
  { method: "DELETE", pattern: new RegExp(`^portal-admin/provider-availability/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^portal-admin/accounts/${ID}/document-class-grants$`) },
  { method: "POST", pattern: new RegExp(`^portal-admin/accounts/${ID}/document-class-grants$`) },
  // P13: Portalfunktionen und Statistik (M21-08, SA-01), Vollmachten (M21-05), Support-Sicht mit
  // Einwilligung (SA-02), Antwort im Chat zur Meldung (M21-01).
  { method: "GET", pattern: /^portal-admin\/(features|statistics|representations)$/ },
  { method: "PATCH", pattern: /^portal-admin\/features$/ },
  // AE28 (M7-06): Protokoll des Portal-Assistenten (Recht Mandanteneinstellungen).
  { method: "GET", pattern: /^portal-admin\/assistant\/log$/ },
  { method: "POST", pattern: /^portal-admin\/representations$/ },
  { method: "POST", pattern: new RegExp(`^portal-admin/representations/${ID}/revoke$`) },
  { method: "GET", pattern: new RegExp(`^portal-admin/accounts/${ID}/(support-view|support-log)$`) },
  { method: "POST", pattern: new RegExp(`^portal-admin/tickets/${ID}/messages$`) },
  // Magic-Link-Anmeldung (M21-01): zweiter Faktor per E-Mail-Code an/aus, Einladungsbrief als
  // PDF mit QR-Code (Einladung als Anschreiben, 90 Tage gültiger Code).
  { method: "PATCH", pattern: new RegExp(`^portal-admin/accounts/${ID}/security$`) },
  { method: "POST", pattern: new RegExp(`^portal-admin/accounts/${ID}/sync-grants$`) },
  { method: "POST", pattern: new RegExp(`^portal-admin/accounts/${ID}/invitation-letter$`) },
  // Vorschläge aus dem Portal (M21-02 Adressänderung, M3-02 Portalstufe SEPA-Mandat): Liste je
  // Kontakt und Entscheidung; das Annehmen eines Mandats legt nur eine Bankverbindung mit
  // Nachweis an, nie ein aktives Einzugsmandat (G2).
  { method: "GET", pattern: /^portal-admin\/change-requests$/ },
  { method: "POST", pattern: new RegExp(`^portal-admin/change-requests/${ID}/decide$`) },
  { method: "GET", pattern: /^portal-admin\/sepa-mandate-proposals$/ },
  { method: "POST", pattern: new RegExp(`^portal-admin/sepa-mandate-proposals/${ID}/decide$`) },
  // Freigabeflag je Dokument (M21-03): Sichtbarkeit intern, Eigentümer, Mieter, Dienstleister, Beirat.
  { method: "PATCH", pattern: new RegExp(`^documents/${ID}$`) },
  // Aufbewahrungs- und Sperrstatus je Dokument (U11-01): Lesen, Anzeige im Dokumentdetail.
  { method: "GET", pattern: new RegExp(`^documents/${ID}/retention-status$`) },
  // Löschungssperre setzen und aufheben (GAG-26, 7.11 S05); Aufheben mit zweiter Person (API).
  { method: "POST", pattern: new RegExp(`^documents/${ID}/hold$`) },
  { method: "DELETE", pattern: new RegExp(`^documents/${ID}/hold$`) },
  // Dokumentauswahl (V05) und Beschlussauswahl für die Startregel Beschluss (V03): nur Lesen.
  { method: "GET", pattern: /^documents$/ },
  { method: "GET", pattern: /^hoa\/resolutions$/ },
  // Datenschutz (P17, Abschnitt 16): Register, Löschprofile, Löschanträge, Verzeichnis-Entwurf.
  { method: "GET", pattern: /^privacy\/(register|processing-records|deletion-profiles|erasure-requests)$/ },
  { method: "POST", pattern: /^privacy\/(register|erasure-requests)$/ },
  { method: "PUT", pattern: new RegExp(`^privacy/register/${ID}$`) },
  { method: "PUT", pattern: /^privacy\/deletion-profiles$/ },
  { method: "POST", pattern: new RegExp(`^privacy/deletion-profiles/${ID}/release$`) },
  { method: "POST", pattern: new RegExp(`^privacy/erasure-requests/${ID}/(approve|reject|execute)$`) },
  // AE32 (S711-10): Dienstleister laut Konfiguration, Übernahme ins Register, PDF-Entwurf.
  { method: "GET", pattern: /^privacy\/(register\/config-sources|processing-records\/pdf)$/ },
  { method: "POST", pattern: /^privacy\/register\/config-sources\/sync$/ },
  // Portalformulare (A56): Vorlagen je Mandant.
  { method: "GET", pattern: /^portal-admin\/forms$/ },
  { method: "POST", pattern: /^portal-admin\/forms$/ },
  // AE30 (AA14-01): Elementtypen mit Prüfregel und Vorschau im Trockenlauf; AA14-02: Bewertungen.
  { method: "GET", pattern: /^portal-admin\/forms\/element-types$/ },
  { method: "POST", pattern: /^portal-admin\/forms\/preview$/ },
  { method: "GET", pattern: /^portal-admin\/provider-ratings$/ },
  { method: "PATCH", pattern: new RegExp(`^portal-admin/forms/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^portal-admin/forms/${ID}$`) },
  { method: "GET", pattern: /^tenant\/portal-role-permissions$/ },
  { method: "PUT", pattern: /^tenant\/portal-role-permissions$/ },
  { method: "POST", pattern: /^tenant\/portal-role-permissions\/resync$/ },
  // Ausgehende Webhook-Abonnements (Abschnitt 12, A69): Katalog, Liste, Anlegen, Ändern,
  // Löschen, Zustellprotokoll und manuelle Neuzustellung (Rechte webhooks:*).
  { method: "GET", pattern: /^tenant\/webhooks$/ },
  { method: "GET", pattern: /^tenant\/webhooks\/event-types$/ },
  { method: "POST", pattern: /^tenant\/webhooks$/ },
  { method: "PATCH", pattern: new RegExp(`^tenant/webhooks/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^tenant/webhooks/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^tenant/webhooks/${ID}/deliveries$`) },
  // GAE-30, GAF-20, GAF-21: API-Schlüssel (nur Präfix, Widerruf), Branding, Mailquellen mit Geheimnisrotation.
  { method: "GET", pattern: /^tenant\/(api-keys|branding)$/ },
  { method: "POST", pattern: /^tenant\/api-keys$/ },
  { method: "DELETE", pattern: new RegExp(`^tenant/api-keys/${ID}$`) },
  { method: "GET", pattern: /^mail\/inbound\/sources$/ },
  { method: "POST", pattern: /^mail\/inbound\/sources$/ },
  { method: "PATCH", pattern: new RegExp(`^mail/inbound/sources/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^mail/inbound/sources/${ID}/rotate-secret$`) },
  { method: "GET", pattern: new RegExp(`^mail/inbound/sources/${ID}/events$`) },
  { method: "POST", pattern: new RegExp(`^tenant/webhook-deliveries/${ID}/redeliver$`) },
  { method: "GET", pattern: /^tenant\/settings$/ },
  { method: "PATCH", pattern: /^tenant\/settings$/ },
  // AG03 (GAF-11): platform wide switches (platform administrators only, checked by the API).
  { method: "GET", pattern: /^platform\/settings$/ },
  { method: "PATCH", pattern: /^platform\/settings$/ },
  // Rechnungsstellung und Steuer (M13-04/M18-01, operator decision 25.09.2026).
  { method: "GET", pattern: /^tenant\/billing-settings$/ },
  { method: "PATCH", pattern: /^tenant\/billing-settings$/ },
  // Own account: password change and session list (Meine Daten).
  { method: "POST", pattern: /^auth\/password$/ },
  { method: "GET", pattern: /^auth\/sessions$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/sessions/${ID}$`) },
  { method: "GET", pattern: /^auth\/trusted-devices$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/trusted-devices/${ID}$`) },
  // M2-03: Passkeys (WebAuthn) vorbereitet; Registrierung antwortet bis zur Freigabe 503.
  { method: "GET", pattern: /^auth\/webauthn\/(status|credentials)$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/webauthn/credentials/${ID}$`) },
  // S16-01: Passkey registrieren (Optionen und Prüfung); die Anmeldung läuft über /api/session/webauthn.
  { method: "POST", pattern: /^auth\/webauthn\/register\/(options|verify)$/ },
  // Own UI preferences (theme, expanded navigation groups): PATCH /auth/me/preferences.
  { method: "PATCH", pattern: /^auth\/me\/preferences$/ },
  // Optional second factor (operator 26.09.2026, M2-01): confirm and disable; the setup with
  // its QR code runs through /api/session/totp/setup.
  { method: "POST", pattern: /^auth\/totp\/(confirm|disable)$/ },
  // M2-04: Richtlinie zweiter Faktor je Rolle (Einstellungen, Rollen und Rechte).
  { method: "GET", pattern: /^auth\/mfa-policy$/ },
  { method: "PUT", pattern: /^auth\/mfa-policy$/ },
  // Platform: tenant and tenant administrator creation (platform admins only, checked by the API).
  { method: "POST", pattern: /^platform\/tenants$/ },
  { method: "POST", pattern: /^platform\/users$/ },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/members$`) },
  { method: "POST", pattern: /^ai\/conversations$/ },
  { method: "GET", pattern: new RegExp(`^ai/conversations/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^ai/conversations/${ID}/messages$`) },
  { method: "GET", pattern: new RegExp(`^ai/runs/${ID}$`) },
  { method: "GET", pattern: /^ai\/examples$/ },
  { method: "GET", pattern: new RegExp(`^ai/proposals/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^ai/proposals/${ID}/(apply|reject)$`) },
  { method: "GET", pattern: /^ai\/usage$/ },
  { method: "GET", pattern: /^ai\/providers$/ },
  { method: "PUT", pattern: /^ai\/routing$/ },
  { method: "PUT", pattern: /^ai\/invoice-intake-auto$/ },
  { method: "GET", pattern: /^ai\/automation$/ },
  { method: "PUT", pattern: /^ai\/automation$/ },
  { method: "GET", pattern: /^ai\/automation$/ },
  { method: "PUT", pattern: /^ai\/automation$/ },
  { method: "PUT", pattern: /^ai\/providers\/(anthropic|openai)$/ },
  { method: "POST", pattern: /^ai\/providers\/(anthropic|openai)\/release$/ },
  // Verbindungstest je Stufe (Einstellungen, KI-Anbieter); erteilt keine Freigabe.
  { method: "POST", pattern: /^ai\/providers\/(anthropic|openai)\/test$/ },
  // Wissensbasis je Mandant und Objekt (Welle 3 Punkt 14, M34).
  { method: "GET", pattern: /^ai\/knowledge$/ },
  { method: "POST", pattern: /^ai\/knowledge$/ },
  { method: "PUT", pattern: new RegExp(`^ai/knowledge/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^ai/knowledge/${ID}$`) },
  // M34-01 Freigabeworkflow: Status, Vier-Augen-Freigabe und Versionsverlauf.
  { method: "GET", pattern: new RegExp(`^ai/knowledge/${ID}/versions$`) },
  { method: "POST", pattern: new RegExp(`^ai/knowledge/${ID}/(submit|approve|withdraw)$`) },
  // Mail-Vorbereitung (M34).
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/preparation$`) },
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/preparation$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/preparation/correct$`) },
  { method: "GET", pattern: /^imports$/ },
  { method: "GET", pattern: new RegExp(`^imports/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^imports/${ID}/undo-preview$`) },
  { method: "POST", pattern: new RegExp(`^imports/${ID}/undo$`) },
  { method: "POST", pattern: new RegExp(`^ai/import-runs/${ID}/apply-role$`) },
  { method: "POST", pattern: new RegExp(`^ai/import-runs/${ID}/resolve-entities$`) },
  // Immoware24 import assistant (M8, 13.1).
  { method: "GET", pattern: /^imports\/immoware24\/(fields|mappings|overview)$/ },
  { method: "POST", pattern: /^imports\/immoware24\/(mappings|files)$/ },
  { method: "GET", pattern: new RegExp(`^imports/immoware24/files/${ID}(/rows|/reconciliation)?$`) },
  { method: "POST", pattern: new RegExp(`^imports/immoware24/files/${ID}/(validate|test-run|apply)$`) },
  // AE37 (Q08-01): header heuristic, validation report, stored column assignments, export status.
  { method: "POST", pattern: /^imports\/immoware24\/header-detection$/ },
  { method: "GET", pattern: new RegExp(`^imports/immoware24/files/${ID}/column-proposal$`) },
  { method: "POST", pattern: new RegExp(`^imports/immoware24/files/${ID}/check$`) },
  { method: "GET", pattern: /^imports\/immoware24\/(column-assignments|export-requirements)$/ },
  { method: "PUT", pattern: /^imports\/immoware24\/column-assignments$/ },
  { method: "DELETE", pattern: new RegExp(`^imports/immoware24/column-assignments/${ID}$`) },
  // Immoware24-Listen (Objektdaten, Kontakte) als CSV-Upload, Testlauf oder Übernahme.
  { method: "POST", pattern: /^imports\/immoware24\/lists\/(objektdaten|kontakte|zuordnung|adressen|adressen-ableiten)$/ },
  { method: "POST", pattern: /^imports\/immoware24\/lists\/zuordnung\/manuell$/ },
  // Abgleichberichte des Parallelbetriebs (A68): Liste, Erstellen, JSON, CSV, Spaltenzuordnung.
  { method: "GET", pattern: /^imports\/reconciliation-reports(\/columns)?$/ },
  // Vollimport mit Stichtag (M8-01, M8-02, V9): Vorprüfung, Trockenlauf, Übernahme, Abgleichbericht.
  { method: "GET", pattern: /^imports\/immoware24\/vollimport(\/exporttypen)?$/ },
  { method: "GET", pattern: /^imports\/immoware24\/history\/(tickets|open-items|open-items\/summary|bank-links)$/ },
  { method: "GET", pattern: /^imports\/immoware24\/history\/open-items\/balance-check$/ },
  { method: "GET", pattern: new RegExp(`^imports/immoware24/history/bank-links/${ID}/candidates$`) },
  { method: "POST", pattern: /^imports\/immoware24\/vollimport(\/vorpruefung)?$/ },
  { method: "GET", pattern: new RegExp(`^imports/immoware24/vollimport/${ID}(/pdf)?$`) },
  // Migration von Immoware24 ohne Parallelbetrieb (6.9.10, M8-03): Status, Journal, Salden,
  // Abgleich, Wechsel des führenden Systems (Freigaben bleiben in der API).
  { method: "GET", pattern: /^imports\/migration\/(status|journal-columns|switch-requests)$/ },
  { method: "PUT", pattern: /^imports\/migration\/journal-columns$/ },
  { method: "GET", pattern: new RegExp(`^imports/migration/ledgers/${ID}(/journal|/opening-balances|/year-expenses)?$`) },
  { method: "PUT", pattern: new RegExp(`^imports/migration/ledgers/${ID}/(cutoff|opening-balances)$`) },
  { method: "POST", pattern: new RegExp(`^imports/migration/ledgers/${ID}/(journal|switch-requests|opening-balances/import)$`) },
  { method: "GET", pattern: new RegExp(`^imports/migration/opening-balances/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^imports/migration/opening-balances/${ID}/(release|post)$`) },
  { method: "GET", pattern: new RegExp(`^imports/migration/properties/${ID}/reconciliation$`) },
  { method: "POST", pattern: new RegExp(`^imports/migration/properties/${ID}/reconciliation$`) },
  { method: "GET", pattern: new RegExp(`^imports/migration/reconciliation/${ID}(/pdf)?$`) },
  { method: "GET", pattern: new RegExp(`^imports/migration/properties/${ID}/acceptance$`) },
  { method: "POST", pattern: new RegExp(`^imports/migration/properties/${ID}/acceptance$`) },
  { method: "PUT", pattern: new RegExp(`^imports/migration/acceptance/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^imports/migration/acceptance/${ID}/sign$`) },
  { method: "POST", pattern: new RegExp(`^imports/migration/switch-requests/${ID}/(approve|reject)$`) },
  { method: "POST", pattern: /^imports\/reconciliation-reports$/ },
  { method: "PUT", pattern: /^imports\/reconciliation-reports\/columns$/ },
  { method: "GET", pattern: new RegExp(`^imports/reconciliation-reports/${ID}(/csv)?$`) },
  // Evaluations (M18, 7.5): liquidity, payments by debtor, revenue; read only.
  // Zugang der Zahlungsaufforderung an der Offene-Posten-Ansicht erfassen (M16-03, Restpunkt 27.09.2026).
  { method: "PATCH", pattern: new RegExp(`^accounting/open-items/${ID}/notice-received$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/liquidity$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/payments-by-debtor$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/payment-type-accounts$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/revenue$`) },
  { method: "GET", pattern: /^accounting\/rule-versions\/due-checkpoints$/ },
  { method: "GET", pattern: /^accounting\/rule-versions\/checkpoints$/ },
  { method: "POST", pattern: /^accounting\/rule-versions\/checkpoints$/ },
  { method: "PATCH", pattern: new RegExp(`^accounting/rule-versions/checkpoints/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/rule-versions/${ID}/withdraw$`) },
  { method: "POST", pattern: new RegExp(`^accounting/rule-versions/${ID}/confirm$`) },
  // Weitere Auswertungen mit Kopfangaben, Excel und Verfahrensdokumentation (M18-01 bis M18-09).
  {
    method: "GET",
    pattern: new RegExp(
      `^accounting/ledgers/${ID}/reports/(monthly-matrix|target-actual|bank-statement|vat-overview|vat-overview-by-property|income-expense|revenue|payments-by-debtor|trial-balance|open-items|account-sheet|xlsx|line-property-drift)$`,
    ),
  },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/procedure-documentation$`) },
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
  // M13-08: earlier runs per month; M13-03 to M13-06: Verwalterhonorar settings, due periods,
  // issued invoices (release, credit note) and the XRechnung download, check and filing.
  { method: "GET", pattern: /^accounting\/receivable-runs$/ },
  { method: "GET", pattern: /^accounting\/admin-fees$/ },
  { method: "POST", pattern: /^accounting\/admin-fees$/ },
  { method: "GET", pattern: /^accounting\/admin-fees-periods$/ },
  { method: "GET", pattern: new RegExp(`^accounting/admin-fees/${ID}(/invoice-preview)?$`) },
  { method: "PATCH", pattern: new RegExp(`^accounting/admin-fees/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^accounting/admin-fees/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/admin-fees/${ID}/invoice-issue$`) },
  { method: "GET", pattern: /^accounting\/admin-fee-invoices$/ },
  { method: "GET", pattern: new RegExp(`^accounting/admin-fee-invoices/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/admin-fee-invoices/${ID}/(release|cancel|posting-drafts)$`) },
  { method: "GET", pattern: /^accounting\/admin-fee-posting-config$/ },
  { method: "PUT", pattern: /^accounting\/admin-fee-posting-config$/ },
  { method: "POST", pattern: new RegExp(`^accounting/admin-fee-invoices/${ID}/(document|xrechnung-credit-note/document)$`) },
  { method: "POST", pattern: /^accounting\/admin-fees-run$/ },
  { method: "GET", pattern: new RegExp(`^accounting/invoices/${ID}/xrechnung(\\.xml|/check)$`) },
  { method: "POST", pattern: new RegExp(`^accounting/invoices/${ID}/xrechnung/document$`) },
  // S13-03 (AE25): ZUGFeRD/Factur-X hybrid of fee invoices (download, check, filing; nothing is sent).
  { method: "GET", pattern: new RegExp(`^accounting/admin-fee-invoices/${ID}/zugferd(\\.pdf|/check)$`) },
  { method: "POST", pattern: new RegExp(`^accounting/admin-fee-invoices/${ID}/zugferd/document$`) },
  // Bank (M11, M12): statement import, proposals, confirmed booking, ignore with reason.
  { method: "POST", pattern: /^banking\/imports$/ },
  // Kennzahlen des Bankabgleichs (A45): Abdeckungsgrad und Fehlerquote je Zeitraum, lesend.
  { method: "GET", pattern: /^banking\/matching-metrics$/ },
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/candidates$`) },
  // P09 (Lückenliste 30.09.2026): AI posting display (M12-04), payer IBAN proposal (M12-03),
  // sync hour and manual full sync (M11-05), weekly L3 digest (M12-02).
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/ai-posting$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/ai-posting$`) },
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/payer-iban$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/payer-iban$`) },
  { method: "GET", pattern: /^ai\/posting-enabled$/ },
  { method: "PUT", pattern: /^ai\/posting-enabled$/ },
  { method: "GET", pattern: /^banking\/sync\/settings$/ },
  { method: "PUT", pattern: /^banking\/sync\/settings$/ },
  { method: "POST", pattern: /^banking\/sync\/run$/ },
  { method: "GET", pattern: /^banking\/consent-sync\/settings$/ },
  { method: "PUT", pattern: /^banking\/consent-sync\/settings$/ },
  { method: "GET", pattern: /^banking\/auto-posting\/digests$/ },
  { method: "POST", pattern: /^banking\/auto-posting\/digests\/build$/ },
  { method: "POST", pattern: new RegExp(`^banking/auto-posting/digests/${ID}/confirm$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/(book|ignore)$`) },
  // GAG-25: reopen an ignored transaction with a reason (status back to new, never a posting).
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/reopen$`) },
  // BK-2 (plan M12 step S2): daily bank work in the CRM against the existing API. Transaction
  // list with filters and pagination, duplicate clarification (keep or ignore with reason),
  // "Regel lernen" from a booked transaction, bulk confirmation with preview, MT940 and CSV
  // upload with column mapping, bank reconciliation B09, bank rules with the four eyes life
  // cycle (propose, approve, activate with cap and evidence, disable). The automation runner
  // (`POST /banking/auto-post`) and the switch (`PUT /banking/automation`) stay outside on
  // purpose: activation is gated by an open operator decision (ADR 0014, plan section 4).
  { method: "GET", pattern: /^banking\/transactions$/ },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/(review|learn)$`) },
  { method: "POST", pattern: /^banking\/bulk-confirm$/ },
  { method: "POST", pattern: /^banking\/imports\/csv(\/preview)?$/ },
  { method: "GET", pattern: /^banking\/csv-mappings$/ },
  { method: "POST", pattern: /^banking\/csv-mappings$/ },
  { method: "GET", pattern: new RegExp(`^banking/accounts/${ID}/reconciliation$`) },
  { method: "GET", pattern: /^banking\/rules$/ },
  { method: "POST", pattern: /^banking\/rules$/ },
  { method: "POST", pattern: new RegExp(`^banking/rules/${ID}/(approve|activate|disable)$`) },
  // Automatikstufen, Ein-Klick, Korrigieren, gelernte Regelvorschläge und Nachkontrolle
  // (ADR 0014 Nachtrag S4 bis S6, Regeln M12-05 und M12-06). Der Automatiklauf selbst
  // (`POST /banking/auto-post`) bleibt außerhalb: er läuft nach Import und Sync.
  { method: "GET", pattern: /^banking\/automation\/(levels|metrics)$/ },
  { method: "POST", pattern: /^banking\/automation\/level-requests$/ },
  { method: "POST", pattern: new RegExp(`^banking/automation/level-requests/${ID}/(approve|reject)$`) },
  { method: "PUT", pattern: /^banking\/automation\/(levels|outgoing)$/ },
  // AE03: comparison report (read only) and the four eyes switch request (G1 checked by the API).
  { method: "GET", pattern: /^banking\/automation\/(comparison|switch-requests)$/ },
  { method: "POST", pattern: /^banking\/automation\/switch-requests$/ },
  // AF01 (GAA-01): PUT /banking/automation only switches off (switching on returns 409 and
  // runs through the request above), so the immediate switch off is offered in the CRM.
  { method: "PUT", pattern: /^banking\/automation$/ },
  { method: "POST", pattern: new RegExp(`^banking/automation/switch-requests/${ID}/(approve|reject)$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/(accept|correct)$`) },
  { method: "GET", pattern: /^banking\/rule-proposals$/ },
  { method: "POST", pattern: new RegExp(`^banking/rule-proposals/${ID}/(accept|reject)$`) },
  { method: "GET", pattern: /^banking\/auto-posting\/reviews$/ },
  { method: "POST", pattern: new RegExp(`^banking/auto-posting/reviews/${ID}$`) },
  // Ledger list, chart of accounts and open items for the booking dialog (accounting:read).
  { method: "GET", pattern: /^accounting\/ledgers$/ },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/(accounts|open-items)$`) },
  // Bookkeeping in the CRM (M10-01 to M10-06, gap list 30.09.2026): drafts, posting,
  // reversal with reason, lock, opening balance check, chart of accounts, allocation.
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/entries(/cost-transfer|/interest)?$`) },
  // P01-01 (AE05): tax accounts for withholdings on credit interest and withholdings per entry.
  { method: "GET", pattern: /^accounting\/interest-tax-config$/ },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/interest-tax-config$`) },
  { method: "PUT", pattern: new RegExp(`^accounting/ledgers/${ID}/interest-tax-config$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/entries/${ID}/interest-tax$`) },
  { method: "DELETE", pattern: new RegExp(`^accounting/ledgers/${ID}/entries/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/entries/${ID}/(post|approve|reverse)$`) },
  // GA05-02: versioned notes on posted entries (read accounting:read, write accounting:update).
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/entries/${ID}/notes$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/entries/${ID}/notes$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/(lock|sync-creditors)$`) },
  // AG02 (GAC-05): leading system per process kind (read, request, decision by a second person).
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/leading-switches$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/leading-switches$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/leading-switches/${ID}/decide$`) },
  // AF05 (GAF-05): tax flags per account, revenue account per payment type, debtor accounts from contracts.
  { method: "PUT", pattern: new RegExp(`^accounting/ledgers/${ID}/accounts/${ID}/tax-flags$`) },
  { method: "PUT", pattern: new RegExp(`^accounting/ledgers/${ID}/payment-type-accounts$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/sync-debtors$`) },
  // AF05 (GAF-06): second approval of a tax invoice above the limit (read state, approve by a third person).
  { method: "GET", pattern: new RegExp(`^accounting/tax/invoices/${ID}/approval$`) },
  { method: "POST", pattern: new RegExp(`^accounting/tax/invoices/${ID}/second-approval$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/year-carryover$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/year-carryover$`) },
  // S69-04: maintained open item remainders as of a cut-off date; S69-02: approval decisions.
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/open-item-balances$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/open-item-balances/refresh$`) },
  { method: "GET", pattern: /^accounting\/approval-decisions$/ },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/accounts$`) },
  { method: "PATCH", pattern: new RegExp(`^accounting/ledgers/${ID}/accounts/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/accounts/${ID}/(allocations|sheet)$`) },
  { method: "PUT", pattern: new RegExp(`^accounting/ledgers/${ID}/accounts/${ID}/allocations$`) },
  // Payment orders (M15): approval and cancel only; the payment file needs G2.
  { method: "POST", pattern: new RegExp(`^banking/payment-orders/${ID}/(approve|cancel)$`) },
  // Direct debit runs (M15, pain.008): four eyes approval, cancel, file generation as a
  // document. The download stays behind G2 (API); nothing here transmits anything to a bank.
  { method: "GET", pattern: /^accounting\/direct-debits$/ },
  { method: "POST", pattern: new RegExp(`^accounting/direct-debits/${ID}/(approve|cancel|file)$`) },
  // Download hinter G2, Protokoll und Einreichungsbestätigung (M15-01 Folgepunkt).
  { method: "GET", pattern: new RegExp(`^accounting/direct-debits/${ID}/file$`) },
  { method: "GET", pattern: new RegExp(`^accounting/direct-debits/${ID}/downloads$`) },
  { method: "POST", pattern: new RegExp(`^accounting/direct-debits/${ID}/submit$`) },
  { method: "GET", pattern: /^banking\/payment-orders$/ },
  // AF03 (GAF-02): payment files read only (list, one batch with download log, format per
  // account). Create, download and submit stay without BFF path: they are G2 actions (API).
  { method: "GET", pattern: /^banking\/payment-batches$/ },
  { method: "GET", pattern: new RegExp(`^banking/payment-batches/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^banking/payment-bank-config/${ID}$`) },
  // AF03 (GAF-03): bank connections, sync log, learning switch (ADR 0014), decision log per
  // transaction. Connections never return credentials; the switch books nothing.
  { method: "GET", pattern: /^banking\/(connections|runs|learning)$/ },
  { method: "POST", pattern: /^banking\/connections$/ },
  { method: "PUT", pattern: /^banking\/learning$/ },
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/decisions$`) },
  // AF03 (GAF-04): creditor identifier per legal entity (operator input, not validated),
  // direct debit preview and pre-notification drafts (delivery only via M23, nothing sent).
  { method: "PUT", pattern: new RegExp(`^accounting/direct-debits/creditor-ids/(tenant|legal-entities/${ID})$`) },
  { method: "POST", pattern: /^accounting\/direct-debits\/preview$/ },
  { method: "POST", pattern: new RegExp(`^accounting/direct-debits/${ID}/pre-notifications$`) },
  // Payment run (M15-02 to M15-07, S15-02): preview, draft orders, status report import.
  // Approval stays per order (four eyes); the payment file stays behind G2 (API).
  { method: "GET", pattern: /^accounting\/payment-runs\/(preview|bank-status-reports|previews|settings)$/ },
  { method: "POST", pattern: /^accounting\/payment-runs\/(orders|payout-orders|bank-status-reports|previews)$/ },
  { method: "GET", pattern: new RegExp(`^accounting/direct-debits/${ID}/reconciliation$`) },
  { method: "POST", pattern: new RegExp(`^accounting/direct-debits/${ID}/bank-status$`) },
  { method: "PUT", pattern: /^accounting\/payment-runs\/settings$/ },
  { method: "GET", pattern: /^accounting\/tax\/section35a\/certificate(\.pdf)?$/ },
  { method: "GET", pattern: new RegExp(`^accounting/payment-runs/bank-limits/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^accounting/payment-runs/bank-limits/${ID}$`) },
  // AE22 (P04-04, Q01-01): payables from statement credits. Switch default off; release G3
  // and four eyes, payout order G2 and G3, reversal of a posted reclass G1 (API).
  { method: "GET", pattern: /^accounting\/credit-payables(\/(candidates|settings))?$/ },
  { method: "PUT", pattern: /^accounting\/credit-payables\/settings$/ },
  { method: "POST", pattern: /^accounting\/credit-payables$/ },
  { method: "GET", pattern: new RegExp(`^accounting/credit-payables/${ID}(/payout-options)?$`) },
  { method: "POST", pattern: new RegExp(`^accounting/credit-payables/${ID}/(release|payment-order|withdraw)$`) },
  // finAPI (M11-finapi): read only aggregator onboarding, consent, fetch (Stufen 1-3).
  { method: "GET", pattern: /^banking\/finapi\/config$/ },
  { method: "PUT", pattern: /^banking\/finapi\/config$/ },
  { method: "GET", pattern: /^banking\/finapi\/connections$/ },
  { method: "POST", pattern: /^banking\/finapi\/connections$/ },
  { method: "POST", pattern: new RegExp(`^banking/finapi/connections/${ID}/(check|reauthorize|disconnect|fetch)$`) },
  { method: "POST", pattern: new RegExp(`^banking/finapi/accounts/${ID}/(assign|fetch)$`) },
  // FinTS/HBCI PIN/TAN (M11-01 Nachtrag 27.09.2026): Institutssuche, Verbindung, TAN-Sitzung, Konten.
  { method: "GET", pattern: /^banking\/fints\/institutes$/ },
  { method: "GET", pattern: /^banking\/fints\/connections$/ },
  { method: "POST", pattern: /^banking\/fints\/connections$/ },
  { method: "POST", pattern: new RegExp(`^banking/fints/connections/${ID}/(restart|refresh)$`) },
  { method: "DELETE", pattern: new RegExp(`^banking/fints/connections/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^banking/fints/connections/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^banking/fints/sessions/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^banking/fints/sessions/${ID}/tan$`) },
  { method: "POST", pattern: new RegExp(`^banking/fints/accounts/${ID}/assign$`) },
  // EBICS-Grundgerüst (M11-01, AE23): Schalter, Teilnehmer, Schlüssel, INI/HIA, HPB, Prüfung, C53.
  // Nur Abruf, keine Zahlung (G2 bleibt geschlossen); Übertragung erst mit geprüfter Implementierung.
  { method: "GET", pattern: /^banking\/ebics\/(status|subscribers)$/ },
  { method: "PUT", pattern: /^banking\/ebics\/settings$/ },
  { method: "POST", pattern: /^banking\/ebics\/subscribers$/ },
  { method: "GET", pattern: new RegExp(`^banking/ebics/subscribers/${ID}(/letters|/letters\\.pdf)?$`) },
  {
    method: "POST",
    pattern: new RegExp(
      `^banking/ebics/subscribers/${ID}/(keys|signature-key|ini|ini/external|hia|activation|hpb|bank-keys/verify|suspend|statements)$`,
    ),
  },
  // Bankkontenauswahl: Kontenliste je Objekt und Rechtsträger, Zuordnung und Standardkonto.
  // Nur lesend und organisatorisch, kein Zahlungsverkehr (G2 bleibt geschlossen).
  { method: "GET", pattern: /^banking\/accounts$/ },
  { method: "PUT", pattern: new RegExp(`^banking/accounts/${ID}/assignments$`) },
  { method: "DELETE", pattern: new RegExp(`^banking/accounts/${ID}/assignments/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^banking/accounts/${ID}/legal-entity-default$`) },
  // Verbrauchsinformation je Objekt (Regel H03): Monate, Objektschalter, manueller Lauf.
  { method: "GET", pattern: new RegExp(`^properties/${ID}/consumption-info$`) },
  { method: "PUT", pattern: new RegExp(`^properties/${ID}/consumption-info/settings$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/consumption-info/run$`) },
  // D26 substitute process without portal: printable version and recorded delivery.
  { method: "GET", pattern: new RegExp(`^properties/${ID}/consumption-info/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^properties/${ID}/consumption-info/${ID}/delivery$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/bank-account-options$`) },
  // Bankkonten des Rechtsträgers (M16-13): Standardkonto anzeigen und setzen (Restpunkt 27.09.2026).
  { method: "GET", pattern: new RegExp(`^properties/${ID}/bank-accounts$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/bank-accounts/${ID}/default$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/legal-entities$`) },
  // Einrichtung in drei Schritten (Bank, Regel M11-08): internes Konto für den Dateiweg anlegen.
  { method: "POST", pattern: new RegExp(`^properties/${ID}/bank-accounts$`) },
  // Dienstleister/Handwerker je Objekt (Regel M11-08): Liste, Verknüpfen, Gewerk, Lösen, Nachziehen.
  { method: "GET", pattern: new RegExp(`^properties/${ID}/creditors$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/creditors$`) },
  { method: "PATCH", pattern: new RegExp(`^properties/${ID}/creditors/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^properties/${ID}/creditors/${ID}$`) },
  { method: "POST", pattern: /^properties\/creditors\/backfill$/ },
  { method: "GET", pattern: new RegExp(`^contacts/${ID}/creditor-properties$`) },
  // Kreditor anlegen aus dem Buchungsdialog: Gegenpartei prüfen, Kontakt mit Rolle Dienstleister.
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/counterparty-contact$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/creditor-contact$`) },
  // Eigentümer festlegen (operator 26.09.2026): Objekteigentümer der Mietverwaltung.
  { method: "GET", pattern: new RegExp(`^properties/${ID}/owners$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/owner$`) },
  // Stammdaten in der Oberfläche (C2, 28.09.2026): Eigentümerdetails, Ansprechpartner, Zähler
  // mit Zählerwechsel, Wartungen mit Erledigung; Zusatzfeldwerte über PATCH properties/{id}.
  { method: "PUT", pattern: new RegExp(`^properties/${ID}/owners/${ID}/details$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/contacts$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/contacts$`) },
  { method: "PATCH", pattern: new RegExp(`^properties/${ID}/contacts/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/meters$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/meters$`) },
  { method: "PATCH", pattern: new RegExp(`^meters/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^meters/${ID}/changes$`) },
  { method: "POST", pattern: new RegExp(`^meters/${ID}/changes$`) },
  { method: "GET", pattern: new RegExp(`^meters/${ID}/readings$`) },
  { method: "POST", pattern: new RegExp(`^meters/${ID}/readings$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/maintenance$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/maintenance$`) },
  { method: "PATCH", pattern: new RegExp(`^maintenance/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^maintenance/${ID}/done$`) },
  // Rechnung zu Bankumsatz abgleichen und Zahlungsvorschlag (M11-finapi Stage 3, G2 gesperrt).
  { method: "GET", pattern: new RegExp(`^banking/invoice-matching/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^banking/invoice-matching/${ID}/match$`) },
  // Dunning (M16): preview and approval by a second person; fee amount and Basiszinssatz are
  // only active once the operator has entered them (V7).
  { method: "GET", pattern: /^accounting\/dunning-settings$/ },
  { method: "PUT", pattern: /^accounting\/dunning-settings$/ },
  // Remove an object override (M16-10); the object inherits the tenant default again.
  { method: "DELETE", pattern: /^accounting\/dunning-settings$/ },
  { method: "POST", pattern: /^accounting\/dunning-settings\/presets$/ },
  { method: "POST", pattern: /^accounting\/dunning-runs$/ },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-runs/${ID}/approve$`) },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/mark-sent$`) },
  // Dunning letters and Mahnbescheid preparation as PDF drafts (M16-02, A31, A33): preview
  // returns the PDF, the second endpoint files it; nothing is sent, no application is filed.
  { method: "POST", pattern: /^accounting\/dunning-settings\/letter-preview$/ },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/letter(-preview)?$`) },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/mahnbescheid(-preview)?$`) },
  { method: "GET", pattern: /^accounting\/dunning-interest-rates$/ },
  { method: "POST", pattern: /^accounting\/dunning-interest-rates$/ },
  { method: "GET", pattern: new RegExp(`^accounting/dunning-cases/${ID}/delivery-proofs$`) },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/delivery-proofs$`) },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-cases/${ID}/interest-draft$`) },
  { method: "POST", pattern: new RegExp(`^accounting/open-items/${ID}/dunning-blocks$`) },
  { method: "GET", pattern: /^accounting\/dunning-blocks$/ },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-blocks/${ID}/release$`) },
  {
    method: "POST",
    pattern: new RegExp(`^accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung$`),
  },
  {
    method: "GET",
    pattern: new RegExp(`^accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung$`),
  },
  // Operating cost statements (M17): drafting and status steps; issuing needs G3 (API).
  { method: "GET", pattern: /^statements$/ },
  { method: "POST", pattern: /^statements$/ },
  { method: "POST", pattern: new RegExp(`^statements/${ID}/(cost-items|calculate|transition|new-version)$`) },
  // M17-01 to M17-08: draft editing, results with access per tenant, letters (drafts), diff,
  // result entries as drafts (G3 in the API), Belegeinsicht.
  { method: "PATCH", pattern: new RegExp(`^statements/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^statements/${ID}/cost-items/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^statements/${ID}/cost-items/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^statements/${ID}/(results|diff|inspections)$`) },
  { method: "PUT", pattern: new RegExp(`^statements/${ID}/results/${ID}/delivery$`) },
  { method: "POST", pattern: new RegExp(`^statements/${ID}/(letters|letters/preview|result-entries|inspections)$`) },
  // GA06-02: Informationsblatt zur Abrechnung (PDF draft).
  { method: "POST", pattern: new RegExp(`^statements/${ID}/info-sheet/preview$`) },
  // AB07 (GA06-02): info sheet filed and linked to the statement run (G3), outputs list.
  { method: "POST", pattern: new RegExp(`^statements/${ID}/info-sheet$`) },
  { method: "GET", pattern: new RegExp(`^statements/${ID}/outputs$`) },
  { method: "PATCH", pattern: new RegExp(`^statements/${ID}/inspections/${ID}$`) },
  // Draft heating statement (M17-02): inputs, consumption import, preview and feed; G3 unchanged.
  { method: "GET", pattern: new RegExp(`^statements/${ID}/heating(/consumption-info)?$`) },
  { method: "GET", pattern: new RegExp(`^statements/${ID}/heating/comparison(/report)?$`) },
  { method: "PUT", pattern: new RegExp(`^statements/${ID}/heating(/consumptions)?$`) },
  { method: "POST", pattern: new RegExp(`^statements/${ID}/heating/(import-consumptions|calculate|apply)$`) },
  // Metering service heating cost import (M17-09).
  { method: "GET", pattern: new RegExp(`^billing/heating-cost-imports(/${ID})?$`) },
  { method: "POST", pattern: /^billing\/heating-cost-imports$/ },
  { method: "PUT", pattern: new RegExp(`^billing/heating-cost-imports/${ID}(/(mapping|rows))?$`) },
  { method: "POST", pattern: new RegExp(`^billing/heating-cost-imports/${ID}/(csv|check|apply)$`) },
  // Umlagefähigkeit (M17-01) und Vorschussregel (M17-03): Katalog, Zuordnung, Vorschläge mit Bestätigung.
  { method: "GET", pattern: new RegExp(`^statements/${ID}/allocability-check$`) },
  { method: "GET", pattern: new RegExp(`^statements/${ID}/allocation-basis-report$`) },
  { method: "GET", pattern: new RegExp(`^contracts/${ID}/allocation-agreements$`) },
  { method: "POST", pattern: new RegExp(`^contracts/${ID}/allocation-agreements$`) },
  { method: "PATCH", pattern: new RegExp(`^contracts/${ID}/allocation-agreements/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^contracts/${ID}/allocation-agreements/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/allocation-agreements/bulk$`) },
  { method: "GET", pattern: /^billing\/allocation-basis-setting$/ },
  { method: "PUT", pattern: /^billing\/allocation-basis-setting$/ },
  { method: "GET", pattern: new RegExp(`^statements/${ID}/advance-proposals$`) },
  { method: "POST", pattern: new RegExp(`^statements/${ID}/advance-proposals$`) },
  { method: "POST", pattern: new RegExp(`^statements/${ID}/advance-proposals/${ID}/(confirm|reject)$`) },
  { method: "GET", pattern: /^billing\/advance-rule$/ },
  { method: "PUT", pattern: /^billing\/advance-rule$/ },
  { method: "GET", pattern: new RegExp(`^statements/${ID}/deadlines$`) },
  { method: "GET", pattern: /^billing\/deadline-settings$/ },
  { method: "PUT", pattern: /^billing\/deadline-settings$/ },
  { method: "GET", pattern: /^billing\/heating-rule-tables$/ },
  { method: "PUT", pattern: /^billing\/heating-rule-tables$/ },
  { method: "GET", pattern: /^billing\/operating-cost-types$/ },
  { method: "GET", pattern: /^billing\/operating-cost-types\/accounts$/ },
  { method: "PUT", pattern: new RegExp(`^billing/operating-cost-types/accounts/${ID}$`) },
  // KI-Plausibilität eines Abrechnungsentwurfs (A35): Hinweise als Vorschlag, keine Wirkung.
  { method: "GET", pattern: new RegExp(`^(hoa/)?statements/${ID}/ai-check$`) },
  { method: "POST", pattern: new RegExp(`^(hoa/)?statements/${ID}/ai-check$`) },
  // Owner statements (M17, A06): drafts; the PDF needs G3 (API).
  { method: "GET", pattern: /^billing\/owner-statements$/ },
  { method: "GET", pattern: new RegExp(`^billing/owner-statements/${ID}$`) },
  { method: "POST", pattern: /^billing\/owner-statements$/ },
  { method: "POST", pattern: new RegExp(`^billing/owner-statements/${ID}/(calculate|approve)$`) },
  // S69-01: status model of owner and reserve statements.
  { method: "POST", pattern: new RegExp(`^billing/owner-statements/${ID}/transition$`) },
  // GA03-08: output options (attach receipts).
  { method: "PATCH", pattern: new RegExp(`^billing/owner-statements/${ID}/options$`) },
  // AB07 (GA06-03): previews of letter and § 35a proof, filing behind G3, outputs list.
  { method: "GET", pattern: new RegExp(`^billing/owner-statements/${ID}/preview/(letter|s35a)$`) },
  { method: "POST", pattern: new RegExp(`^billing/owner-statements/${ID}/outputs$`) },
  { method: "GET", pattern: new RegExp(`^billing/owner-statements/${ID}/outputs$`) },
  { method: "GET", pattern: /^hoa\/reserve-statements$/ },
  { method: "GET", pattern: new RegExp(`^hoa/reserve-statements/${ID}$`) },
  { method: "POST", pattern: /^hoa\/reserve-statements$/ },
  { method: "POST", pattern: new RegExp(`^hoa/reserve-statements/${ID}/(calculate|transition)$`) },
  // HOA (M24, M25): drafts, calculation, resolution bound to the snapshot, meeting steps.
  // Issuing, due and posting of statements need G4 (checked by the API).
  { method: "POST", pattern: /^hoa\/(plans|statements|meetings|resolutions|special-levies)$/ },
  { method: "POST", pattern: new RegExp(`^hoa/special-levies/${ID}/(calculate|resolve|apply|amend)$`) },
  { method: "POST", pattern: /^hoa\/majority-rules$/ },
  // Umlaufbeschluss mit abgesenkter Mehrheit (M25-02): recording and the per tenant switch.
  { method: "POST", pattern: /^hoa\/circular-resolutions$/ },
  { method: "GET", pattern: /^hoa\/circular-lower-majority$/ },
  // AG07 (GAF-32): portal circular votes (read only) and the portal switch.
  { method: "GET", pattern: /^hoa\/(portal-circular-votes|portal-circular-settings)$/ },
  { method: "GET", pattern: new RegExp(`^hoa/meetings/${ID}/portal-circular-votes$`) },
  { method: "PUT", pattern: /^hoa\/portal-circular-settings$/ },
  // M14-02 (U01): Auswahl für Beschluss und Wirtschaftsplanposition in der Rechnungserfassung.
  { method: "GET", pattern: /^hoa\/(plans|resolutions)$/ },
  { method: "GET", pattern: new RegExp(`^hoa/plans/${ID}$`) },
  { method: "PUT", pattern: /^hoa\/circular-lower-majority$/ },
  // Darlehen, Versicherungsfälle, Maßnahmen (W10, A59) und erklärte Differenzen der
  // Überleitungsrechnung (W04, A60): Erfassung und Nachweis, keine Buchung.
  { method: "POST", pattern: /^hoa\/(loans|measures|insurance-claims)$/ },
  { method: "POST", pattern: new RegExp(`^hoa/(loans|insurance-claims)/${ID}/items$`) },
  { method: "POST", pattern: new RegExp(`^hoa/measures/${ID}/financing$`) },
  { method: "PATCH", pattern: new RegExp(`^hoa/(measures|insurance-claims)/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^hoa/statements/${ID}/reconciliation-notes$`) },
  // Beiratszugang und Antworten am Prüfauftrag (A52); der Beirat selbst arbeitet im Portal.
  { method: "POST", pattern: new RegExp(`^hoa/audit-engagements/${ID}/board-access$`) },
  { method: "POST", pattern: new RegExp(`^hoa/audit-engagements/${ID}/board-access/${ID}/revoke$`) },
  { method: "POST", pattern: new RegExp(`^hoa/audit-engagements/${ID}/notes/${ID}/answer$`) },
  { method: "POST", pattern: new RegExp(`^hoa/plans/${ID}/(items|calculate|transition|apply)$`) },
  // Wirtschaftsplan in die Zahlungspläne (W02): Vorschau vor der Bestätigung durch die zweite Person.
  { method: "GET", pattern: new RegExp(`^hoa/plans/${ID}/apply/preview$`) },
  // AE09 (W02, M12-L2): difference of posted months after a plan change within the year.
  { method: "GET", pattern: new RegExp(`^hoa/plans/${ID}/differences$`) },
  { method: "POST", pattern: new RegExp(`^hoa/plans/${ID}/differences/draft$`) },
  { method: "POST", pattern: new RegExp(`^hoa/plan-differences/${ID}/(approve|reject)$`) },
  { method: "GET", pattern: /^hoa\/plan-change-settings$/ },
  { method: "PUT", pattern: /^hoa\/plan-change-settings$/ },
  { method: "POST", pattern: new RegExp(`^hoa/statements/${ID}/(costs|calculate|transition|post|new-version)$`) },
  // W2 P07 (M24-01, M24-02): reserves, reserve movements, costs from the ledger.
  { method: "POST", pattern: /^hoa\/reserves$/ },
  { method: "POST", pattern: new RegExp(`^hoa/statements/${ID}/(reserve-movements|costs/from-ledger)$`) },
  // GA07-03: Sondererwerb im Abrechnungsjahr beantragen und freigeben (vier Augen).
  { method: "POST", pattern: new RegExp(`^hoa/statements/${ID}/acquisitions/${ID}/(request|release)$`) },
  { method: "GET", pattern: /^hoa\/acquisition-rules$/ },
  { method: "PUT", pattern: /^hoa\/acquisition-rules\/[a-z_]+$/ },
  // T09 (M24-01): reserve detail, change, development per year, movements of a statement.
  { method: "GET", pattern: new RegExp(`^hoa/reserves/${ID}(/development)?$`) },
  { method: "PATCH", pattern: new RegExp(`^hoa/reserves/${ID}$`) },
  // AE07 (M24-01, V01-01): reserve plan per year and opening change switch.
  { method: "GET", pattern: new RegExp(`^hoa/reserves/${ID}/(plans|opening-changes)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/reserves/${ID}/plans$`) },
  { method: "GET", pattern: new RegExp(`^hoa/reserve-plans/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^hoa/reserve-plans/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^hoa/reserve-plans/${ID}/resolve$`) },
  { method: "POST", pattern: new RegExp(`^hoa/plans/${ID}/reserve-plans/derive$`) },
  { method: "GET", pattern: /^hoa\/reserve-policy$/ },
  { method: "PUT", pattern: /^hoa\/reserve-policy$/ },
  { method: "POST", pattern: new RegExp(`^hoa/reserve-opening-changes/${ID}/(approve|reject)$`) },
  // AE08 (P07-02): Soll and Ist per earmarked reserve, variant switch.
  { method: "GET", pattern: new RegExp(`^hoa/ledgers/${ID}/reserve-payments$`) },
  { method: "GET", pattern: /^hoa\/reserve-payment-settings$/ },
  { method: "PUT", pattern: /^hoa\/reserve-payment-settings$/ },
  { method: "GET", pattern: /^hoa\/correction-report-settings$/ },
  { method: "PUT", pattern: /^hoa\/correction-report-settings$/ },
  { method: "GET", pattern: /^hoa\/allocation-proposal-settings$/ },
  { method: "PUT", pattern: /^hoa\/allocation-proposal-settings$/ },
  { method: "GET", pattern: /^hoa\/statements\/[0-9a-f-]{36}\/allocation-proposal$/ },
  { method: "POST", pattern: new RegExp(`^hoa/inspection-requests/ownership-transfers/scan$`) },
  { method: "GET", pattern: new RegExp(`^hoa/statements/${ID}/reserve-movements$`) },
  { method: "DELETE", pattern: new RegExp(`^hoa/statements/${ID}/reserve-movements/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/(agenda|invite|attendance)$`) },
  // AD06 / GA11-03: Online-Abstimmung je TOP öffnen/schließen, Wortmeldung abarbeiten.
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/agenda/${ID}/voting/(open|close)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/speaker-requests/${ID}$`) },
  // AE31 (AD06-02): Stimmkonflikt Vollmacht gegen eigene Stimme entscheiden.
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/vote-conflicts/${ID}/resolve$`) },
  // Protokollentwurf der Versammlung als PDF (A62); Download über /api/handover-files.
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/protocol-draft$`) },
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/close(/confirm|/withdraw)?$`) },
  // AF09 (GAF-15): Empfängerliste der Einladung, Störungsprotokoll der Online-Versammlung.
  { method: "GET", pattern: new RegExp(`^hoa/meetings/${ID}/invitation-recipients$`) },
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/disruptions$`) },
  // Mehrheitsregeln je Beschlussgegenstand (M25-01): Prüfung nur als Anzeige, keine Statusänderung.
  { method: "GET", pattern: /^hoa\/majority-rules\/subject-rules$/ },
  { method: "POST", pattern: /^hoa\/majority-rules\/subject-rules$/ },
  { method: "PUT", pattern: new RegExp(`^hoa/majority-rules/subject-rules/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^hoa/majority-rules/subject-rules/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^hoa/majority-rules/subject-rules/${ID}/approve$`) },
  { method: "GET", pattern: new RegExp(`^hoa/resolutions/${ID}/majority-check$`) },
  // Beschlussfrist der virtuellen Versammlung (M9-07).
  { method: "PATCH", pattern: new RegExp(`^hoa/meetings/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^hoa/agenda/${ID}/votes$`) },
  { method: "GET", pattern: new RegExp(`^hoa/agenda/${ID}/tally$`) },
  { method: "POST", pattern: new RegExp(`^hoa/agenda/${ID}/announce$`) },
  { method: "PATCH", pattern: new RegExp(`^hoa/agenda/${ID}$`) }, // GA03-02
  // Einsichtsanfragen außerhalb des Portals (A61): Erfassung, Statuswechsel, Rückfragen, Paket.
  { method: "GET", pattern: /^hoa\/inspection-requests$/ },
  { method: "POST", pattern: /^hoa\/inspection-requests$/ },
  { method: "GET", pattern: new RegExp(`^hoa/inspection-requests/${ID}(/candidates|/package)?$`) },
  { method: "POST", pattern: new RegExp(`^hoa/inspection-requests/${ID}/(transition|notes|package|revoke|owner-check)$`) },
  // Prüfposition: Änderungshistorie und Berichtsbestätigung (M25-03, M25-05).
  { method: "GET", pattern: new RegExp(`^hoa/audit-items/${ID}/history$`) },
  { method: "POST", pattern: new RegExp(`^hoa/audits/${ID}/reports/[0-9]+/confirm$`) },
  // Letting (M26): rent increase process (sending needs G3, checked by the API), prospects.
  { method: "POST", pattern: /^letting\/(rent-increases|prospects)$/ },
  { method: "POST", pattern: new RegExp(`^letting/rent-increases/${ID}/actions$`) },
  // Mieterhöhungsschreiben auf dem Briefbogen mit Versandnachweis; der Versand bleibt hinter G3.
  { method: "POST", pattern: new RegExp(`^letting/rent-increases/${ID}/letter/pdf$`) },
  { method: "PATCH", pattern: new RegExp(`^letting/prospects/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^letting/prospects/${ID}$`) },
  // Mietspiegelpflege und Übernahme der Spanne (M26-03), Interessentenabgleich (M26-06),
  // Exposé als PDF mit Bildern (M26-05), Mieterhöhungsfälle je Vertrag (M5-08).
  { method: "GET", pattern: /^letting\/rent-index(\/lookup)?$/ },
  { method: "POST", pattern: /^letting\/rent-index(\/import)?$/ },
  { method: "DELETE", pattern: new RegExp(`^letting/rent-index/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^letting/rent-increases/${ID}/adopt-rent-index$`) },
  // M26-01: KI-Plausibilität des Mieterhöhungsfalls (nur Hinweise).
  { method: "GET", pattern: new RegExp(`^letting/rent-increases/${ID}/ai-check$`) },
  { method: "POST", pattern: new RegExp(`^letting/rent-increases/${ID}/ai-check$`) },
  { method: "GET", pattern: /^letting\/rent-increases$/ },
  { method: "GET", pattern: new RegExp(`^letting/listings/${ID}/prospect-matches$`) },
  { method: "POST", pattern: new RegExp(`^letting/units/${ID}/expose/pdf$`) },
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
  // Zählerstände übernehmen (Package F): Zählerstände des Protokolls in die Stammdaten der Einheit.
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/meters/transfer$`) },
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/(documents|signatures|complete|versions|status|dispatches)$`) },
  // Änderung nach Unterschrift (M30-09): reopen the content with a mandatory reason.
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/changes$`) },
  // Mängel als Tickets anlegen (S13-01).
  { method: "POST", pattern: new RegExp(`^handover/protocols/${ID}/defects/tickets$`) },
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
  { method: "GET", pattern: new RegExp(`^units/${ID}(/occupants|/allocation-values)?$`) },
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
  // Stammdaten in der Oberfläche (C1): Gebäude, Einheiten, Umlageschlüssel und Schlüsselwerte.
  { method: "POST", pattern: new RegExp(`^properties/${ID}/buildings$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/units$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/allocation-(keys|summary)$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/allocation-keys$`) },
  { method: "PATCH", pattern: new RegExp(`^properties/${ID}/allocation-keys/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^units/${ID}/allocation-values$`) },
  // Tickets (M19).
  { method: "POST", pattern: /^tickets$/ },
  { method: "PATCH", pattern: new RegExp(`^tickets/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/comments$`) },
  // Ticketvorlagen (Checkliste, Zusatzfelder inkl. IBAN) und Sammelstatuswechsel (M19-02).
  { method: "GET", pattern: /^tickets\/templates$/ },
  { method: "POST", pattern: /^tickets\/templates$/ },
  { method: "GET", pattern: new RegExp(`^tickets/templates/${ID}$`) },
  // Regel-Engine Stufe 1 (A38): Regeln, Aktivierung, Testlauf ohne Wirkung, Protokoll.
  { method: "GET", pattern: /^automation\/(meta|rules|runs|rule-templates|job-schedules)$/ },
  // Standardjobs je Mandant (S15-03).
  { method: "PUT", pattern: /^automation\/job-schedules\/[a-z0-9-]+$/ },
  { method: "POST", pattern: /^automation\/rules$/ },
  { method: "GET", pattern: new RegExp(`^automation/rules/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^automation/rules/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^automation/rules/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^automation/rules/${ID}/(activate|test)$`) },
  // Lern-Workflow (Regel M9-11): Regelvorschläge aus wiederholten manuellen Entscheidungen.
  { method: "GET", pattern: /^automation\/rule-proposals$/ },
  { method: "POST", pattern: new RegExp(`^automation/rule-proposals/${ID}/(accept|reject)$`) },
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
  // Ticket-Mailverlauf (operator 26.09.2026): Thread mit Anhängen, Vorbelegung der Antwort,
  // Anhangsvorschau nur über den Ticketbezug, Dokumentsuche für eigene Anhänge.
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/(messages|reply-context|reply-documents)$`) },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/mail-attachments/${ID}/content$`) },
  { method: "PATCH", pattern: new RegExp(`^tickets/${ID}/checklist/[a-zA-Z0-9_-]{1,64}$`) },
  { method: "POST", pattern: /^tickets\/bulk-status$/ },
  { method: "POST", pattern: /^tickets\/bulk$/ },
  // Tickets zusammenführen (M36): Zielsuche über die Liste (q), Vorschau über das Detail.
  { method: "GET", pattern: /^tickets$/ },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}$`) },
  // Stammdatenänderung aus der Ticket-Mail (Vorschlag, Entscheidung, Antwortentwurf; 26.09.2026).
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/proposals$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/proposals/(contact-change|${ID}/(accept|accept-and-reply|correct|reject|reply-draft))$`) },
  { method: "POST", pattern: /^tickets\/merge$/ },
  { method: "GET", pattern: new RegExp(`^properties/${ID}$`) },
  // Kataloge und Zusatzfelder (P1 AP4, 4.11 und Anhang B): Pflege in den Einstellungen.
  { method: "GET", pattern: /^catalogs$/ },
  { method: "GET", pattern: /^catalogs\/[a-z][a-z0-9_]{0,62}$/ },
  { method: "POST", pattern: /^catalogs\/[a-z][a-z0-9_]{0,62}$/ },
  { method: "PATCH", pattern: new RegExp(`^catalogs/[a-z][a-z0-9_]{0,62}/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^catalogs/[a-z][a-z0-9_]{0,62}/${ID}$`) },
  { method: "GET", pattern: /^custom-fields$/ },
  { method: "POST", pattern: /^custom-fields$/ },
  { method: "PATCH", pattern: new RegExp(`^custom-fields/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^custom-fields/${ID}$`) },
  // Energieausweis am Objekt (A63): Objektstammdaten vollständig speichern.
  { method: "PUT", pattern: new RegExp(`^properties/${ID}$`) },
  // Zuweiser mit Grund (operator 25.09.2026, mail-optimierung M20).
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/assignees$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/assignees$`) },
  { method: "DELETE", pattern: new RegExp(`^tickets/${ID}/assignees/${ID}$`) },
  // Rechnung zuordnen (M11-finapi Stage 3): Kategorie Rechnung, Jahresablage im Objektordner.
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/attach-invoice$`) },
  // Paperless-Dokumente in Ticket- und Objektansicht (M31).
  { method: "GET", pattern: new RegExp(`^properties/${ID}/dms-documents$`) },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/dms-documents$`) },
  // Arbeitsaufträge (A74): Terminvorschläge je Auftrag für die Kurzanzeige im Ticket und die Auftragsseite.
  { method: "GET", pattern: new RegExp(`^work-orders/${ID}/appointment-proposals$`) },
  { method: "GET", pattern: new RegExp(`^work-orders/${ID}/rating$`) },
  { method: "POST", pattern: new RegExp(`^work-orders/${ID}/rating$`) },
  // Auftragsliste und Auftragsdetail, Teams, Kommentarliste (M19-01, M19-02, M19-07).
  { method: "GET", pattern: /^work-orders$/ },
  { method: "GET", pattern: new RegExp(`^work-orders/${ID}$`) },
  { method: "GET", pattern: /^teams$/ },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/comments$`) },
  { method: "DELETE", pattern: new RegExp(`^tickets/${ID}/comments/${ID}$`) },
  { method: "GET", pattern: /^dms-documents\/[0-9]+\/file$/ },
  // Paperless-Suche und Gesellschaftsfilter (Übernahme aus dem Immoware Hub, 7.2), nur lesend.
  { method: "GET", pattern: /^dms-documents$/ },
  { method: "GET", pattern: /^dms-documents\/companies$/ },
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
  // Nachforderungsschreiben auf dem Briefbogen mit Versandnachweis (M12 Lücken, 29.09.2026).
  {
    method: "POST",
    pattern: new RegExp(`^objektakte/properties/${ID}/completeness/nachforderungsschreiben/pdf$`),
  },
  // Objektakte-Export für den Nachfolger: starten, Stand, Liste, Download (Ereignis je Abruf).
  { method: "GET", pattern: new RegExp(`^properties/${ID}/objektakte-export$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/objektakte-export$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/objektakte-export/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/objektakte-export/${ID}/download$`) },

  // Objektakte-Übernahme, Stufe 4/5 (Synchronisationsstand, Löschmarkierungen, KI-Kosten).
  { method: "GET", pattern: /^objektakte\/sync$/ },
  { method: "PUT", pattern: /^objektakte\/sync$/ },
  { method: "POST", pattern: /^objektakte\/sync\/runs$/ },
  { method: "GET", pattern: /^objektakte\/sync\/deletions$/ },
  { method: "GET", pattern: /^objektakte\/ai-calls\/summary$/ },
  // M35 Parallelbetrieb: Abgleichbericht objektakte gegen CRM, Vorschaubild-Übernahme, lokales Modell.
  { method: "GET", pattern: /^objektakte\/reconciliation$/ },
  { method: "POST", pattern: /^objektakte\/imports$/ },
  { method: "GET", pattern: new RegExp(`^objektakte/imports/${ID}$`) },
  // GAG-12: Verlauf der Importläufe und OCR-Cache leeren.
  { method: "GET", pattern: /^objektakte\/import-runs$/ },
  { method: "DELETE", pattern: new RegExp(`^objektakte/import-runs/${ID}/ocr-cache$`) },
  { method: "POST", pattern: new RegExp(`^objektakte/imports/${ID}/ocr-cache$`) },
  { method: "GET", pattern: /^objektakte\/previews\/import$/ },
  { method: "POST", pattern: /^objektakte\/previews\/import$/ },
  { method: "GET", pattern: new RegExp(`^objektakte/previews/documents/${ID}$`) },
  { method: "GET", pattern: /^objektakte\/local-model$/ },
  { method: "POST", pattern: new RegExp(`^objektakte/local-model/cases/${ID}/propose$`) },
  // DMS-Seite mit Daten der Objektübernahme (M29 Stufe 4, Abruf serverseitig durch die API).
  { method: "GET", pattern: /^integrations\/objektakte\/objects\/[0-9A-Za-z]{1,16}\/documents$/ },
  { method: "POST", pattern: /^integrations\/objektakte\/objects\/[0-9A-Za-z]{1,16}\/documents\/link$/ },
  { method: "POST", pattern: /^integrations\/objektakte\/objects\/[0-9A-Za-z]{1,16}\/person-proposals$/ },
  { method: "POST", pattern: /^integrations\/objektakte\/objects\/[0-9A-Za-z]{1,16}\/persons-export$/ },
  { method: "GET", pattern: /^integrations\/objektakte\/person-proposals$/ },
  // Ablagestand eines CRM-Dokuments über objektakte (Upload 26.09.2026).
  { method: "GET", pattern: new RegExp(`^integrations/objektakte/documents/${ID}/filing$`) },
  { method: "GET", pattern: new RegExp(`^integrations/objektakte/person-proposals/${ID}$`) },
  {
    method: "POST",
    pattern: new RegExp(`^integrations/objektakte/person-proposals/${ID}/(test-run|approve|reject)$`),
  },
  { method: "GET", pattern: /^document-categories$/ },
  // Ordnerstruktur der Objektakte und fehlende Standardkategorien (Package F).
  { method: "GET", pattern: /^document-folders$/ },
  { method: "POST", pattern: /^document-categories\/ensure-defaults$/ },
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
  // M14-02 (Welle 5 T05): sachliche Prüfung als Befunde und Toleranzen je Mandant.
  { method: "GET", pattern: new RegExp(`^accounting/invoices/${ID}/factual-check$`) },
  { method: "GET", pattern: /^accounting\/invoice-check-settings$/ },
  { method: "PUT", pattern: /^accounting\/invoice-check-settings$/ },
  // M14-01, M14-08 (Welle 2 P03): Kreditoren mit Saldo, offenen Posten und Kontoauszug;
  // Rechnungspläne lesen, ändern, beenden, löschen; Gutschrift als XRechnung (S711-02).
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/creditors$`) },
  { method: "GET", pattern: new RegExp(`^accounting/ledgers/${ID}/creditors/${ID}/(open-items|statement)$`) },
  { method: "GET", pattern: /^accounting\/recurring-invoices$/ },
  { method: "POST", pattern: /^accounting\/recurring-invoices$/ },
  { method: "GET", pattern: new RegExp(`^accounting/recurring-invoices/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^accounting/recurring-invoices/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^accounting/recurring-invoices/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/recurring-invoices/${ID}/(end|generate)$`) },
  { method: "GET", pattern: new RegExp(`^accounting/admin-fee-invoices/${ID}/xrechnung-credit-note(\\.xml|/check)$`) },
  // S711-01: Validierungsergebnis einer E-Rechnung speichern.
  { method: "POST", pattern: new RegExp(`^receipts/drafts/${ID}/validation$`) },
  // Beleg aus Paperless holen und als Rechnung erfassen (M14 KI-Extraktion, manuelle Aktion).
  { method: "POST", pattern: /^invoices\/intake\/paperless$/ },
  // Schadenbearbeiter (INT-SDT-01): settings (secrets write only), connection test, pull,
  // takeover queue and ticket actions. The public webhook is not proxied.
  { method: "GET", pattern: /^integrations\/schadenstool\/config$/ },
  { method: "PUT", pattern: /^integrations\/schadenstool\/config$/ },
  { method: "POST", pattern: /^integrations\/schadenstool\/(config\/test|pull)$/ },
  { method: "GET", pattern: /^integrations\/schadenstool\/takeover$/ },
  { method: "POST", pattern: new RegExp(`^integrations/schadenstool/takeover/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^integrations/schadenstool/tickets/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^integrations/schadenstool/tickets/${ID}/(handover|comments|attachments)$`) },
  // Lexware Office (INT-LEXO-01): configs per legal entity (key write only), invoice kind
  // mapping, queue, contact links, invoice drafts, recurring preparations, invoice copies.
  { method: "GET", pattern: /^integrations\/lexoffice\/(config|configs|runs|outbox|legal-entities|invoice-kinds|invoice-drafts|recurring-preps)$/ },
  { method: "PUT", pattern: /^integrations\/lexoffice\/(config|invoice-kinds)$/ },
  { method: "POST", pattern: /^integrations\/lexoffice\/(test|configs|invoice-drafts|invoice-drafts\/preview)$/ },
  { method: "GET", pattern: new RegExp(`^integrations/lexoffice/configs/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^integrations/lexoffice/configs/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^integrations/lexoffice/configs/${ID}/(test|contacts/match|contacts/links/push-batch)$`) },
  { method: "GET", pattern: new RegExp(`^integrations/lexoffice/configs/${ID}/(runs|contacts/links|contacts/search)$`) },
  { method: "POST", pattern: new RegExp(`^integrations/lexoffice/configs/${ID}/contacts/links/${ID}/(decide|retry|push|resolve-conflict)$`) },
  { method: "POST", pattern: new RegExp(`^integrations/lexoffice/outbox/${ID}/retry$`) },
  { method: "GET", pattern: new RegExp(`^integrations/lexoffice/contacts/${ID}/lexoffice$`) },
  { method: "GET", pattern: new RegExp(`^integrations/lexoffice/invoice-drafts/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^integrations/lexoffice/recurring-preps/${ID}/(done|dismiss)$`) },
  { method: "GET", pattern: new RegExp(`^integrations/lexoffice/tickets/${ID}/invoice-copies$`) },
  { method: "POST", pattern: new RegExp(`^integrations/lexoffice/tickets/${ID}/invoice-copies$`) },
  { method: "POST", pattern: new RegExp(`^integrations/lexoffice/invoice-copies/${ID}/(correct|accept|reject|link-recipient)$`) },
  // Telefonie (13.5, A70): settings (secret write only), call list, callback proposal.
  { method: "GET", pattern: /^communication\/telephony\/settings$/ },
  { method: "PUT", pattern: /^communication\/telephony\/settings$/ },
  { method: "GET", pattern: /^communication\/calls$/ },
  { method: "PATCH", pattern: new RegExp(`^communication/calls/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^communication/calls/${ID}/(assign|proposal/accept|proposal/dismiss)$`) },
  { method: "GET", pattern: new RegExp(`^contacts/${ID}/calls$`) },
  // Kommunikation (M23): Kontakthistorie, Zustellung je Zustellweg, Serienbrief aus Vorlage,
  // Nachweis, Kalender-Abo mit Token. Leerstandsmaßnahmen der Vermietung (M26-04).
  { method: "GET", pattern: new RegExp(`^contacts/${ID}/history$`) },
  { method: "POST", pattern: /^dispatches$/ },
  { method: "POST", pattern: /^dispatches\/(serial|serial-merge)$/ },
  { method: "POST", pattern: new RegExp(`^dispatches/${ID}/evidence$`) },
  { method: "GET", pattern: /^document-templates$/ },
  // AE16 (AA11-01/02): Textbausteine mit Freigabe.
  { method: "GET", pattern: new RegExp(`^document-text-blocks(/codes|/policy|/${ID})?$`) },
  { method: "PUT", pattern: /^document-text-blocks\/policy$/ },
  { method: "POST", pattern: /^document-text-blocks$/ },
  { method: "PATCH", pattern: new RegExp(`^document-text-blocks/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^document-text-blocks/${ID}/(submit|approve|reject|retire)$`) },
  // AE29 (M21-04): Rechtstexte des Portals, Freigabestand, Schalter und Abgleich der Fassung.
  { method: "GET", pattern: /^tenant\/legal-texts-config$/ },
  { method: "PUT", pattern: /^tenant\/legal-texts-config$/ },
  { method: "POST", pattern: /^tenant\/legal-texts-config\/apply-terms-version$/ },
  { method: "PATCH", pattern: new RegExp(`^document-templates/${ID}$`) },
  { method: "GET", pattern: /^generated-documents$/ },
  { method: "PATCH", pattern: new RegExp(`^work-orders/${ID}/approval-workflow$`) },
  { method: "GET", pattern: /^workspace\/calendar-feed\/token$/ },
  { method: "POST", pattern: /^workspace\/calendar-feed\/token$/ },
  { method: "DELETE", pattern: /^workspace\/calendar-feed\/token$/ },
  // AH20 (GAG-34): Kalender als ICS-Datei (Download aus der Kalenderseite).
  { method: "GET", pattern: /^workspace\/calendar\.ics$/ },
  { method: "PUT", pattern: new RegExp(`^letting/vacancies/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^letting/vacancies/${ID}/listing$`) },
  // Belegeingang (M14): KI-Entwürfe aus Upload, Mail-Anhang oder Paperless, Feldprüfung, Entscheidung.
  { method: "GET", pattern: /^receipts\/drafts$/ },
  { method: "POST", pattern: /^receipts\/drafts$/ },
  { method: "POST", pattern: /^receipts\/drafts\/paperless$/ },
  { method: "GET", pattern: new RegExp(`^receipts/drafts/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^receipts/drafts/${ID}/(confirm|reject)$`) },
  // Upload only (multipart); document reads stay outside the allowlist.
  { method: "POST", pattern: /^documents$/ },
  // Dokumente (R02, Q03): geschwärzte Kopien, Eingangsadresse, direkter Upload (Mandantenschalter).
  { method: "GET", pattern: new RegExp(`^documents/${ID}/redactions$`) },
  { method: "POST", pattern: new RegExp(`^documents/${ID}/redactions$`) },
  { method: "POST", pattern: new RegExp(`^documents/${ID}/redactions/${ID}/release$`) },
  // Dokumenteingang (GAF-01): Eingangsvorschläge annehmen, ablehnen, Folgeaktionen, Automatik zurücknehmen.
  { method: "GET", pattern: /^documents\/intake-proposals$/ },
  { method: "GET", pattern: new RegExp(`^documents/intake-proposals/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^documents/intake-proposals/${ID}/(accept|reject|revert-auto)$`) },
  { method: "POST", pattern: new RegExp(`^documents/intake-proposals/${ID}/followups/[a-z_]+/confirm$`) },
  { method: "GET", pattern: /^document-intake-address$/ },
  { method: "PUT", pattern: /^document-intake-address$/ },
  { method: "GET", pattern: /^document-direct-upload$/ },
  { method: "PUT", pattern: /^document-direct-upload$/ },
  { method: "GET", pattern: /^document-invoice-intake-auto$/ },
  { method: "PUT", pattern: /^document-invoice-intake-auto$/ },
  { method: "POST", pattern: /^documents\/uploads$/ },
  { method: "POST", pattern: new RegExp(`^documents/uploads/${ID}/complete$`) },
  // Q03 (M6-01 to M6-09): ZIP bulk upload, letter templates, letters with preview, serial
  // letters (drafts filed, nothing sent), category tree.
  { method: "POST", pattern: /^documents\/zip-import$/ },
  { method: "POST", pattern: /^document-templates$/ },
  { method: "POST", pattern: /^letters(\/preview|\/serial)?$/ },
  { method: "POST", pattern: /^document-categories$/ },
  // Schwarzes Brett je Objekt (M21-01, A54): maintenance of notices at the property.
  // Verwaltung beenden und wieder aktivieren (operator 27.09.2026).
  { method: "GET", pattern: new RegExp(`^properties/${ID}/termination$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/(terminate|reactivate)$`) },
  { method: "GET", pattern: new RegExp(`^properties/${ID}/notices$`) },
  { method: "POST", pattern: new RegExp(`^properties/${ID}/notices$`) },
  { method: "PATCH", pattern: new RegExp(`^notices/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^notices/${ID}/end$`) },
  { method: "GET", pattern: new RegExp(`^notices/${ID}/reads$`) },
  // Messdienstleister (mhvp.metering Stufe 1): Verbindungen, Zuordnungen, Abruf, Klärung, CSV.
  { method: "GET", pattern: /^metering\/(providers|connections|assignments|sync-jobs|clearing-items|assignments-export|assignments-import\/template)$/ },
  { method: "POST", pattern: /^metering\/(connections|assignments|sync-jobs)$/ },
  { method: "GET", pattern: new RegExp(`^metering/(connections|assignments|sync-jobs)/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^metering/(connections|assignments|unit-assignments)/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^metering/connections/${ID}/secrets$`) },
  { method: "POST", pattern: new RegExp(`^metering/connections/${ID}/test$`) },
  { method: "POST", pattern: new RegExp(`^metering/assignments/${ID}/(remote-confirm|change-provider|units)$`) },
  { method: "GET", pattern: new RegExp(`^metering/assignments/${ID}/(units|consumption|billing-results)$`) },
  { method: "POST", pattern: new RegExp(`^metering/clearing-items/${ID}/resolve$`) },
  { method: "POST", pattern: /^metering\/assignments-import\/(preview|apply)$/ },
  { method: "POST", pattern: new RegExp(`^metering/connections/${ID}/heiwako-import/preview$`) },
  // Aufbewahrungsmatrix und Löschvorschläge (M6-04, V17): Profile, Kategoriezuordnung, Läufe.
  { method: "PATCH", pattern: new RegExp(`^retention-profiles/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^retention-profiles/(${ID}/release|apply)$`) },
  { method: "PATCH", pattern: new RegExp(`^document-categories/${ID}$`) },
  { method: "POST", pattern: /^deletion-proposals$/ },
  { method: "POST", pattern: new RegExp(`^deletion-proposals/${ID}/(approve|reject|execute)$`) },
  // Operations the CRM screens already called but the allowlist missed (operator report
  // 27.09.2026, "Erledigungsarten konnten nicht geladen werden"; found by
  // allowlist-coverage.test.ts). Authorization stays with the API (permission per route).
  { method: "GET", pattern: /^tickets\/resolution-kinds$/ },
  // 1.36.0: signature profile and preview (own profile, preview of a member needs members:read),
  // position of a member (members:update, tenant checked by the API), FinTS setup status.
  { method: "PUT", pattern: /^mail\/signature\/profile$/ },
  { method: "GET", pattern: /^mail\/signature\/preview$/ },
  { method: "PUT", pattern: new RegExp(`^tenant/members/${ID}/position$`) },
  { method: "GET", pattern: /^banking\/fints\/config$/ },
  { method: "GET", pattern: /^banking\/clarifications$/ },
  { method: "POST", pattern: new RegExp(`^banking/clarifications/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/clarification$`) },
  { method: "POST", pattern: new RegExp(`^accounting/ledgers/${ID}/open-items/settlement-proposal(/confirm)?$`) },
  { method: "GET", pattern: /^ai\/embeddings\/status$/ },
  { method: "POST", pattern: /^ai\/embeddings\/reindex$/ },
  { method: "POST", pattern: new RegExp(`^ai/knowledge/${ID}/reject$`) },
  // Rückmeldung "hilfreich / nicht hilfreich" (Audit 29.09.2026): Zähler je Antwort, Wissenseintrag und Playbook.
  { method: "POST", pattern: new RegExp(`^ai/runs/${ID}/feedback$`) },
  { method: "POST", pattern: new RegExp(`^ai/knowledge/${ID}/feedback$`) },
  { method: "POST", pattern: new RegExp(`^mail/playbooks/${ID}/feedback$`) },
  { method: "POST", pattern: new RegExp(`^mail/playbooks/${ID}/use$`) },
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/posting-proposals$`) },
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/relations$`) },
  { method: "PATCH", pattern: new RegExp(`^contacts/${ID}/contact-relations/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^contacts/${ID}/contact-relations/${ID}$`) },
  // WEG: Vermögensbericht und Darlehen (M24-02, M24-03), Belegprüfung, Einwahl, Einladungsfrist.
  { method: "POST", pattern: /^hoa\/asset-reports$/ },
  { method: "PATCH", pattern: new RegExp(`^hoa/asset-reports/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^hoa/asset-reports/${ID}/(calculate|transition)$`) },
  { method: "GET", pattern: new RegExp(`^hoa/asset-reports/${ID}/pdf$`) },
  // AB07 (GA07-02): letter dispatch of the issued asset report (G4).
  { method: "POST", pattern: new RegExp(`^hoa/asset-reports/${ID}/dispatch$`) },
  // Gesamtabrechnung WEG als PDF (M24-03): nur nach interner Freigabe und bei offenem G4 (API).
  { method: "GET", pattern: new RegExp(`^hoa/statements/${ID}/pdf$`) },
  { method: "GET", pattern: new RegExp(`^hoa/statements/${ID}/correction-report$`) },
  { method: "PUT", pattern: new RegExp(`^hoa/statements/${ID}/loan-allocation$`) },
  { method: "POST", pattern: /^hoa\/audits$/ },
  { method: "GET", pattern: new RegExp(`^hoa/audits/${ID}/candidates$`) },
  { method: "POST", pattern: new RegExp(`^hoa/audits/${ID}/(items|reports)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/audit-reports/${ID}/board-statement$`) },
  { method: "PUT", pattern: new RegExp(`^hoa/meetings/${ID}/dial-in$`) },
  { method: "PUT", pattern: /^hoa\/meeting-settings$/ },
  { method: "PUT", pattern: /^hoa\/online-meeting-settings$/ },
  // Vermietung: Absage mit Vorlage und Selbstauskunft-Link (M26-02).
  { method: "GET", pattern: /^letting\/prospects\/rejection-templates$/ },
  { method: "POST", pattern: new RegExp(`^letting/prospects/${ID}/(reject|self-disclosure-link)$`) },
  // Postfach: Re-Authentifizierung, Vertretungen (M20-04), Archiv, Nachladen.
  { method: "POST", pattern: /^mail\/mail-approval\/reauth$/ },
  { method: "POST", pattern: /^mail\/mail-approval\/deputies$/ },
  { method: "DELETE", pattern: new RegExp(`^mail/mail-approval/deputies/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/archive$`) },
  // Rückkanal Gmail zu Plattform (M20-08): Verlauf, Zurücklegen, Automatik zurücknehmen,
  // Abgleich je Postfach, Wartungslauf der Kopien, Spike-Bestätigung.
  { method: "GET", pattern: new RegExp(`^mail/messages/${ID}/sync-events$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/restore-inbox$`) },
  { method: "POST", pattern: new RegExp(`^mail/messages/${ID}/revert-gmail-decision$`) },
  { method: "POST", pattern: new RegExp(`^mail/mailboxes/${ID}/reconcile-state$`) },
  { method: "POST", pattern: /^mail\/maintenance\/align-copies$/ },
  { method: "POST", pattern: /^tenant\/settings\/gmail-spike-confirm$/ },
  { method: "POST", pattern: new RegExp(`^mail/mailboxes/${ID}/backfill$`) },
  // Messwesen: Übermittlungen an den Messdienstleister (Prüfung, Freigabe, Auftrag, Abruf).
  { method: "GET", pattern: /^metering\/transmissions$/ },
  { method: "POST", pattern: /^metering\/transmissions\/check$/ },
  { method: "POST", pattern: new RegExp(`^metering/transmissions/${ID}/(release|order|poll)$`) },
  { method: "POST", pattern: new RegExp(`^automation/webhook-deliveries/${ID}/redeliver$`) },
  // Kontenrahmen-Freigabe (M10-01/M10-02), DATEV-Selbstprüfung (M18-06), Steuern (M14).
  { method: "GET", pattern: /^accounting\/templates$/ },
  { method: "POST", pattern: /^accounting\/templates\/default$/ },
  { method: "POST", pattern: new RegExp(`^accounting/templates/${ID}/(release|submit-review|back-to-draft|versions)$`) },
  { method: "GET", pattern: new RegExp(`^accounting/templates/${ID}/export$`) },
  { method: "GET", pattern: new RegExp(`^accounting/templates/${ID}/coverage-report$`) },
  { method: "PUT", pattern: new RegExp(`^accounting/templates/${ID}/(four-eyes|accounts)$`) },
  // G1 Öffnung (M12-09): Checkliste, Ergebnis je Prüfpunkt, Antrag über den Freigabepfad.
  { method: "GET", pattern: /^accounting\/period-locks(\/settings|\/[0-9a-f-]{36})?$/ },
  { method: "PUT", pattern: /^accounting\/period-locks\/settings$/ },
  { method: "POST", pattern: /^accounting\/period-locks$/ },
  { method: "POST", pattern: /^accounting\/period-locks\/[0-9a-f-]{36}\/(release-request|release)$/ },
  { method: "GET", pattern: /^statements\/[0-9a-f-]{36}\/period-lock$/ },
  { method: "POST", pattern: /^statements\/co2-split$/ },
  { method: "GET", pattern: /^accounting\/g1-opening$/ },
  { method: "PUT", pattern: /^accounting\/g1-opening\/items\/[A-Za-z0-9_]{1,32}$/ },
  { method: "POST", pattern: /^accounting\/g1-opening\/request$/ },
  // AE01 Abnahmeregister (V16)
  { method: "GET", pattern: /^accounting\/acceptance\/cases$/ },
  { method: "GET", pattern: /^accounting\/acceptance\/cases\/D[0-9]{2}$/ },
  { method: "GET", pattern: /^accounting\/acceptance\/export\.md$/ },
  { method: "POST", pattern: /^accounting\/acceptance\/cases\/D[0-9]{2}\/expected$/ },
  { method: "PUT", pattern: new RegExp(`^accounting/acceptance/expected/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/acceptance/expected/${ID}/(submit|decision|results)$`) },
  { method: "GET", pattern: /^accounting\/datev\/exports$/ },
  { method: "POST", pattern: new RegExp(`^accounting/datev/exports/${ID}/check$`) },
  { method: "GET", pattern: new RegExp(`^accounting/datev/exports/${ID}/check$`) },
  { method: "POST", pattern: /^accounting\/datev\/check-file$/ },
  // DATEV file download (accounting:read, legal entity scope checked per run) and the
  // synthetic sample batch for the import test at the tax advisor (M18-06).
  { method: "GET", pattern: new RegExp(`^accounting/datev/exports/${ID}/download$`) },
  { method: "GET", pattern: /^accounting\/datev\/sample-batch$/ },
  { method: "PUT", pattern: /^accounting\/tax\/settings$/ },
  { method: "GET", pattern: new RegExp(`^accounting/tax/(properties|suppliers)/${ID}/profile$`) },
  { method: "PUT", pattern: new RegExp(`^accounting/tax/(properties|suppliers)/${ID}/profile$`) },
  { method: "POST", pattern: /^tenant\/manager-entity$/ },
  { method: "GET", pattern: new RegExp(`^portal-admin/forms/${ID}/submissions$`) },
  // SLA-Freigabe je Kategorie (M19-01) und Beiratsbeteiligung an Tickets (M19-02).
  { method: "POST", pattern: new RegExp(`^sla/rules/${ID}/(approve|revoke-approval)$`) },
  { method: "GET", pattern: /^tickets\/board\/policy$/ },
  { method: "PUT", pattern: /^tickets\/board\/policy$/ },
  { method: "GET", pattern: new RegExp(`^tickets/${ID}/board-submissions$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/board-submissions$`) },
  { method: "POST", pattern: new RegExp(`^tickets/board/submissions/${ID}/(votes|close)$`) },
  // Plattform (M27-01 bis M27-03): Preisliste, G5-Nachweise, Onboarding, Mandantenexport. Only
  // platform administrators pass the API (require_platform_admin); the evidence list never opens
  // G5 itself, the export keeps its four eyes approval in the API.
  { method: "GET", pattern: /^platform\/pricing$/ },
  { method: "PATCH", pattern: new RegExp(`^platform/pricing/items/${ID}$`) },
  { method: "GET", pattern: /^platform\/pricing\/offer\.pdf$/ },
  { method: "GET", pattern: new RegExp(`^platform/tenants/${ID}/g5-evidence$`) },
  { method: "PUT", pattern: new RegExp(`^platform/tenants/${ID}/g5-evidence/[a-z0-9_]{1,48}$`) },
  { method: "POST", pattern: /^platform\/onboarding$/ },
  // AD10 (GB16-01, GB16-02): Wartungsfenster und Monatsverfuegbarkeit, Plattformadministratoren (API prueft).
  { method: "GET", pattern: /^platform\/maintenance-windows$/ },
  { method: "POST", pattern: /^platform\/maintenance-windows$/ },
  { method: "PATCH", pattern: new RegExp(`^platform/maintenance-windows/${ID}$`) },
  { method: "GET", pattern: /^platform\/availability$/ },
  { method: "PUT", pattern: /^platform\/availability$/ },
  // AE36 (AC09-01, AA15-01): Skalierungsmessung (ADR 0021) und Demo-Kennzeichen, Plattformadministratoren (API prueft).
  { method: "GET", pattern: /^platform\/ops\/scale$/ },
  { method: "PATCH", pattern: /^platform\/ops\/scale\/settings$/ },
  { method: "POST", pattern: /^platform\/ops\/scale\/snapshot$/ },
  { method: "PUT", pattern: new RegExp(`^platform/tenants/${ID}/demo$`) },
  { method: "GET", pattern: /^platform\/availability\/live$/ },
  { method: "PUT", pattern: /^platform\/availability\/settings$/ },
  { method: "GET", pattern: new RegExp(`^platform/tenants/${ID}/export-requests$`) },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/export-requests$`) },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/export-requests/${ID}/(approve|reject)$`) },
  { method: "GET", pattern: new RegExp(`^platform/tenants/${ID}/export-requests/${ID}/download$`) },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/export-requests/${ID}/run$`) },
  // Release gates (GA14-04, AB02): platform overview and decisions per tenant, requests and
  // revocations in the signed in tenant; the API checks platform admin and permissions.
  { method: "GET", pattern: new RegExp(`^platform/tenants/${ID}/release-gates$`) },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/release-gates/requests/${ID}/(approve|reject)$`) },
  { method: "GET", pattern: /^tenant\/release-gates(\/checklists|\/requests)?$/ },
  { method: "POST", pattern: /^tenant\/release-gates\/requests$/ },
  { method: "POST", pattern: new RegExp(`^tenant/release-gates/requests/${ID}/revoke$`) },
  // Licences, price list, billing preview and usage history (M27-02, M27-03, M27-05); platform
  // administrators only, checked by the API.
  { method: "GET", pattern: /^platform\/price-list$/ },
  { method: "POST", pattern: /^platform\/price-list$/ },
  { method: "PATCH", pattern: new RegExp(`^platform/price-list/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^platform/price-list/${ID}$`) },
  { method: "GET", pattern: /^platform\/licenses$/ },
  { method: "POST", pattern: /^platform\/licenses$/ },
  { method: "PATCH", pattern: new RegExp(`^platform/licenses/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^platform/licenses/${ID}/end$`) },
  { method: "GET", pattern: new RegExp(`^platform/tenants/${ID}/(billing-preview|usage/history)$`) },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/usage$`) },
  // AA17: Standard-Zustellweg, Nummernkreise, Kundendomains, Mandantenstatus, OIDC-Clients.
  { method: "GET", pattern: /^tenant\/delivery-default$/ },
  { method: "PUT", pattern: /^tenant\/delivery-default$/ },
  { method: "GET", pattern: /^tenant\/number-formats$/ },
  { method: "PUT", pattern: /^tenant\/number-formats$/ },
  { method: "POST", pattern: /^tenant\/number-formats\/preview$/ },
  { method: "GET", pattern: new RegExp(`^platform/tenants/${ID}/domains$`) },
  { method: "POST", pattern: new RegExp(`^platform/tenants/${ID}/domains$`) },
  { method: "DELETE", pattern: new RegExp(`^platform/tenants/${ID}/domains/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^platform/domains/${ID}/verify$`) },
  { method: "PATCH", pattern: new RegExp(`^platform/tenants/${ID}$`) },
  { method: "GET", pattern: /^platform\/audit-events$/ },
  { method: "GET", pattern: /^platform\/oidc-clients$/ },
  { method: "POST", pattern: /^platform\/oidc-clients$/ },
  { method: "POST", pattern: /^platform\/oidc-clients\/[a-z0-9][a-z0-9._-]{1,99}\/(rotate-secret|activate|deactivate)$/ },
  // AF20 (GAF-17/18/24/25/26): Besichtigungen, Makler-Anbindung, OpenImmo-Import, U-Protokoll-Import, Lexware-Läufe, KI-Schalter, Datenqualität.
  { method: "GET", pattern: new RegExp(`^letting/prospects/${ID}/(viewings|self-disclosure-links)$`) },
  { method: "POST", pattern: new RegExp(`^letting/prospects/${ID}/viewings$`) },
  { method: "PATCH", pattern: new RegExp(`^letting/prospects/viewings/${ID}$`) },
  { method: "GET", pattern: /^letting\/broker\/[a-z0-9_-]+\/config$/ },
  { method: "PUT", pattern: /^letting\/broker\/[a-z0-9_-]+\/config$/ },
  { method: "POST", pattern: new RegExp(`^letting/listings/${ID}/broker/[a-z0-9_-]+/sync$`) },
  { method: "POST", pattern: /^letting\/openimmo-import\/preview$/ },
  { method: "POST", pattern: new RegExp(`^letting/openimmo-import/${ID}/rows/${ID}/apply$`) },
  { method: "POST", pattern: /^handover\/imports\/uprotokoll(\/files)?$/ },
  { method: "GET", pattern: /^handover\/imports\/uprotokoll\/files$/ },
  { method: "DELETE", pattern: new RegExp(`^handover/imports/uprotokoll/files/${ID}$`) },
  { method: "GET", pattern: /^accounting\/invoices$/ }, // AG14: Auswahl für den Lexware Export
  { method: "POST", pattern: /^integrations\/lexoffice\/(import\/receipts|export\/contacts|export\/invoices)$/ },
  { method: "GET", pattern: /^ai\/fast-table-import$/ },
  { method: "PUT", pattern: /^ai\/fast-table-import$/ },
  { method: "GET", pattern: /^data-quality\/report$/ },
  { method: "POST", pattern: /^data-quality\/check$/ },
];

/** Paths whose POST body is forwarded as multipart/form-data instead of JSON. */
const MULTIPART = new RegExp(
  `^(documents|mail/messages/${ID}/attachments/upload|letting/flow-import/preview|handover/protocols/${ID}/documents|imports/immoware24/lists/(objektdaten|kontakte|zuordnung|adressen)|imports/immoware24/vollimport(/vorpruefung)?|imports/migration/ledgers/${ID}/opening-balances/import|objektakte/imports(/${ID}/ocr-cache)?|letting/listings/${ID}/images|metering/assignments-import/(preview|apply)|metering/connections/${ID}/heiwako-import/preview)$`,
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
  } else if (method === "DELETE") {
    // GAG-26: DELETE /documents/{id}/hold carries the reason; forwarded only when present.
    const text = await request.text();
    if (text) {
      body = text;
      headers.set("content-type", "application/json");
    }
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
  for (const name of [
    "content-type",
    "etag",
    "content-disposition",
    "x-total-count",
    "x-page",
    "x-page-size",
  ]) {
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
