import { useFormatter, useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

export type FrameworkContract = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  cancelled_at: string | null;
  active: boolean;
};
export type AvailabilityWindow = {
  id: string;
  starts_at: string;
  ends_at: string;
  kind: "available" | "unavailable";
  note: string | null;
};

/** GA11-04: framework contracts and availability calendar of the service provider (read only). */
export function ProviderInfo({
  contracts,
  windows,
}: {
  contracts: FrameworkContract[];
  windows: AvailabilityWindow[];
}) {
  const t = useTranslations("ProviderInfo");
  const format = useFormatter();
  const day = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium", timeZone: "Europe/Berlin" });
  const moment = (iso: string) =>
    format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Berlin" });
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <section aria-labelledby="pi-contracts" className="flex flex-col gap-2">
        <h2 id="pi-contracts" className="text-lg font-semibold">
          {t("contracts")}
        </h2>
        {contracts.length === 0 ? <p className={ui.notice}>{t("noContracts")}</p> : null}
        <ul className="flex flex-col gap-2">
          {contracts.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3">
              <span className="font-medium">{c.title}</span>
              <span className="text-sm text-muted">
                {day(c.starts_at)}
                {" bis "}
                {c.ends_at ? day(c.ends_at) : t("open")}
              </span>
              <span className={ui.badge}>{c.active ? t("active") : t("inactive")}</span>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="pi-availability" className="flex flex-col gap-2">
        <h2 id="pi-availability" className="text-lg font-semibold">
          {t("availability")}
        </h2>
        <p className="text-sm text-muted">{t("availabilityHelp")}</p>
        {windows.length === 0 ? <p className={ui.notice}>{t("noWindows")}</p> : null}
        <ul className="flex flex-col gap-2">
          {windows.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3">
              <span>
                {moment(w.starts_at)}
                {" bis "}
                {moment(w.ends_at)}
              </span>
              <span className={ui.badge}>{t(`kind.${w.kind}`)}</span>
              {w.note ? <span className="w-full text-sm text-muted">{w.note}</span> : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
