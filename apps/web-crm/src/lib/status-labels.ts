/**
 * German plain text labels for domain statuses (operator decision 27.09.2026, design
 * proposal 7). One place per domain so lists, detail pages and the command palette show the
 * same wording. Colour is only a second carrier of meaning: every status has an icon and a
 * text, an optional explanation says what the status means for the next step.
 *
 * Labels are German by rule 10 (UI text); no dashes as sentence punctuation.
 */
export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";
export type StatusIcon = "dot" | "clock" | "check" | "warning" | "cross" | "lock" | "pen" | "send";

export type StatusDescriptor = {
  label: string;
  tone: StatusTone;
  icon: StatusIcon;
  /** Plain text explanation shown in the popover of the chip. */
  explanation?: string;
};

export type StatusDomain =
  | "ticket"
  | "ticketPriority"
  | "mail"
  | "dunningRun"
  | "dunningCase"
  | "directDebitRun"
  | "gate"
  | "meteringAssignment"
  | "property"
  | "mailSync";

const TICKET: Record<string, StatusDescriptor> = {
  new: { label: "Neu", tone: "info", icon: "dot", explanation: "Noch nicht zugeordnet oder bearbeitet." },
  in_progress: { label: "In Bearbeitung", tone: "warning", icon: "pen", explanation: "Ein Bearbeiter arbeitet an diesem Ticket." },
  waiting: { label: "Wartet", tone: "neutral", icon: "clock", explanation: "Wartet auf eine Rückmeldung von außen." },
  done: { label: "Erledigt", tone: "success", icon: "check" },
  closed: { label: "Geschlossen", tone: "neutral", icon: "check" },
  rejected: { label: "Abgelehnt", tone: "danger", icon: "cross" },
};

const TICKET_PRIORITY: Record<string, StatusDescriptor> = {
  low: { label: "Niedrig", tone: "neutral", icon: "dot" },
  normal: { label: "Normal", tone: "neutral", icon: "dot" },
  high: { label: "Hoch", tone: "warning", icon: "warning" },
  urgent: { label: "Dringend", tone: "danger", icon: "warning" },
  immediate: { label: "Sofort", tone: "danger", icon: "warning" },
};

const MAIL: Record<string, StatusDescriptor> = {
  new: { label: "Neu", tone: "info", icon: "dot" },
  assigned: { label: "Zugeordnet", tone: "info", icon: "pen" },
  done: { label: "Erledigt", tone: "success", icon: "check" },
  draft: { label: "Entwurf", tone: "neutral", icon: "pen", explanation: "Noch nicht zum Versand freigegeben." },
  pending: {
    label: "Wartet auf Freigabe",
    tone: "warning",
    icon: "clock",
    explanation: "Freigabe durch eine zweite Person nötig, bevor die Nachricht versendet wird.",
  },
  sending: { label: "Wird gesendet", tone: "info", icon: "send" },
  sent: { label: "Gesendet", tone: "success", icon: "send" },
};

const DUNNING_RUN: Record<string, StatusDescriptor> = {
  preview: {
    label: "Vorschau",
    tone: "warning",
    icon: "clock",
    explanation: "Vorschlag ohne Wirkung nach außen. Erst nach Freigabe werden Mahnungen erzeugt.",
  },
  approved: { label: "Freigegeben", tone: "success", icon: "check" },
};

const DUNNING_CASE: Record<string, StatusDescriptor> = {
  proposed: { label: "Vorgeschlagen", tone: "warning", icon: "clock" },
  excluded: { label: "Ausgeschlossen", tone: "neutral", icon: "cross" },
  sent: { label: "Versandt", tone: "success", icon: "send" },
};

