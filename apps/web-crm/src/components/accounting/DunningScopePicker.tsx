"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

export type DunningScopeProperty = { id: string; number: string; name: string };

/** Wahl zwischen Mandantenvorgabe und einem Objekt; die Auswahl steht in der URL
 * (`?objekt=<id>`), damit die Seite serverseitig die wirksamen Werte lädt. */
export function DunningScopePicker({
  properties,
  selected,
}: {
  properties: DunningScopeProperty[];
  selected: string | null;
}) {
  const t = useTranslations("Dunning");
  const router = useRouter();
  return (
    <label className="flex flex-wrap items-center gap-2 text-sm">
      <span className={ui.label}>{t("scopeLabel")}</span>
      <select
        className={`${ui.input} max-w-md`}
        value={selected ?? ""}
        onChange={(e) =>
          router.push(
            e.target.value
              ? `/buchhaltung/mahnwesen/einstellungen?objekt=${encodeURIComponent(e.target.value)}`
              : "/buchhaltung/mahnwesen/einstellungen",
          )
        }
      >
        <option value="">{t("scopeTenant")}</option>
        {properties.map((p) => (
          <option key={p.id} value={p.id}>
            {t("scopeProperty", { number: p.number, name: p.name })}
          </option>
        ))}
      </select>
    </label>
  );
}
