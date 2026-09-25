import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  SlaSettings,
  type EmergencyAlert,
  type Member,
  type OnCallSchedule,
  type SlaRule,
  type SmsGatewayConfig,
  type WorkCalendar,
} from "@/components/sla/SlaSettings";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  if (!res.ok) return fallback;
  return (await res.json()) as T;
}

/** SLA und Bereitschaft (M21 Übernahme aus dem Immoware Hub): Regeln mit Eskalationsstufen,
 *  Bereitschaftsplan, Geschäftszeitenkalender und Notfallalarme. Bearbeiten nur mit
 *  sla:update, sonst schreibgeschützt (Muster aus MailboxSettings). */
export default async function SlaSettingsPage() {
  const t = await getTranslations("Sla");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("sla:read")) notFound();
  const canManage = permissions.includes("sla:update");
  const [rules, onCall, currentOnCall, calendar, alerts, members, smsGateway] = await Promise.all([
    getJson<SlaRule[]>("/api/v1/sla/rules", []),
    getJson<OnCallSchedule[]>("/api/v1/sla/on-call", []),
    getJson<OnCallSchedule | null>("/api/v1/sla/on-call/current", null),
    getJson<WorkCalendar>("/api/v1/sla/calendar", {
      weekdays: [0, 1, 2, 3, 4],
      opens_at: "08:00",
      closes_at: "16:30",
      timezone: "Europe/Berlin",
      holidays: [],
    }),
    getJson<EmergencyAlert[]>("/api/v1/sla/alerts", []),
    api.GET("/api/v1/tenant/members"),
    getJson<SmsGatewayConfig>("/api/v1/sla/sms-gateway", {
      enabled: false,
      url: null,
      method: "POST",
      auth_header_name: null,
      auth_header_set: false,
      body_template: null,
      sender: null,
    }),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <SlaSettings
        rules={rules}
        onCall={onCall}
        currentOnCall={currentOnCall}
        calendar={calendar}
        alerts={alerts}
        members={(members.data ?? []) as Member[]}
        canManage={canManage}
        smsGateway={smsGateway}
      />
    </div>
  );
}
