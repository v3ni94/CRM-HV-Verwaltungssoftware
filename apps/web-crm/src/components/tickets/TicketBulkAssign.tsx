"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Assignable = { user_id: string; display_name: string };

/** Bulk assignment in the ticket list (M9-04): sets the primary assignee of all selected tickets
 *  through POST /workspace/bulk (action tickets.assign). All or nothing: the API refuses the
 *  whole action for an unknown ticket, a merged ticket or an assignee without membership, and
 *  each assignment writes history, notification and event like a single assignment. The user
 *  list is loaded when the user opens the assignment, not with the list. Needs tickets:update
 *  (checked by the API). */
export function TicketBulkAssign({
  ids,
  disabled,
  onDone,
}: {
  ids: string[];
  disabled: boolean;
  onDone: (changed: number) => void;
}) {
  const t = useTranslations("TicketBulkAssign");
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState<Assignable[] | null>(null);
  const [assignee, setAssignee] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openPanel() {
    setOpen(true);
    setError(null);
    if (users !== null) return;
    const res = await bff<Assignable[]>("/api/bff/workspace/assignable-users");
    if (res.ok && Array.isArray(res.data)) setUsers(res.data);
    else {
      setUsers([]);
      if (!res.ok) setError(res.message);
    }
  }

  async function apply() {
    if (!assignee) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ changed: number }>("/api/bff/workspace/bulk", {
      method: "POST",
      body: JSON.stringify({ action: "tickets.assign", ids, assignee_user_id: assignee }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setOpen(false);
    setAssignee("");
    onDone(res.data?.changed ?? 0);
  }

  if (!open) {
    return (
      <button type="button" className={ui.secondary} disabled={disabled} onClick={() => void openPanel()}>
        {t("open")}
      </button>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-2" data-testid="bulk-assign">
      <select
        className={ui.input}
        value={assignee}
        aria-label={t("assignee")}
        disabled={users === null || busy}
        onChange={(e) => setAssignee(e.target.value)}
      >
        <option value="">{users === null ? t("loading") : t("choose")}</option>
        {(users ?? []).map((u) => (
          <option key={u.user_id} value={u.user_id}>
            {u.display_name}
          </option>
        ))}
      </select>
      <button type="button" className={ui.primary} disabled={busy || disabled || !assignee} onClick={() => void apply()}>
        {t("apply", { count: ids.length })}
      </button>
      <button type="button" className={ui.secondary} disabled={busy} onClick={() => setOpen(false)}>
        {t("cancel")}
      </button>
      {error ? (
        <span role="alert" className="text-xs text-danger-fg">
          {error}
        </span>
      ) : null}
    </span>
  );
}
