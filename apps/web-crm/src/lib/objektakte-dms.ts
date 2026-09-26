/** M29 Stufe 4: shapes of the CRM endpoints under /api/v1/integrations/objektakte (the API
 *  passes the objektakte contract fields through and adds the CRM references). */

export type DmsStatus = {
  configured: boolean;
  reason: "not_configured" | "other_tenant" | null;
  webhook_configured: boolean;
};

export type DmsCompleteness = { required: number; present: number; missing: number; percent: number };

export type DmsObject = {
  number: string;
  name: string;
  archived: boolean;
  takeover_status: string;
  open_review_cases: number;
  completeness: DmsCompleteness;
  drive_folder_id: string | null;
  drive_folder_url: string | null;
  updated_at: string | null;
  property_id: string | null;
};

export type DmsMissingDocument = { category: string; subfolder: string | null; label: string };

export type DmsObjectDetail = DmsObject & {
  address?: { street: string | null; house_number: string | null; zip: string | null; city: string | null };
  missing_documents?: DmsMissingDocument[];
  open_cases_by_type?: Record<string, number>;
  crm_document_count: number;
};

export type DmsDocument = {
  id: number;
  title: string;
  doc_type: string | null;
  category: string | null;
  subfolder: string | null;
  status: string;
  drive_file_id: string | null;
  drive_url: string | null;
  sha256: string;
  filed_at: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  crm_document_id: string | null;
};

export type DmsDocumentPage = { count: number; page: number; page_size: number; results: DmsDocument[] };

export type DmsLinkResult = {
  object_number: string;
  property_id: string | null;
  total: number;
  created: number;
  linked: number;
  updated: number;
  unchanged: number;
  invalid: number;
};

export type PersonKind = "owners" | "tenants";

export type ProposalRowStatus = "unchanged" | "new" | "conflict" | "unit_unknown" | "no_unit" | "crm_only";

export type ProposalRow = {
  source_id: string | null;
  display_name: string;
  unit_labels: string[];
  share?: string | null;
  lease_start?: string | null;
  lease_end?: string | null;
  status: ProposalRowStatus;
  units: { unit_label: string; unit_id?: string; status: string; crm_names?: string[] }[];
};

export type PersonProposal = {
  id: string;
  property_id: string;
  object_number: string;
  kind: PersonKind;
  status: "tested" | "approved" | "rejected";
  fetched_at: string;
  decided_at: string | null;
  decision_note: string | null;
  summary: { reference_date: string; remote_total: number; crm_total: number; counts: Record<ProposalRowStatus, number> };
  rows: ProposalRow[];
  writes_master_data: false;
};

export const PROPOSAL_ROW_STATUSES: ProposalRowStatus[] = ["unchanged", "conflict", "new", "unit_unknown", "no_unit", "crm_only"];

export function dmsBase(number: string): string {
  return `/api/bff/integrations/objektakte/objects/${encodeURIComponent(number)}`;
}
