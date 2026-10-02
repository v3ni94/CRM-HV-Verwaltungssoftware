"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type EvidenceItem = {
  code: string;
  label: string;
  status: "open" | "done";
  done: boolean;
  document_id: string | null;
  note: string | null;
  decided_at: string | null;
};

export type EvidenceList = {
  tenant_id: string;
  items: EvidenceItem[];
  complete: boolean;
  missing: string[];
  gate_open: boolean;
};

type Tenant = { id: string; name: string; slug: string };

/** M27-02: G5 evidence checklist per tenant. Marking an item "done" needs a document of the
 *  tenant. The page never opens the gate: G5 is approved through the gate request by the
 *  superadmin, and only when every item is done. */
export function G5Evidence({ tenants, initial }: { tenants: Tenant[]; initial: EvidenceList | null }) {
  const t = useTranslations("PlatformG5");
  const tCommon = useTranslations("Common");
  const [tenantId, setTenantId] = useState(initial?.tenant_id ?? tenants[0]?.id ?? "");
  const [list, setList] = useState<EvidenceList | null>(initial);
  const [drafts, setDrafts] = useState<Record<string, { document_id: string; note: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load(id: string) {
    setTenantId(id);
    setError(null);
    const res = await bff<EvidenceList>(`/api/bff/platform/tenants/${id}/g5-evidence`);
    if (res.ok) setList(res.data);
    else setError(res.message);
  }

  async function save(item: EvidenceItem, status: "open" | "done") {
    if (busy) return;
    setBusy(true);
    setError(null);
    const draft = drafts[item.code] ?? { document_id: item.document_id ?? "", note: item.note ?? "" };
    const res = await bff<EvidenceItem>(`/api/bff/platform/tenants/${tenantId}/g5-evidence/${item.code}`, {
      method: "PUT",
      body: JSON.stringify({
        status,
        document_id: draft.document_id.trim() || null,
        note: draft.note.trim() || null,
      }),
    });
    if (!res.ok) {
      setError(res.message);
      setBusy(false);
      return;
    }
    await load(tenantId);
    setBusy(false);
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
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {list ? (
        <>
          <p className={list.gate_open ? ui.success : ui.notice}>
            {list.gate_open ? t("gateOpen") : list.complete ? t("completeClosed") : t("incomplete", { count: list.missing.length })}
          </p>
          <ul className={ui.sectionGap}>
            {list.items.length === 0 ? <li className="text-sm text-muted">{tCommon("emptyList")}</li> : null}
            {list.items.map((item) => {
              const draft = drafts[item.code] ?? { document_id: item.document_id ?? "", note: item.note ?? "" };
              return (
                <li key={item.code} className={`${ui.card} flex flex-col gap-2`}>
                  <div className="flex items-center gap-2">
                    <span className={item.done ? ui.badgeSuccess : ui.badgeWarning}>{item.done ? t("done") : t("openStatus")}</span>
                    <span className="font-medium">{item.label}</span>
                  </div>
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("documentId")}</span>
                    <input
                      className={ui.input}
                      value={draft.document_id}
                      onChange={(e) => setDrafts({ ...drafts, [item.code]: { ...draft, document_id: e.target.value } })}
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("note")}</span>
                    <input
                      className={ui.input}
                      value={draft.note}
                      onChange={(e) => setDrafts({ ...drafts, [item.code]: { ...draft, note: e.target.value } })}
                    />
                  </label>
                  <div className={ui.formActions}>
                    <button type="button" className={ui.primary} disabled={busy} onClick={() => void save(item, "done")}>
                      {t("markDone")}
                    </button>
                    <button type="button" className={ui.secondary} disabled={busy} onClick={() => void save(item, "open")}>
                      {t("markOpen")}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className={ui.help}>{t("releaseHint")}</p>
        </>
      ) : (
        <p className={ui.help}>{t("noData")}</p>
      )}
    </div>
  );
}
