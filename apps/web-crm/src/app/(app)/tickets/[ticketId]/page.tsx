import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { DmsDocumentsPanel } from "@/components/documents/DmsDocumentsPanel";
import { SlaBadge } from "@/components/tickets/SlaBadge";
import { TicketChecklist } from "@/components/tickets/TicketChecklist";
import { TicketEdit } from "@/components/tickets/TicketForms";
import { TicketMergeDialog } from "@/components/tickets/TicketMergeDialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Comment = { body: string; internal: boolean; created_at: string };
type Event = { kind: string; at: string };

export default async function TicketPage({ params }: { params: Promise<{ ticketId: string }> }) {
  const { ticketId } = await params;
  const t = await getTranslations("Tickets");
  const { data, error, response } = await serverApi().GET("/api/v1/tickets/{ticket_id}", {
    params: { path: { ticket_id: ticketId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const me = await serverApi().GET("/api/v1/auth/me");
  const canManageSla = me.data?.permissions.includes("sla:update") ?? false;
  const comments = (data.comments ?? []) as Comment[];
  const events = (data.events ?? []) as Event[];
  const checklist = (data.checklist ?? []) as { key: string; label: string; required: boolean; done: boolean }[];
  const extraFieldValues = (data.extra_fields ?? {}) as Record<string, unknown>;
  let extraFieldDefs: { key: string; label: string; type: string; required: boolean }[] = [];
  if (data.template_id) {
    const tpl = await serverApi().GET("/api/v1/tickets/templates/{template_id}", {
      params: { path: { template_id: String(data.template_id) } },
    });
    extraFieldDefs = (tpl.data?.extra_fields ?? []) as typeof extraFieldDefs;
  }
  const api = serverApi();
  const mergedInto = data.merged_into_ticket_id ? String(data.merged_into_ticket_id) : null;
  const [mergedTarget, mergedSources, contact, property] = await Promise.all([
    mergedInto ? api.GET("/api/v1/tickets/{ticket_id}", { params: { path: { ticket_id: mergedInto } } }) : null,
    api.GET("/api/v1/tickets", { params: { query: { merged_into: ticketId } } }),
    data.contact_id ? api.GET("/api/v1/contacts/{contact_id}", { params: { path: { contact_id: String(data.contact_id) } } }) : null,
    data.property_id ? api.GET("/api/v1/properties/{property_id}", { params: { path: { property_id: String(data.property_id) } } }) : null,
  ]);
  const sources = (mergedSources.data ?? []).map((s) => ({ id: String(s.id), number: Number(s.number), title: s.title ? String(s.title) : "" }));
  const canMerge = !mergedInto && data.status !== "closed";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/tickets", label: t("title") }]}
        title={`#${String(data.number)} ${String(data.title ?? "")}`}
        description={data.public_description ? String(data.public_description) : undefined}
      />
      {mergedInto ? (
        <div role="status" className={ui.notice} data-testid="merged-banner">
          <Link href={`/tickets/${mergedInto}`} className="font-medium text-fg hover:underline">
            {t("merge.mergedBanner", { number: String(mergedTarget?.data?.number ?? "") })}
          </Link>
          <div className="text-xs">{t("merge.mergedLocked")}</div>
        </div>
      ) : null}
      {sources.length > 0 ? (
        <div className={ui.notice} data-testid="merged-sources">
          {t("merge.contains")}{" "}
          {sources.map((s, i) => (
            <span key={s.id}>
              {i > 0 ? ", " : ""}
              <Link href={`/tickets/${s.id}`} className="font-medium text-fg hover:underline">
                #{s.number} {s.title}
              </Link>
            </span>
          ))}
        </div>
      ) : null}
      {mergedInto ? null : (
        <>
          <SlaBadge ticketId={ticketId} canManage={canManageSla} />
          <TicketEdit id={ticketId} status={String(data.status)} priority={String(data.priority)} />
          <TicketChecklist
            ticketId={ticketId}
            checklist={checklist}
            extraFieldDefs={extraFieldDefs}
            extraFieldValues={extraFieldValues}
          />
        </>
      )}
      {canMerge ? (
        <TicketMergeDialog
          source={{
            id: ticketId,
            number: Number(data.number),
            title: data.title ? String(data.title) : null,
            status: String(data.status),
            priority: String(data.priority),
            contact: contact?.data?.display_name ? String(contact.data.display_name) : null,
            property: property?.data?.name ? String(property.data.name) : null,
            messageCount: Number(data.message_count ?? 0) + comments.length,
          }}
        />
      ) : null}
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("comments")}</h2>
        <ul className="flex flex-col gap-2 text-sm">
          {comments.map((c, i) => (
            <li key={i} className={ui.card}>
              <div className="text-xs text-muted">
                {formatDateTime(c.created_at)} · {c.internal ? t("internal") : t("external")}
              </div>
              <div className="whitespace-pre-wrap">{c.body}</div>
            </li>
          ))}
        </ul>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("history")}</h2>
        <ul className="text-xs text-muted">
          {events.map((e, i) => (
            <li key={i}>
              {formatDateTime(e.at)} · {e.kind}
            </li>
          ))}
        </ul>
      </section>
      <DmsDocumentsPanel entity="ticket" id={ticketId} />
    </div>
  );
}
