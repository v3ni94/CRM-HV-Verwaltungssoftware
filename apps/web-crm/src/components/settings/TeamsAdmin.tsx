"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type TeamRow = { id: string; name: string; member_user_ids: string[] };
export type TeamMemberOption = { id: string; label: string };

/** Team management for tickets (M19-02, 6.6 team): list, create, rename, change members,
 *  delete. The API refuses deleting a team that is used by tickets or templates; the message is
 *  shown. Reading needs tickets:read, every change tickets:approve (checked by the API). */
export function TeamsAdmin({ members, canManage }: { members: TeamMemberOption[]; canManage: boolean }) {
  const t = useTranslations("TeamsAdmin");
  const [teams, setTeams] = useState<TeamRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  const load = useCallback(async () => {
    const res = await bff<TeamRow[]>("/api/bff/teams");
    if (res.ok) setTeams(res.data ?? []);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const label = (id: string) => members.find((m) => m.id === id)?.label ?? id;

  function startCreate() {
    setCreating(true);
    setEditing(null);
    setName("");
    setSelected([]);
    setError(null);
  }

  function startEdit(team: TeamRow) {
    setEditing(team.id);
    setCreating(false);
    setName(team.name);
    setSelected([...team.member_user_ids]);
    setError(null);
  }

  function cancel() {
    setCreating(false);
    setEditing(null);
  }

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function save() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError(t("nameRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = creating
      ? await bff("/api/bff/teams", { method: "POST", body: JSON.stringify({ name: trimmed, member_user_ids: selected }) })
      : await bff(`/api/bff/teams/${editing}`, {
          method: "PATCH",
          body: JSON.stringify({ name: trimmed, member_user_ids: selected }),
        });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    cancel();
    await load();
  }

  async function remove(team: TeamRow) {
    if (!window.confirm(t("deleteConfirm", { name: team.name }))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/teams/${team.id}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await load();
  }

  const form =
    creating || editing ? (
      <form
        className="flex flex-col gap-3 rounded-md border border-border p-3"
        aria-label={creating ? t("newTitle") : t("editTitle")}
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("name")}</span>
          <input className={ui.input} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="flex flex-col gap-1">
          <legend className={ui.label}>{t("members")}</legend>
          {members.length === 0 ? <p className="text-sm text-muted">{t("noMembers")}</p> : null}
          {members.map((m) => (
            <label key={m.id} className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" checked={selected.includes(m.id)} onChange={() => toggle(m.id)} />
              {m.label}
            </label>
          ))}
        </fieldset>
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("save")}
          </button>
          <button type="button" className={ui.secondary} onClick={cancel}>
            {t("cancel")}
          </button>
        </div>
      </form>
    ) : null;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="teams-admin-title" data-testid="teams-admin">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="teams-admin-title" className={ui.h2}>
          {t("title")}
        </h2>
        {canManage && !creating ? (
          <button type="button" className={`${ui.buttonSm} ml-auto`} onClick={startCreate}>
            {t("new")}
          </button>
        ) : null}
      </div>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {creating ? form : null}
      {teams === null ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : teams.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {teams.map((team) =>
            editing === team.id ? (
              <li key={team.id}>{form}</li>
            ) : (
              <li key={team.id} className="flex flex-wrap items-center gap-2 border-b border-border py-2 text-sm" data-testid="team-row">
                <span className="font-medium">{team.name}</span>
                <span className="text-xs text-muted">
                  {team.member_user_ids.length === 0
                    ? t("noMembersAssigned")
                    : team.member_user_ids.map(label).join(", ")}
                </span>
                {canManage ? (
                  <span className="ml-auto flex gap-2">
                    <button type="button" className={ui.buttonSm} disabled={busy} aria-label={t("editFor", { name: team.name })} onClick={() => startEdit(team)}>
                      {t("edit")}
                    </button>
                    <button type="button" className={ui.buttonSm} disabled={busy} aria-label={t("deleteFor", { name: team.name })} onClick={() => void remove(team)}>
                      {t("delete")}
                    </button>
                  </span>
                ) : null}
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  );
}
