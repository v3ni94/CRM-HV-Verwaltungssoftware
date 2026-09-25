"use client";

import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Matrix = Record<string, string[]>;

/** "Portalrechte je Rolle" (Betreiberentscheidung 25.09.2026, M2-08 entschieden,
 * docs/rules/M2-07.md): welche Portalfunktionen der Portalzugang je CRM-Systemrolle
 * freischaltet. Checkbox-Matrix, editierbar nur mit `tenant_settings:update`. */
export function PortalRolePermissions({
  catalogue,
  initialRoles,
  canUpdate,
}: {
  catalogue: string[];
  initialRoles: Matrix;
  canUpdate: boolean;
}) {
  const [roles, setRoles] = useState<Matrix>(initialRoles);
  const [busy, setBusy] = useState(false);
  const [resyncing, setResyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggle(role: string, permission: string, checked: boolean) {
    setRoles((prev) => {
      const current = prev[role] ?? [];
      const next = checked ? [...current, permission] : current.filter((p) => p !== permission);
      return { ...prev, [role]: next };
    });
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await bff<{ roles: Matrix }>("/api/bff/tenant/portal-role-permissions", {
      method: "PUT",
      body: JSON.stringify(roles),
    });
    setBusy(false);
    if (result.ok) {
      setRoles(result.data.roles);
      setMessage("Gespeichert.");
    } else {
      setError(result.message);
    }
  }

  async function resync() {
    setResyncing(true);
    setMessage(null);
    setError(null);
    const result = await bff<{ members: number }>(
      "/api/bff/tenant/portal-role-permissions/resync",
      { method: "POST" },
    );
    setResyncing(false);
    if (result.ok) {
      setMessage(`Auf ${result.data.members} bestehende Zugänge angewendet.`);
    } else {
      setError(result.message);
    }
  }

  const roleCodes = Object.keys(roles).sort();

  return (
    <section className={ui.card}>
      <h2 className={ui.h2}>Portalrechte je Rolle</h2>
      <p className="mt-1 text-sm text-muted">
        Jede Mitarbeiterin und jeder Mitarbeiter erhält einen Portalzugang für den gesamten
        Mandanten. Diese Matrix legt fest, welche Portalfunktionen die jeweilige CRM-Rolle dort
        sieht. Ausgenommene Rollen (Portalnutzer, Nur-Lesezugriff, Steuerberater,
        Versicherungsmakler) erhalten keinen Portalzugang.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-max border-collapse text-sm">
          <thead>
            <tr>
              <th className="border-b border-border p-2 text-left">Rolle</th>
              {catalogue.map((permission) => (
                <th key={permission} className="border-b border-border p-2 text-left text-xs">
                  {permission}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {roleCodes.map((code) => (
              <tr key={code}>
                <td className="border-b border-border p-2 font-medium">{code}</td>
                {catalogue.map((permission) => (
                  <td key={permission} className="border-b border-border p-2">
                    <input
                      type="checkbox"
                      aria-label={`${code}: ${permission}`}
                      disabled={!canUpdate}
                      checked={roles[code]?.includes(permission) ?? false}
                      onChange={(e) => toggle(code, permission, e.target.checked)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canUpdate ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
            Speichern
          </button>
          <button type="button" className={ui.button} disabled={resyncing} onClick={() => void resync()}>
            Auf bestehende Zugänge anwenden
          </button>
          {message ? <span className="text-xs text-success-fg">{message}</span> : null}
          {error ? <span className={ui.error}>{error}</span> : null}
        </div>
      ) : null}
    </section>
  );
}
