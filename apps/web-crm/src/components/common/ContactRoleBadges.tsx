"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { entityHref } from "@/lib/entity-links";

/** ``mhvp.contacts.schemas.ObjectRelationOut`` (Verträge, Eigentum, Objektbezüge eines
 * Kontakts); nur die für die Rollenanzeige nötigen Felder. */
type ObjectRelation = {
  kind: "mieter" | "eigentuemer" | "kontakt";
  property_id: string;
  property_name: string;
  unit_id: string | null;
  unit_label: string | null;
  active: boolean;
  category_code: string | null;
};

export type ContactRole = {
  key: string;
  label: string;
  propertyId: string;
  propertyName: string;
  unitId: string | null;
  unitLabel: string | null;
};

const SERVICE_CATEGORIES = new Set(["caretaker", "emergency", "utility"]);

/** Rollen (Mieter, Eigentümer, Beirat, Dienstleister) eines Kontakts aus dessen aktiven
 * Verträgen, Eigentumsverhältnissen und Objektbeziehungen (operator 27.09.2026, A-068
 * Nachtrag 1.37.0). Ein Kontakt kann mehrere Rollen zugleich haben. */
function rolesFromRelations(relations: ObjectRelation[], t: ReturnType<typeof useTranslations>): ContactRole[] {
  const out: ContactRole[] = [];
  for (const r of relations) {
    if (!r.active) continue;
    let label: string | null = null;
    if (r.kind === "mieter") label = t("mieter");
    else if (r.kind === "eigentuemer") label = t("eigentuemer");
    else if (r.kind === "kontakt" && r.category_code === "board") label = t("beirat");
    else if (r.kind === "kontakt" && r.category_code && SERVICE_CATEGORIES.has(r.category_code)) label = t("dienstleister");
    if (!label) continue;
    out.push({
      key: `${r.kind}-${r.property_id}-${r.unit_id ?? ""}-${r.category_code ?? ""}`,
      label,
      propertyId: r.property_id,
      propertyName: r.property_name,
      unitId: r.unit_id,
      unitLabel: r.unit_label,
    });
  }
  // Eine Rolle je Objekt/Einheit nur einmal anzeigen (mehrere Verträge derselben Art möglich).
  const seen = new Set<string>();
  return out.filter((role) => {
    const dedupeKey = `${role.label}-${role.propertyId}-${role.unitId ?? ""}`;
    if (seen.has(dedupeKey)) return false;
    seen.add(dedupeKey);
    return true;
  });
}

/** Rollenanzeige neben einem Kontakt in Maildetail und Ticketdetail (operator 27.09.2026):
 * Mieter, Eigentümer, Beirat, Dienstleister mit Verweis auf Kontakt, Einheit und Objekt. Leer,
 * solange die Rollen noch laden oder keine aktive Rolle vorliegt. */
export function ContactRoleBadges({ contactId }: { contactId: string }) {
  const t = useTranslations("ContactRoleBadges");
  const [relations, setRelations] = useState<ObjectRelation[] | null>(null);

  useEffect(() => {
    let active = true;
    setRelations(null);
    void bff<ObjectRelation[]>(`/api/bff/contacts/${contactId}/relations`).then((res) => {
      if (active && res.ok) setRelations(res.data ?? []);
    });
    return () => {
      active = false;
    };
  }, [contactId]);

  const roles = relations ? rolesFromRelations(relations, t) : null;
  if (!roles || roles.length === 0) return null;

  return (
    <ul className="flex flex-wrap items-center gap-1.5" data-testid="contact-role-badges" aria-label={t("title")}>
      {roles.map((role) => {
        const propertyHref = entityHref("property", role.propertyId);
        const unitHref = role.unitId ? entityHref("unit", role.unitId) : null;
        return (
          <li
            key={role.key}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-fg"
          >
            <span>{role.label}</span>
            {unitHref ? (
              <Link href={unitHref} className="text-muted hover:underline">
                {role.unitLabel ?? t("unit")}
              </Link>
            ) : null}
            {propertyHref ? (
              <Link href={propertyHref} className="text-muted hover:underline">
                {role.propertyName}
              </Link>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