const DIRECT_DEBIT_RUN: Record<string, StatusDescriptor> = {
  draft: { label: "Entwurf", tone: "neutral", icon: "pen", explanation: "Noch nicht freigegeben." },
  approved: {
    label: "Wartet auf Freigabe",
    tone: "warning",
    icon: "clock",
    explanation: "G2 geschlossen: Freigabe durch zweite Person nötig, bevor eine Datei erzeugt wird.",
  },
  file_generated: {
    label: "Datei erzeugt",
    tone: "warning",
    icon: "lock",
    explanation: "Die Datei liegt als Dokument vor. Der Download ist bis zur Freigabestufe G2 gesperrt.",
  },
  exported: { label: "Exportiert", tone: "success", icon: "check" },
  submitted: { label: "Eingereicht", tone: "info", icon: "send" },
  accepted_by_bank: { label: "Von Bank angenommen", tone: "success", icon: "check" },
  executed: { label: "Ausgeführt", tone: "success", icon: "check" },
  partially_executed: { label: "Teilweise ausgeführt", tone: "warning", icon: "warning" },
  rejected: { label: "Abgelehnt", tone: "danger", icon: "cross" },
  returned: { label: "Zurückgegeben", tone: "danger", icon: "cross" },
  cancelled: { label: "Verworfen", tone: "neutral", icon: "cross" },
};

const GATE: Record<string, StatusDescriptor> = {
  open: { label: "Freigegeben", tone: "success", icon: "check", explanation: "Die Freigabestufe ist für diesen Mandanten geöffnet." },
  closed: {
    label: "Geschlossen",
    tone: "neutral",
    icon: "lock",
    explanation: "Produktive Nutzung dieses Bereichs ist gesperrt, bis die Freigabestufe geöffnet wird.",
  },
};

const METERING_ASSIGNMENT: Record<string, StatusDescriptor> = {
  open: { label: "Offen", tone: "neutral", icon: "dot" },
  proposed: { label: "Vorgeschlagen", tone: "warning", icon: "clock", explanation: "Vorschlag, noch nicht bestätigt." },
  confirmed: { label: "Bestätigt", tone: "success", icon: "check" },
  conflict: { label: "Konflikt", tone: "danger", icon: "warning", explanation: "Mehrere Zuordnungen widersprechen sich und müssen geprüft werden." },
  archived: { label: "Archiviert", tone: "neutral", icon: "cross" },
};

const PROPERTY: Record<string, StatusDescriptor> = {
  onboarding: { label: "In Aufnahme", tone: "warning", icon: "clock", explanation: "Das Objekt wird noch angelegt und ist nicht aktiviert." },
  active: { label: "Aktiv", tone: "success", icon: "check" },
  terminated: { label: "Deaktiviert", tone: "neutral", icon: "lock", explanation: "Das Verwaltungsverhältnis ist beendet. Das Objekt bleibt mit allen Daten erhalten, wird aber nicht mehr bearbeitet." },
};

/** Abgleichstand einer Mail mit Gmail (Rückkanal M20-08); `aus` wird nicht gerendert. */
const MAIL_SYNC: Record<string, StatusDescriptor> = {
  synchron: { label: "Synchron", tone: "neutral", icon: "check", explanation: "Plattform und Gmail Posteingang stimmen überein." },
  abweichend: {
    label: "Abweichend",
    tone: "warning",
    icon: "warning",
    explanation: "Mindestens eine Postfachkopie steht in Gmail anders als der Status in der Plattform.",
  },
  ausstehend: { label: "Ausstehend", tone: "info", icon: "clock", explanation: "Eine Archivierung, Wiederherstellung oder Beruhigungsfrist läuft noch." },
  geloescht: { label: "In Gmail gelöscht", tone: "neutral", icon: "cross", explanation: "Die Nachricht wurde in Gmail endgültig gelöscht, das Original bleibt gespeichert." },
  unbekannt: { label: "Unbekannt", tone: "neutral", icon: "dot", explanation: "Keine Gmail Kopie bekannt." },
};

export const STATUS_LABELS: Record<StatusDomain, Record<string, StatusDescriptor>> = {
  ticket: TICKET,
  ticketPriority: TICKET_PRIORITY,
  mail: MAIL,
  dunningRun: DUNNING_RUN,
  dunningCase: DUNNING_CASE,
  directDebitRun: DIRECT_DEBIT_RUN,
  gate: GATE,
  meteringAssignment: METERING_ASSIGNMENT,
  property: PROPERTY,
  mailSync: MAIL_SYNC,
};

/** Descriptor for a domain status; unknown values fall back to a neutral chip with the raw value. */
export function statusDescriptor(domain: StatusDomain, status: string | null | undefined): StatusDescriptor {
  const key = String(status ?? "");
  return STATUS_LABELS[domain][key] ?? { label: key || "Unbekannt", tone: "neutral", icon: "dot" };
}
