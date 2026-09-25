import { useTranslations } from "next-intl";

import type { components } from "@mhvp/api-client";

type Role = components["schemas"]["ContactRoleCode"];

/** Compact pills for a contact's manual role classification (list rows, detail header). */
export function RolePills({ roles }: { roles: Role[] }) {
  const tl = useTranslations("Labels");
  if (!roles.length) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {roles.map((r) => (
        <span key={r} className="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">
          {tl(`role.${r}`)}
        </span>
      ))}
    </span>
  );
}
