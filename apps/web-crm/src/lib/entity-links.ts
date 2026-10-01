/**
 * Jump paths between entities (Ergänzung, section 5). One place for every route the CRM
 * uses to open a record, shared by the global search, the EntityLinksBar and lists.
 */
export type EntityType =
  | "contact"
  | "property"
  | "building"
  | "unit"
  | "contract"
  | "document"
  | "ticket"
  | "posting"
  | "invoice"
  | "ledger"
  | "meeting"
  | "resolution";

/**
 * Route of a record, or null when the type is unknown or the context is missing.
 * `parentId` is the property of a building or the ledger of a posting.
 */
export function entityHref(type: string, id: string, parentId?: string | null): string | null {
  switch (type) {
    case "contact":
      return `/kontakte/${id}`;
    case "property":
      return `/objekte/${id}`;
    case "building":
      return parentId ? `/objekte/${parentId}/gebaeude/${id}` : null;
    case "unit":
      return `/vermietung/einheit/${id}`;
    case "contract":
      return `/vertraege/${id}`;
    case "document":
      return `/dokumente/${id}`;
    case "ticket":
      return `/tickets/${id}`;
    case "posting":
      return parentId ? `/buchhaltung/${parentId}` : null;
    case "invoice":
      return `/rechnungen/${id}`;
    case "ledger":
      return `/buchhaltung/${id}`;
    case "meeting":
      return `/weg/versammlungen/${id}`;
    case "resolution":
      return `/weg/beschluesse/${id}`;
    default:
      return null;
  }
}
