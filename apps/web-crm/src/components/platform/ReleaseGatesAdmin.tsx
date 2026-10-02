"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type GateState = {
  gate: string;
  label: string;
  open: boolean;
  scopes: string[];
  partially_open: boolean;
};

export type GateRequest = {
  id: string;
  gate: string;
  scope: string;
  evidence: string;
  status: string;
  requested_by: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_comment: string | null;
  opened_by: string | null;
  opened_at: string | null;
  revoked_by: string | null;
  revoked_at: string | null;
  revoke_comment: string | null;
  evidence_document_id: string | null;
  scope_property_ids: string[] | null;
  checklist: Record<string, string> | null;
};

export type GateOverview = { tenant_id: string; gates: GateState[]; requests: GateRequest[] };

export type GateChecklist = {
  gate: string;
  label: string;
  items: { code: string; label: string }[];
  functions: string[];
  evidence_document_required: boolean;
};

type Tenant = { id: string; name: string };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** GA14-04 (AB02): release gates per tenant for platform administrators. Requests and
 *  revocations act on the signed in tenant (tenant API), approvals and rejections on the
 *  selected tenant (platform API, second person). The API keeps every rule: four eyes,
 *  complete checklist and evidence document for G2 to G4, G5 only for the superadmin. */
export function ReleaseGatesAdmin({
  tenants,
  activeTenantId,
  initial,
  checklists,
}: {
  tenants: Tenant[];
  activeTenantId: string | null;
  initial: GateOverview | null;
  checklists: GateChecklist[];
}) {
  const t = useTranslations("PlatformGates");
  const [tenantId, setTenantId] = useState(initial?.tenant_id ?? tenants[0]?.id ?? "");
  const [overview, setOverview] = useState<GateOverview | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [gate, setGate] = useState("G2");
  const [scope, setScope] = useState("");
  const [evidence, setEvidence] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [properties, setProperties] = useState("");
  const [checks, setChecks] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const own = tenantId === activeTenantId;
  const checklist = checklists.find((c) => c.gate === gate);

  async function load(id: string) {
    setTenantId(id);
    setError(null);
    const res = await bff<GateOverview>(`/api/bff/platform/tenants/${id}/release-gates`);
    if (res.ok) setOverview(res.data);
    else setError(res.message);
  }

  async function act(url: string, body: Record<string, unknown>) {
    if (busy) return false;
    setBusy(true);
    setError(null);
    try {
      const res = await bff<GateRequest>(url, { method: "POST", body: JSON.stringify(body) });
      if (!res.ok) {
        setError(res.message);
        return false;
      }
      await load(tenantId);
      return true;
    } finally {
      setBusy(false);
    }
  }

  function decide(row: GateRequest, kind: "approve" | "reject" | "revoke") {
    const comment = comments[row.id]?.trim() || null;
    const url =
      kind === "revoke"
        ? `/api/bff/tenant/release-gates/requests/${row.id}/revoke`
        : `/api/bff/platform/tenants/${tenantId}/release-gates/requests/${row.id}/${kind}`;
    void act(url, { comment });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const ids = properties
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (ids.some((id) => !UUID_RE.test(id)) || (documentId.trim() && !UUID_RE.test(documentId.trim()))) {
      setError(t("invalidId"));
      return;
    }
    const confirmed = Object.fromEntries(Object.entries(checks).filter(([, v]) => v.trim()));
    const ok = await act("/api/bff/tenant/release-gates/requests", {
      gate,
      scope,
      evidence,
      evidence_document_id: documentId.trim() || null,
      scope_property_ids: ids.length ? ids : null,
      checklist: Object.keys(confirmed).length ? confirmed : null,
    });
    if (ok) {
      setScope("");
      setEvidence("");
      setDocumentId("");
      setProperties("");
      setChecks({});
    }
  }

  function stateLabel(g: GateState) {
    if (g.open) return t("stateOpen");
    if (g.partially_open) return t("statePartial");
    return t("stateClosed");
  }

  return (
    <div className={ui.sectionGap}>
      <label className="flex flex-col gap-1 sm:max-w-md">
        <span className={ui.label}>{t("tenant")}</span>
        <select className={ui.input} value={tenantId} onChange={(e) => void load(e.target.value)}>
          {tenants.map((tn) => (
            <option key={tn.id} value={tn.id}>
              {tn.name}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {overview ? (
        <>
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <caption className="sr-only">{t("gatesCaption")}</caption>
              <thead>
                <tr>
                  <th>{t("gate")}</th>
                  <th>{t("state")}</th>
                  <th>{t("scopes")}</th>
                </tr>
              </thead>
              <tbody>
                {overview.gates.map((g) => (
                  <tr key={g.gate}>
                    <td>
                      {g.gate} {g.label}
                    </td>
                    <td>{stateLabel(g)}</td>
                    <td>{g.scopes.join("; ") || t("none")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h2 className={ui.h2}>{t("requests")}</h2>
          {overview.requests.length === 0 ? <p>{t("noRequests")}</p> : null}
          {overview.requests.map((row) => (
            <article key={row.id} className={ui.card} aria-label={`${row.gate} ${row.scope}`}>
              <p>
                <strong>{row.gate}</strong> {row.scope} ({t(`status.${row.status}`)})
              </p>
              <dl className="grid gap-1 text-sm sm:grid-cols-2">
                <dt>{t("evidence")}</dt>
                <dd>{row.evidence}</dd>
                <dt>{t("evidenceDocument")}</dt>
                <dd>
                  {row.evidence_document_id ? (
                    <a className="underline" href={`/dokumente/${row.evidence_document_id}`}>
                      {row.evidence_document_id}
                    </a>
                  ) : (
                    t("none")
                  )}
                </dd>
                <dt>{t("openedBy")}</dt>
                <dd>{row.opened_by ? `${row.opened_by}, ${formatDateTime(row.opened_at)}` : t("none")}</dd>
                <dt>{t("revokedBy")}</dt>
                <dd>
                  {row.revoked_by
                    ? `${row.revoked_by}, ${formatDateTime(row.revoked_at)}${row.revoke_comment ? `: ${row.revoke_comment}` : ""}`
                    : t("none")}
                </dd>
                {row.scope_property_ids ? (
                  <>
                    <dt>{t("properties")}</dt>
                    <dd>{row.scope_property_ids.join(", ")}</dd>
                  </>
                ) : null}
              </dl>
              {row.status === "requested" || row.status === "approved" ? (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("comment")}</span>
                    <input
                      className={ui.input}
                      value={comments[row.id] ?? ""}
                      onChange={(e) => setComments({ ...comments, [row.id]: e.target.value })}
                    />
                  </label>
                  {row.status === "requested" ? (
                    <>
                      <button type="button" className={ui.primary} disabled={busy} onClick={() => decide(row, "approve")}>
                        {t("approve")}
                      </button>
                      <button type="button" className={ui.secondary} disabled={busy} onClick={() => decide(row, "reject")}>
                        {t("reject")}
                      </button>
                    </>
                  ) : null}
                  {own ? (
                    <button type="button" className={ui.secondary} disabled={busy} onClick={() => decide(row, "revoke")}>
                      {t("revoke")}
                    </button>
                  ) : null}
                </div>
              ) : null}
            </article>
          ))}
        </>
      ) : (
        <p>{t("noData")}</p>
      )}
      <h2 className={ui.h2}>{t("newRequest")}</h2>
      {own ? (
        <form className={ui.sectionGap} onSubmit={(e) => void submit(e)}>
          <label className="flex flex-col gap-1 sm:max-w-xs">
            <span className={ui.label}>{t("gate")}</span>
            <select className={ui.input} value={gate} onChange={(e) => setGate(e.target.value)}>
              {checklists.map((c) => (
                <option key={c.gate} value={c.gate}>
                  {c.gate} {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("scope")}</span>
            <textarea className={ui.input} value={scope} onChange={(e) => setScope(e.target.value)} required minLength={10} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("evidence")}</span>
            <input className={ui.input} value={evidence} onChange={(e) => setEvidence(e.target.value)} required minLength={5} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("evidenceDocumentId")}</span>
            <input className={ui.input} value={documentId} onChange={(e) => setDocumentId(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("propertyIds")}</span>
            <input className={ui.input} value={properties} onChange={(e) => setProperties(e.target.value)} />
          </label>
          {checklist && checklist.items.length > 0 ? (
            <fieldset className="flex flex-col gap-2">
              <legend className={ui.label}>{t("checklist")}</legend>
              {checklist.items.map((item) => (
                <label key={item.code} className="flex flex-col gap-1">
                  <span>{item.label}</span>
                  <input
                    className={ui.input}
                    aria-label={t("checkNote", { item: item.label })}
                    value={checks[item.code] ?? ""}
                    onChange={(e) => setChecks({ ...checks, [item.code]: e.target.value })}
                  />
                </label>
              ))}
            </fieldset>
          ) : (
            <p>{t("noChecklist")}</p>
          )}
          <div>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("submit")}
            </button>
          </div>
        </form>
      ) : (
        <p className={ui.notice}>{t("onlyOwnTenant")}</p>
      )}
    </div>
  );
}
