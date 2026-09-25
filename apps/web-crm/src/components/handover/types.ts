/** Übergabeprotokoll (M30): shapes of the /api/v1/handover responses used by the screens. */

export type Kind = "rental" | "sale" | "general";
export type Status =
  | "draft"
  | "in_progress"
  | "signature_pending"
  | "completed"
  | "sent"
  | "archived"
  | "cancelled";

export type Protocol = {
  id: string;
  number: string;
  version: number;
  parent_id: string | null;
  change_reason: string | null;
  kind: Kind;
  status: Status;
  current_step: string;
  property_id: string | null;
  unit_id: string | null;
  street: string | null;
  house_number: string | null;
  postal_code: string | null;
  city: string | null;
  object_label: string | null;
  building: string | null;
  floor: string | null;
  unit_number: string | null;
  unit_label: string | null;
  unit_position: string | null;
  handover_date: string | null;
  handover_start: string | null;
  handover_end: string | null;
  hide_time_information: boolean;
  handover_location: string | null;
  ticket_number: string | null;
  reference_number: string | null;
  management_number: string | null;
  rental_contract_number: string | null;
  internal_contact: string | null;
  internal_note: string | null;
  general_note: string | null;
  deposit_amount: string | null;
  deposit_account_holder: string | null;
  deposit_iban: string | null;
  deposit_bic: string | null;
  deposit_bank_name: string | null;
  deposit_note: string | null;
  deposit_iban_verified: boolean;
  deposit_separate_statement: boolean;
  completed_at: string | null;
  archived_at: string | null;
  pdf_document_id: string | null;
  locked: boolean;
  finalized: boolean;
  address: string;
  participants_summary?: string;
};

export type Item = Record<string, string | number | boolean | null> & {
  id: string;
};

export type Doc = {
  id: string;
  title: string;
  filename: string;
  mime_type: string;
  size: number;
  kind: "photo" | "attachment" | "signature" | "pdf";
  section: string | null;
  item_id: string | null;
  created_at: string;
};

export type Signature = {
  id: string;
  participant_id: string | null;
  signer_name: string | null;
  signer_role: string | null;
  sha256: string;
  signed_at: string;
  signed_location: string | null;
  document_id: string;
};

export type Version = {
  id: string;
  version: number;
  status: Status;
  completed_at: string | null;
  change_reason: string | null;
};

export type Full = Protocol & {
  participants: Item[];
  meters: Item[];
  rooms: Item[];
  defects: Item[];
  keys: Item[];
  items: Item[];
  notes: Item[];
  signatures: Signature[];
  documents: Doc[];
  hints: string[];
  versions: Version[];
};

export const SECTIONS = [
  "participants",
  "meters",
  "rooms",
  "defects",
  "keys",
  "items",
  "notes",
] as const;
export type Section = (typeof SECTIONS)[number];

export const ROLES = [
  "moving_out",
  "moving_in",
  "seller",
  "buyer",
  "handing_over",
  "taking_over",
  "management",
  "broker",
  "caretaker",
  "proxy",
  "witness",
  "relative",
  "expert",
  "craftsman",
  "other",
] as const;

/** Main roles per protocol kind: [out role, in role]. */
export function mainRoles(kind: Kind): [string, string] {
  if (kind === "sale") return ["seller", "buyer"];
  if (kind === "general") return ["handing_over", "taking_over"];
  return ["moving_out", "moving_in"];
}

/** Field definitions per section: name, input type and optional select options. */
export type FieldDef = {
  name: string;
  type:
    | "text"
    | "textarea"
    | "number"
    | "date"
    | "time"
    | "select"
    | "checkbox"
    | "decimal";
  options?: readonly string[];
  wide?: boolean;
};

