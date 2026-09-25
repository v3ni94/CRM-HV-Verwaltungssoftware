"use client";

import type { components } from "@mhvp/api-client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type Member = components["schemas"]["MemberOut"];
type Role = components["schemas"]["RoleOut"];

function StatusBadge({ status }: { status: string }) {
  const t = useTranslations("Members");
  return <StatusPill variant={status === "active" ? "success" : "warning"} label={t(`status.${status}`)} />;
}

function RolesEditor({ member, roles, onSaved }: { member: Member; roles: Role[]; onSaved: (roleCodes: string[]) => void }) {
  const t = useTranslations("Members");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(member.roles);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    const res = await bff<Member>(`/api/bff/tenant/members/${member.membership_id}/roles`, {
      method: "PUT",
      body: JSON.stringify({ role_codes: selected }),
    });
    setBusy(false);
    if (res.ok) {
      onSaved(selected);
      setOpen(false);
    } else {
      setError(res.message);
    }
  }

  if (!open) {
    return (
      <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
        {t("editRoles")}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-surface p-2">
      {roles.map((r) => (
        <label key={r.id} className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={selected.includes(r.code)}
            onChange={(e) =>
              setSelected((prev) => (e.target.checked ? [...prev, r.code] : prev.filter((c) => c !== r.code)))
            }
          />
          {r.name}
        </label>
      ))}
      {error ? <p className={ui.error}>{error}</p> : null}
      <div className="flex gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} disabled={busy} onClick={() => setOpen(false)}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}

function CompetencesEditor({
  member,
  catalogue,
  onSaved,
}: {
  member: Member;
  catalogue: { code: string; label: string }[];
  onSaved: (codes: string[]) => void;
}) {
  const t = useTranslations("Members");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(member.competences ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/tenant/members/${member.membership_id}/competences`, {
      method: "PUT",
      body: JSON.stringify({ competence_codes: selected }),
    });
    setBusy(false);
    if (res.ok) {
      onSaved(selected);
      setOpen(false);
    } else {
      setError(res.message);
    }
  }

  if (!open) {
    return (
      <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
        {t("editCompetences")}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-surface p-2">
      {catalogue.map((c) => (
        <label key={c.code} className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={selected.includes(c.code)}
            onChange={(e) =>
              setSelected((prev) => (e.target.checked ? [...prev, c.code] : prev.filter((x) => x !== c.code)))
            }
          />
          {c.label}
        </label>
      ))}
      {error ? <p className={ui.error}>{error}</p> : null}
      <div className="flex gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} disabled={busy} onClick={() => setOpen(false)}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}

function MobilePhoneEditor({ member, onSaved }: { member: Member; onSaved: (phone: string | null) => void }) {
  const t = useTranslations("Members");
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(member.mobile_phone ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    const phone = value.trim() || null;
    const res = await bff<null>(`/api/bff/tenant/members/${member.membership_id}/mobile-phone`, {
      method: "PUT",
      body: JSON.stringify({ mobile_phone: phone }),
    });
    setBusy(false);
    if (res.ok) {
      onSaved(phone);
      setOpen(false);
    } else {
      setError(res.message);
    }
  }

  if (!open) {
    return (
      <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
        {member.mobile_phone ? t("mobilePhoneShow", { phone: member.mobile_phone }) : t("editMobilePhone")}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-surface p-2">
      <label className="flex flex-col gap-1 text-xs">
        {t("mobilePhone")}
        <input
          type="tel"
          className={ui.input}
          maxLength={40}
          value={value}
          placeholder="+49 170 1234567"
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      <p className="text-xs text-muted">{t("mobilePhoneHint")}</p>
      {error ? <p className={ui.error}>{error}</p> : null}
      <div className="flex gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} disabled={busy} onClick={() => setOpen(false)}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}

function ResetPassword({ membershipId }: { membershipId: string }) {
  const t = useTranslations("Members");
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<null>(`/api/bff/tenant/members/${membershipId}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    setBusy(false);
    if (res.ok) {
      setMessage(t("resetDone"));
      setPassword("");
    } else {
      setError(res.message);
    }
  }

  if (!open) {
    return (
      <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
        {t("resetPassword")}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-surface p-2">
      <p className="text-xs text-muted">{t("resetHint")}</p>
      <input
        type="password"
        className={ui.input}
        value={password}
        minLength={12}
        onChange={(e) => setPassword(e.target.value)}
        placeholder={t("startPassword")}
      />
      {error ? <p className={ui.error}>{error}</p> : null}
      {message ? <p className="text-xs text-success-fg">{message}</p> : null}
      <div className="flex gap-2">
        <button type="button" className={ui.button} disabled={busy || password.length < 12} onClick={() => void submit()}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} disabled={busy} onClick={() => setOpen(false)}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}

function AddMemberForm({ roles, onCreated }: { roles: Role[]; onCreated: (member: Member) => void }) {
  const t = useTranslations("Members");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [roleCodes, setRoleCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const res = await bff<Member>("/api/bff/tenant/members", {
      method: "POST",
      body: JSON.stringify({ email, display_name: displayName, password, role_codes: roleCodes }),
    });
    setBusy(false);
    if (res.ok) {
      onCreated(res.data);
      setEmail("");
      setDisplayName("");
      setPassword("");
      setRoleCodes([]);
    } else {
      setError(res.message);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("addTitle")}</h2>
      <p className="text-xs text-muted">{t("addContactHint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("email")}</span>
        <input type="email" required className={ui.input} value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("displayName")}</span>
        <input required className={ui.input} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("startPassword")}</span>
        <input
          type="password"
          required
          minLength={12}
          className={ui.input}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <span className="text-xs text-muted">{t("passwordHint")}</span>
      </label>
      <fieldset className="flex flex-col gap-1.5">
        <legend className={ui.label}>{t("roles")}</legend>
        {roles.map((r) => (
          <label key={r.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={roleCodes.includes(r.code)}
              onChange={(e) =>
                setRoleCodes((prev) => (e.target.checked ? [...prev, r.code] : prev.filter((c) => c !== r.code)))
              }
            />
            {r.name}
          </label>
        ))}
      </fieldset>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      <button type="submit" className={ui.primary} disabled={busy}>
        {t("addSubmit")}
      </button>
    </form>
  );
}

export function MembersAdmin({
  initialMembers,
  roles,
  competenceCatalogue,
  canCreate,
  canUpdate,
}: {
  initialMembers: Member[];
  roles: Role[];
  competenceCatalogue: { code: string; label: string }[];
  canCreate: boolean;
  canUpdate: boolean;
}) {
  const t = useTranslations("Members");
  const [members, setMembers] = useState(initialMembers);
  const [busyId, setBusyId] = useState<string | null>(null);

  function updateMember(membershipId: string, patch: Partial<Member>) {
    setMembers((prev) => prev.map((m) => (m.membership_id === membershipId ? { ...m, ...patch } : m)));
  }

  async function toggleStatus(member: Member) {
    const next = member.status === "active" ? "disabled" : "active";
    if (!window.confirm(t(next === "disabled" ? "confirmDisable" : "confirmEnable", { name: member.display_name }))) return;
    setBusyId(member.membership_id);
    const res = await bff<Member>(`/api/bff/tenant/members/${member.membership_id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: next }),
    });
    setBusyId(null);
    if (res.ok) updateMember(member.membership_id, { status: next });
  }

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2 sm:hidden" data-testid="members-cards">
        {members.map((m) => (
          <li key={m.membership_id} className={ui.card} data-testid="member-card">
            <div className="flex flex-col gap-1.5">
              <span className="flex items-center justify-between gap-2">
                {m.contact_id ? (
                  <Link href={`/kontakte/${m.contact_id}`} className="font-medium underline">
                    {m.display_name}
                  </Link>
                ) : (
                  <span className="font-medium">{m.display_name}</span>
                )}
                <StatusBadge status={m.status} />
              </span>
              <span className="text-sm text-muted">{m.email}</span>
              <span className="text-sm text-muted">{m.roles.join(", ")}</span>
              <span className="text-xs text-muted">{t("lastLogin")}: {formatDateTime(m.last_login_at)}</span>
              {canUpdate ? (
                <div className="flex flex-col gap-1.5 pt-1">
                  <RolesEditor member={m} roles={roles} onSaved={(roleCodes) => updateMember(m.membership_id, { roles: roleCodes })} />
                  <CompetencesEditor member={m} catalogue={competenceCatalogue} onSaved={(competences) => updateMember(m.membership_id, { competences })} />
                  <MobilePhoneEditor member={m} onSaved={(mobile_phone) => updateMember(m.membership_id, { mobile_phone })} />
                  <ResetPassword membershipId={m.membership_id} />
                  <button
                    type="button"
                    className={`${ui.buttonSm} ${ui.actionFull}`}
                    disabled={busyId === m.membership_id}
                    onClick={() => void toggleStatus(m)}
                  >
                    {m.status === "active" ? t("disable") : t("enable")}
                  </button>
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      <div className="hidden overflow-x-auto rounded-xl border border-border sm:block">
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("name")}</th>
              <th>{t("email")}</th>
              <th>{t("roles")}</th>
              <th>{t("statusColumn")}</th>
              <th>{t("lastLogin")}</th>
              {canUpdate ? <th>{t("actions")}</th> : null}
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.membership_id}>
                <td>
                  {m.contact_id ? (
                    <Link href={`/kontakte/${m.contact_id}`} className="underline">
                      {m.display_name}
                    </Link>
                  ) : (
                    m.display_name
                  )}
                </td>
                <td>{m.email}</td>
                <td>{m.roles.join(", ")}</td>
                <td>
                  <StatusBadge status={m.status} />
                </td>
                <td>{formatDateTime(m.last_login_at)}</td>
                {canUpdate ? (
                  <td>
                    <div className="flex flex-col gap-1.5">
                      <RolesEditor member={m} roles={roles} onSaved={(roleCodes) => updateMember(m.membership_id, { roles: roleCodes })} />
                      <CompetencesEditor member={m} catalogue={competenceCatalogue} onSaved={(competences) => updateMember(m.membership_id, { competences })} />
                  <MobilePhoneEditor member={m} onSaved={(mobile_phone) => updateMember(m.membership_id, { mobile_phone })} />
                      <ResetPassword membershipId={m.membership_id} />
                      <button
                        type="button"
                        className={ui.buttonSm}
                        disabled={busyId === m.membership_id}
                        onClick={() => void toggleStatus(m)}
                      >
                        {m.status === "active" ? t("disable") : t("enable")}
                      </button>
                    </div>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canCreate ? <AddMemberForm roles={roles} onCreated={(member) => setMembers((prev) => [...prev, member])} /> : null}
    </div>
  );
}
