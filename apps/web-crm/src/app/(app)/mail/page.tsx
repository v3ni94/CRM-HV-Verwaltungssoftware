import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ForwardInvoiceButton } from "@/components/mail/ForwardInvoiceButton";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Params = { status?: string };

type Message = {
  id: string;
  status: string;
  direction: string;
  from_address: string | null;
  subject: string | null;
  received_at: string | null;
  ticket_id: string | null;
  attachment_document_ids: string[];
  forwarded_at: string | null;
};

type Forwarding = { enabled: boolean; senders: string[] };

function senderMatches(from: string | null, senders: string[]): boolean {
  if (!from) return false;
  let address = from.trim().toLowerCase();
  const angle = address.match(/<([^>]+)>/);
  if (angle?.[1]) address = angle[1].trim();
  const domain = address.split("@").pop() ?? "";
  return senders.includes(address) || senders.includes(domain);
}

const STATUSES = ["new", "assigned", "done"] as const;

/** Mail inbox overview (menu item under Übersicht): incoming messages of the connected
 *  mailboxes with their assignment state; mailbox management stays under Einstellungen. */
export default async function MailPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const t = await getTranslations("Mail");
  const query = params.status ? { status: params.status } : {};
  const api = serverApi();
  const [{ data, error, response }, forwardingRes] = await Promise.all([
    api.GET("/api/v1/mail/messages", { params: { query } }),
    api.GET("/api/v1/mail/forwarding"),
  ]);
  redirectIfUnauthenticated(response);
  const rows = (data ?? []) as unknown as Message[];
  const forwarding = (forwardingRes.data ?? { enabled: false, senders: [] }) as Forwarding;
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("title")}
        description={t("intro")}
        action={
          <Link href="/einstellungen/postfaecher" className={ui.button}>
            {t("mailboxes")}
          </Link>
        }
      />
      <nav className="flex gap-2 text-sm">
        <Link href="/mail" className={!params.status ? ui.badgeGold : ui.badge}>
          {t("statusAll")}
        </Link>
        {STATUSES.map((s) => (
          <Link key={s} href={`/mail?status=${s}`} className={params.status === s ? ui.badgeGold : ui.badge}>
            {t(`status.${s}`)}
          </Link>
        ))}
      </nav>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <table className={ui.table} data-testid="mail-messages">
            <thead>
              <tr>
                <th>{t("colDate")}</th>
                <th>{t("colFrom")}</th>
                <th>{t("colSubject")}</th>
                <th>{t("colStatus")}</th>
                <th>{t("colTicket")}</th>
                {forwarding.enabled ? <th>{t("colForward")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id}>
                  <td className="whitespace-nowrap tabular-nums">
                    {m.received_at ? formatDateTime(m.received_at) : "–"}
                  </td>
                  <td className="max-w-52 truncate" title={m.from_address ?? undefined}>
                    {m.from_address ?? "–"}
                  </td>
                  <td className="max-w-md">
                    <span className="block truncate break-words" title={m.subject ?? undefined}>
                      {m.subject ?? "–"}
                    </span>
                  </td>
                  <td>
                    <span className={ui.badge}>{t(`status.${m.status}`)}</span>
                  </td>
                  <td>
                    {m.ticket_id ? (
                      <Link href={`/tickets/${m.ticket_id}`} className="text-sm font-medium hover:underline">
                        {t("toTicket")}
                      </Link>
                    ) : (
                      <span className="text-muted">–</span>
                    )}
                  </td>
                  {forwarding.enabled ? (
                    <td>
                      {m.forwarded_at ? (
                        <span className={ui.badge}>{t("forwarded")}</span>
                      ) : m.direction === "in" && m.attachment_document_ids.length > 0 ? (
                        <ForwardInvoiceButton
                          messageId={m.id}
                          suggested={senderMatches(m.from_address, forwarding.senders)}
                        />
                      ) : (
                        <span className="text-muted">–</span>
                      )}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