export const FIELDS: Record<Section, FieldDef[]> = {
  participants: [
    { name: "role", type: "select", options: ROLES },
    { name: "salutation", type: "text" },
    { name: "first_name", type: "text" },
    { name: "last_name", type: "text" },
    { name: "company", type: "text" },
    { name: "street", type: "text" },
    { name: "house_number", type: "text" },
    { name: "postal_code", type: "text" },
    { name: "city", type: "text" },
    { name: "email", type: "text" },
    { name: "phone", type: "text" },
    { name: "comment", type: "textarea", wide: true },
  ],
  meters: [
    {
      name: "meter_type",
      type: "select",
      options: [
        "electricity",
        "gas",
        "water",
        "cold_water",
        "hot_water",
        "heating",
        "heat_quantity",
        "common_electricity",
        "sub_meter",
        "photovoltaic",
        "other",
      ],
    },
    { name: "custom_type", type: "text" },
    { name: "number", type: "text" },
    { name: "value", type: "decimal" },
    {
      name: "unit",
      type: "select",
      options: ["kWh", "m³", "MWh", "Liter", "Einheiten"],
    },
    { name: "location", type: "text" },
    { name: "read_on", type: "date" },
    { name: "read_at", type: "time" },
    { name: "comment", type: "textarea", wide: true },
  ],
  rooms: [
    { name: "name", type: "text" },
    { name: "room_type", type: "text" },
    {
      name: "condition",
      type: "select",
      options: [
        "ok",
        "defective",
        "not_checked",
        "not_accessible",
        "not_included",
      ],
    },
    { name: "comment", type: "textarea", wide: true },
  ],
  defects: [
    { name: "room_id", type: "select", options: [] },
    { name: "category", type: "text" },
    { name: "title", type: "text" },
    { name: "location", type: "text" },
    {
      name: "priority",
      type: "select",
      options: ["info", "low", "medium", "high", "urgent"],
    },
    {
      name: "defect_status",
      type: "select",
      options: ["pre_existing", "new", "acknowledged", "rejected", "unclear"],
    },
    { name: "responsibility", type: "text" },
    { name: "description", type: "textarea", wide: true },
  ],
  keys: [
    { name: "key_type", type: "text" },
    { name: "custom_name", type: "text" },
    { name: "quantity", type: "number" },
    { name: "key_number", type: "text" },
    {
      name: "status",
      type: "select",
      options: ["handed_over", "not_handed_over", "to_follow"],
    },
    { name: "comment", type: "textarea", wide: true },
  ],
  items: [
    { name: "name", type: "text" },
    { name: "item_type", type: "text" },
    { name: "quantity", type: "number" },
    { name: "condition", type: "text" },
    { name: "comment", type: "textarea", wide: true },
  ],
  notes: [
    {
      name: "category",
      type: "select",
      options: [
        "agreement",
        "hint",
        "defect",
        "open_task",
        "follow_up",
        "payment",
        "other",
      ],
    },
    { name: "text", type: "textarea", wide: true },
    { name: "responsible_party", type: "text" },
    { name: "due_date", type: "date" },
    { name: "status", type: "text" },
    { name: "is_internal", type: "checkbox" },
  ],
};

/** Sections that carry photos. */
export const PHOTO_SECTIONS: Section[] = [
  "meters",
  "rooms",
  "defects",
  "items",
];

export function itemTitle(
  section: Section,
  item: Item,
  tRole: (role: string) => string,
): string {
  const s = (k: string) => (item[k] == null ? "" : String(item[k]));
  switch (section) {
    case "participants":
      return [
        tRole(s("role")),
        [s("first_name"), s("last_name")].filter(Boolean).join(" ") ||
          s("company"),
      ]
        .filter(Boolean)
        .join(": ");
    case "meters":
      return [
        s("custom_type") || s("meter_type"),
        s("number") && `Nr. ${s("number")}`,
        s("value") && `${s("value")} ${s("unit")}`,
      ]
        .filter(Boolean)
        .join(", ");
    case "rooms":
      return s("name") || s("room_type") || "Raum";
    case "defects":
      return [s("category"), s("title")].filter(Boolean).join(": ") || "Mangel";
    case "keys":
      return (
        [
          s("custom_name") || s("key_type"),
          s("quantity") && `Anzahl ${s("quantity")}`,
        ]
          .filter(Boolean)
          .join(", ") || "Schlüssel"
      );
    case "items":
      return s("name") || s("item_type") || "Gegenstand";
    case "notes":
      return (s("text") || "Bemerkung").slice(0, 80);
  }
}
