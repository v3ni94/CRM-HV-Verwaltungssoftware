import { getTranslations } from "next-intl/server";

import { MeetingClose } from "@/components/hoa/MeetingClose";
import { MajorityRules, MeetingPanel, type MajorityRule } from "@/components/hoa/HoaForms";
import { MeetingDisruptions, type DisruptionRow } from "@/components/hoa/MeetingDisruptions";
import { MeetingInvitationRecipients, type InvitationRecipientRow } from "@/components/hoa/MeetingInvitationRecipients";
import { MeetingDeadlineForm } from "@/components/hoa/MeetingDeadlineForm";
import { MeetingDetailsForm, type MeetingDetails } from "@/components/hoa/MeetingDetailsForm";
import { MeetingFormPanel, type AttendanceRow, type MeetingFormData } from "@/components/hoa/MeetingFormPanel";
import { VirtualDeadlines, type VirtualDeadlinesData } from "@/components/hoa/VirtualDeadlines";
import { MemberVoting } from "@/components/hoa/MemberVoting";
import { OnlineParticipation, type OnlineOverview } from "@/components/hoa/OnlineParticipation";
import { ProtocolDraft } from "@/components/hoa/ProtocolDraft";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { formatDate, formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function MeetingPage({ params }: { params: Promise<{ meetingId: string }> }) {
  const { meetingId } = await params;
  const t = await getTranslations("HoaWork");
  const api = serverApi();
  const [{ data, error, response }, members, attendanceResponse, onlineResponse] = await Promise.all([
    api.GET("/api/v1/hoa/meetings/{meeting_id}", { params: { path: { meeting_id: meetingId } } }),
    api.GET("/api/v1/hoa/meetings/{meeting_id}/members", { params: { path: { meeting_id: meetingId } } }),
    // M25-03: Teilnahmenachweis mit Kanal (Präsenz, online, Vollmacht).
    serverFetch(`/api/v1/hoa/meetings/${encodeURIComponent(meetingId)}/attendance-list`),
    // AD06: Online-Teilnahme aus dem Portal (Zusagen, Vollmachten, Wortmeldungen, TOP-Abstimmung).
    serverFetch(`/api/v1/hoa/meetings/${encodeURIComponent(meetingId)}/online`),
  ]);
  const online = onlineResponse.ok ? ((await onlineResponse.json()) as OnlineOverview) : null;
  // GA03-01: Vorlagen als Auswahlliste (aktive Vorlagen des Mandanten).
  const templatesResponse = await serverFetch("/api/v1/document-templates");
  const templates = templatesResponse.ok ? ((await templatesResponse.json()) as { id: string; name: string }[]) : [];
  // GAF-15: Empfänger der Einladung (nur Anzeige).
  const recipientsResponse = await serverFetch(`/api/v1/hoa/meetings/${encodeURIComponent(meetingId)}/invitation-recipients`);
  const recipients = recipientsResponse.ok ? ((await recipientsResponse.json()) as InvitationRecipientRow[]) : [];
  const attendance = attendanceResponse.ok ? (((await attendanceResponse.json()) as { rows?: AttendanceRow[] }).rows ?? []) : [];
  redirectIfUnauthenticated(response);
  const entity = String(data?.legal_entity_id ?? "");
  const rules = data
    ? ((await api.GET("/api/v1/hoa/majority-rules", { params: { query: { legal_entity_id: entity } } })).data ?? [])
    : [];
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>
        {t("meeting")} {formatDateTime(String(data.scheduled_at))} · {t(`meetingStatus.${String(data.status)}`)}
      </h1>
      <p className="text-sm text-muted">
        {t(`principle.${String(data.voting_principle)}`)}
        {data.invited_at ? ` · ${t("invitedOn", { date: formatDate(String(data.invited_at)) })}` : ""} ·{" "}
        {t("represented", { n: Number(data.represented ?? 0), proxies: Number(data.proxies ?? 0) })}
      </p>
      <p className={ui.notice}>{t("meetingNotice")}</p>
      <MeetingFormPanel meetingId={meetingId} data={data as unknown as MeetingFormData} attendance={attendance} />
      <MeetingDetailsForm meetingId={meetingId} data={data as unknown as MeetingDetails} closed={String(data.status) === "closed"} templates={templates.map((x) => ({ id: String(x.id), name: String(x.name) }))} />
      {data.mode === "virtual" && (data as { virtual_basis_deadlines?: VirtualDeadlinesData | null }).virtual_basis_deadlines ? (
        <VirtualDeadlines
          data={(data as unknown as { virtual_basis_deadlines: VirtualDeadlinesData }).virtual_basis_deadlines}
          termNotice={(data as { virtual_basis_term_notice?: string | null }).virtual_basis_term_notice ?? null}
        />
      ) : null}
      {data.mode === "virtual" ? (
        <MeetingDeadlineForm
          meetingId={meetingId}
          deadline={data.resolution_deadline_at ? String(data.resolution_deadline_at) : null}
          source={data.resolution_deadline_source ? String(data.resolution_deadline_source) : null}
        />
      ) : null}
      <MeetingInvitationRecipients rows={recipients} />
      {data.mode !== "presence" ? (
        <MeetingDisruptions
          meetingId={meetingId}
          rows={((data as { disruptions?: DisruptionRow[] }).disruptions ?? []) as DisruptionRow[]}
          closed={["closing", "closed"].includes(String(data.status))}
        />
      ) : null}
      <MemberVoting
        meetingId={meetingId}
        status={String(data.status)}
        members={(members.data ?? []) as never}
        agenda={(data.agenda ?? []) as never}
      />
      {online && data.mode !== "presence" ? (
        <OnlineParticipation
          meetingId={meetingId}
          data={online}
          units={Object.fromEntries(((members.data ?? []) as { contract_id: string; unit_number: string | null }[]).map((m) => [m.contract_id, m.unit_number ?? ""]))}
        />
      ) : null}
      <MeetingPanel
        id={meetingId}
        status={String(data.status)}
        agenda={(data.agenda ?? []) as never}
        rules={rules as MajorityRule[]}
      />
      <MajorityRules legalEntityId={entity} rules={rules as MajorityRule[]} />
      <MeetingClose
        meetingId={meetingId}
        status={String(data.status)}
        minutesDocumentId={(data as { minutes_document_id?: string | null }).minutes_document_id ?? null}
        closeRequestedAt={(data as { close_requested_at?: string | null }).close_requested_at ?? null}
        closedAt={(data as { closed_at?: string | null }).closed_at ?? null}
      />
      <ProtocolDraft
        meetingId={meetingId}
        draftDocumentId={(data as { minutes_draft_document_id?: string | null }).minutes_draft_document_id ?? null}
        minutesDocumentId={(data as { minutes_document_id?: string | null }).minutes_document_id ?? null}
      />
    </div>
  );
}
