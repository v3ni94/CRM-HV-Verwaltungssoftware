"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { PRIORITIES } from "@/components/tickets/TicketForms";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Assignable = { user_id: string; display_name: string };
type Team = { id: string; name: string };

/** Shared partial success report of the bulk endpoints (S12-05). */
export type BulkReport = {
  total: number;
  succeeded: number;
  failed: number;
  items: { id: string; ok: boolean; code: string | null; detail: string | null }[];
};

/** Bulk assignment, team and priority in the ticket list (M9-04, S12-05): sets the primary
 *  assignee, team and/or priority of all selected tickets through POST /tickets/bulk. Each ticket
 *  runs on its own; the partial success report (succeeded, failed per ticket) goes to the
 *  caller. An assignee without membership or an unknown team refuses the whole call. The user
 *  and team lists are loaded when the user opens the panel. Needs tickets:update (checked by
 *  the API). */
export function TicketBulkAssign({
  ids,
  disabled,
  onDone,
}: {
  ids: string[];
  disabled: boolean;
  onDone: (report: BulkReport) => void;
}) {
  const t = useTranslations("TicketBulkAssign");
  const tp = useTranslations("Tickets");
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState<Assignable[] | null>(null);
  const [assignee, setAssignee] = useState("");
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamId, setTeamId] = useState("");
  const [priority, setPriority] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openPanel() {
    setOpen(true);
    setError(null);
    if (users !== null) return;
    const teamRes = await bff<Team[]>("/api/bff/teams");
    if (teamRes.ok && Array.isArray(teamRes.data)) setTeams(teamRes.data);
    const res = await bff<Assignable[]>("/api/bff/workspace/assignable-users");
    if (res.ok && Array.isArray(res.data)) setUsers(res.data);
    else {
      setUsers([]);
      if (!res.ok) setError(res.message);
    }
  }

  async function apply() {
    if (!assignee && !teamId && !priority) return;
    setBusy(true);
    setError(null);
    const res = await bff<BulkReport>("/api/bff/tickets/bulk", {
      method: "POST",
      body: JSON.stringify({
        ids,
        ...(assignee ? { assignee_user_id: assignee } : {}),
        ...(teamId ? { team_id: teamId } : {}),
        ...(priority ? { priority } : {}),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setOpen(false);
    setAssignee("");
    setTeamId("");
    setPriority("");
    onDone(res.data);
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
      <select className={ui.input} value={teamId} aria-label={t("team")} disabled={busy} onChange={(e) => setTeamId(e.target.value)}>
        <option value="">{t("chooseTeam")}</option>
        {teams.map((tm) => (
          <option key={tm.id} value={tm.id}>
            {tm.name}
          </option>
        ))}
      </select>
      <select className={ui.input} value={priority} aria-label={t("priority")} disabled={busy} onChange={(e) => setPriority(e.target.value)}>
        <option value="">{t("choosePriority")}</option>
        {PRIORITIES.map((p) => (
          <option key={p} value={p}>
            {tp(`priorities.${p}`)}
          </option>
        ))}
      </select>
      <button type="button" className={ui.primary} disabled={busy || disabled || (!assignee && !teamId && !priority)} onClick={() => void apply()}>
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
