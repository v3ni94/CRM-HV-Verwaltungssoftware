"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type Assignee = { id: string; user_id: string; primary: boolean; reason: string; created_at: string };
type Assignable = { user_id: string; display_name: string };

/** Zuständige eines Tickets (GAL-305, M19): mehrere Bearbeiter je Ticket setzen und entfernen.
 *  Der Hauptzuständige (Zuweisung) bleibt über die Ticketbearbeitung gesteuert; hier kommen
 *  weitere Zuständige dazu. Schreiben braucht tickets:update, die API prüft es. */
export function TicketAssignees({ ticketId, canUpdate }: { ticketId: string; canUpdate: boolean }) {
  const t = useTranslations("TicketAssignees");
  const [rows, setRows] = useState<Assignee[] | null>(null);
  const [users, setUsers] = useState<Assignable[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { busy, guard } = useBusy();

  const load = useCallback(async () => {
    const res = await bff<Assignee[]>(`/api/bff/tickets/${ticketId}/assignees`);
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setError(res.message);
    }
  }, [ticketId]);

  useEffect(() => {
    void load();
    void (async () => {
      const res = await bff<Assignable[]>("/api/bff/workspace/assignable-users");
      if (res.ok && Array.isArray(res.data)) setUsers(res.data);
    })();
  }, [load]);

  const nameOf = (id: string) => users.find((u) => u.user_id === id)?.display_name ?? t("unknownUser");
  const free = users.filter((u) => !(rows ?? []).some((r) => r.user_id === u.user_id));

  const add = guard(async () => {
    if (!selected) return;
    setError(null);
    const res = await bff<Assignee>(`/api/bff/tickets/${ticketId}/assignees`, {
      method: "POST",
      body: JSON.stringify({ user_id: selected, reason: "manuell", primary: false }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSelected("");
    await load();
  });

  const remove = guard(async (row: Assignee) => {
    setError(null);
    const res = await bff<unknown>(`/api/bff/tickets/${ticketId}/assignees/${row.user_id}`, { method: "DELETE" });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await load();
  });

  return (
    <section className="flex flex-col gap-2" data-testid="ticket-assignees">
      <h3 className="text-sm font-medium">{t("title")}</h3>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2">
              <span>{nameOf(r.user_id)}</span>
              {r.primary ? <span className={ui.badge}>{t("primary")}</span> : null}
              <span className="text-xs text-muted">{r.reason}</span>
              {canUpdate ? (
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void remove(r)}>
                  {t("remove")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canUpdate ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("add")}</span>
            <select className={ui.input} value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">{t("choose")}</option>
              {free.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.display_name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className={ui.buttonSm} disabled={busy || !selected} onClick={() => void add()}>
            {t("addButton")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
