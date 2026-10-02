"use client";

import { useTranslations } from "next-intl";

import { formatDate, formatDateTime, formatDecimal } from "@/lib/format";
import { ui } from "@/lib/ui";

import { DefectTicketsButton } from "./DefectTicketsButton";
import { PhotoStrip } from "./PhotoStrip";
import type { Step } from "./steps";
import { type Doc, type Full, type Item, itemTitle } from "./types";

export type HandoverSummaryProps = {
  p: Full;
  /** `locked`: read view of a completed protocol; `overview`: summary step of the editor with
   *  an edit button per section and the hints on top. */
  mode: "locked" | "overview";
  onGoTo?: (step: Step) => void;
};

const label = (item: Item, key: string) => (item[key] == null ? "" : String(item[key]));

/** Read view of the stored protocol (M31 WP2): only saved data, no editor mount. Rooms with
 *  their defects grouped below, defects without room in a block of their own, tel and mailto
 *  links, PDF in the same tab. No statement about legal effect, delivery or reading. */
export function HandoverSummary({ p, mode, onGoTo }: HandoverSummaryProps) {
  const t = useTranslations("Handover");
  const tRole = (r: string) => (r ? t(`roles.${r}`) : "");
  const photosOf = (id: string): Doc[] => p.documents.filter((d) => d.item_id === id);
  const attachments = p.documents.filter((d) => d.kind === "attachment" || (d.kind === "photo" && !d.item_id));
  const unassigned = p.defects.filter((d) => !d.room_id);
  const photoCount = p.documents.filter((d) => d.kind === "photo").length;
  const opt = (section: string, field: string, value: string) => (value ? t(`options.${section}.${field}.${value}`) : "");
  const edit = (step: Step) =>
    mode === "overview" && onGoTo ? (
      <button type="button" className={ui.buttonSm} onClick={() => onGoTo(step)} data-testid={`summary-edit-${step}`}>
        {t("summary.edit")}
      </button>
    ) : null;
  const Section = ({ step, title, children }: { step: Step; title: string; children: React.ReactNode }) => (
    <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby={`summary-${step}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 id={`summary-${step}`} className={ui.h3}>
          {title}
        </h2>
        {edit(step)}
      </div>
      {children}
    </section>
  );
  const Empty = () => <p className="text-sm text-muted">{t("summary.none")}</p>;

  return (
    <div className="flex flex-col gap-4" data-testid="handover-summary">
      {mode === "overview" && p.hints.length ? (
        <div className={ui.notice} data-testid="hints">
          <strong>{t("hints.title")}</strong>
          <ul className="mt-1 list-disc pl-5">
            {p.hints.map((h, i) => (
              <li key={h}>
                {h}
                {onGoTo && p.hint_codes?.[i] ? (
                  <HintLink code={p.hint_codes[i]} onGoTo={onGoTo} label={t("summary.edit")} />
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {mode === "locked" ? <p className={ui.notice}>{t("summary.readOnlyHint")}</p> : null}
      {mode === "overview" && p.status !== "cancelled" ? <DefectTicketsButton protocolId={p.id} defectCount={p.defects.length} /> : null}

      <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="summary-object">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="summary-object" className={ui.h3}>
            {p.number}
            {p.version > 1 ? ` ${t("versions.label", { version: p.version })}` : ""}
          </h2>
          <span className="flex items-center gap-2">
            <span className={p.finalized ? ui.badgeSuccess : p.status === "cancelled" ? ui.badgeDanger : ui.badgeGold}>{t(`statusLabel.${p.status}`)}</span>
            {edit("object")}
          </span>
        </div>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-2">
          <dt className="text-muted">{t("fields.address")}</dt>
          <dd>{p.address || t("summary.empty")}</dd>
          {p.object_label ? (
            <>
              <dt className="text-muted">{t("fields.object_label")}</dt>
              <dd>{p.object_label}</dd>
            </>
          ) : null}
          <dt className="text-muted">{t("summary.unit")}</dt>
          <dd>{[p.unit_number, p.unit_label, p.unit_position].filter(Boolean).join(" ") || t("summary.empty")}</dd>
          {p.floor ? (
            <>
              <dt className="text-muted">{t("summary.floor")}</dt>
              <dd>{p.floor}</dd>
            </>
          ) : null}
          <dt className="text-muted">{t("summary.date")}</dt>
          <dd className={ui.num}>{formatDate(p.handover_date) || t("summary.empty")}</dd>
          {!p.hide_time_information && (p.handover_start || p.handover_end) ? (
            <>
              <dt className="text-muted">{t("summary.time")}</dt>
              <dd className={ui.num}>{[p.handover_start?.slice(0, 5), p.handover_end?.slice(0, 5)].filter(Boolean).join(" bis ")}</dd>
            </>
          ) : null}
          {p.handover_location ? (
            <>
              <dt className="text-muted">{t("summary.location")}</dt>
              <dd>{p.handover_location}</dd>
            </>
          ) : null}
        </dl>
      </section>

      <Section step="participants" title={t("summary.participants")}>
        {p.participants.length === 0 ? (
          <Empty />
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {p.participants.map((x) => {
              const name = [label(x, "first_name"), label(x, "last_name")].filter(Boolean).join(" ") || label(x, "company");
              return (
                <li key={x.id} className="flex flex-col gap-1 rounded-md border border-border-soft p-3 text-sm">
                  <span className={ui.badge}>{label(x, "role_label") || tRole(label(x, "role"))}</span>
                  <span className="font-medium">{name || t("signature.noName")}</span>
                  {label(x, "company") && name !== label(x, "company") ? <span className="text-muted">{label(x, "company")}</span> : null}
                  {label(x, "phone") ? (
                    <a href={`tel:${label(x, "phone").replace(/\s+/g, "")}`} className={`${ui.num} inline-flex min-h-11 items-center underline`}>
                      {label(x, "phone")}
                    </a>
                  ) : null}
                  {label(x, "email") ? (
                    <a href={`mailto:${label(x, "email")}`} className="inline-flex min-h-11 items-center break-all underline">
                      {label(x, "email")}
                    </a>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section step="meters" title={t("summary.meters")}>
        {p.meters.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {p.meters.map((m) => (
              <li key={m.id} className="flex flex-col gap-1 rounded-md border border-border-soft p-3">
                <div className="flex flex-wrap justify-between gap-2">
                  <span className="font-medium">{label(m, "custom_type") || opt("meters", "meter_type", label(m, "meter_type"))}</span>
                  <span className={ui.num}>
                    {label(m, "value") ? `${formatDecimal(label(m, "value"), 3).replace(/,?0+$/, "")} ${label(m, "unit")}`.trim() : t("summary.empty")}
                  </span>
                </div>
                <div className="text-muted">
                  {label(m, "number") ? `Nr. ${label(m, "number")}` : ""}
                  {label(m, "read_on") ? ` · ${t("summary.readAt")} ${formatDate(label(m, "read_on"))}` : ""}
                </div>
                <PhotoStrip docs={photosOf(m.id)} itemTitle={itemTitle("meters", m, tRole)} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section step="rooms" title={t("summary.rooms")}>
        {p.rooms.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-3 text-sm">
            {p.rooms.map((r) => (
              <li key={r.id} className="flex flex-col gap-2 rounded-md border border-border-soft p-3" data-testid="summary-room">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{label(r, "name") || label(r, "room_type") || "Raum"}</span>
                  {label(r, "condition") ? <span className={label(r, "condition") === "defective" ? ui.badgeWarning : ui.badge}>{opt("rooms", "condition", label(r, "condition"))}</span> : null}
                </div>
                {label(r, "comment") ? <p className="text-muted">{label(r, "comment")}</p> : null}
                <PhotoStrip docs={photosOf(r.id)} itemTitle={itemTitle("rooms", r, tRole)} />
                {p.defects.filter((d) => d.room_id === r.id).map((d) => (
                  <DefectCard key={d.id} d={d} docs={photosOf(d.id)} opt={opt} tRole={tRole} />
                ))}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {unassigned.length ? (
        <Section step="defects" title={t("summary.unassignedDefects")}>
          <ul className="flex flex-col gap-2 text-sm" data-testid="summary-unassigned">
            {unassigned.map((d) => (
              <li key={d.id}>
                <DefectCard d={d} docs={photosOf(d.id)} opt={opt} tRole={tRole} />
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section step="keys" title={t("summary.keys")}>
        {p.keys.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {p.keys.map((k) => (
              <li key={k.id} className="flex flex-wrap justify-between gap-2">
                <span>{label(k, "custom_name") || label(k, "key_type") || "Schlüssel"}</span>
                <span className="text-muted">
                  <span className={ui.num}>{label(k, "quantity")}</span> {label(k, "status") ? opt("keys", "status", label(k, "status")) : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section step="items" title={t("summary.items")}>
        {p.items.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {p.items.map((i) => (
              <li key={i.id} className="flex flex-col gap-1">
                <div className="flex flex-wrap justify-between gap-2">
                  <span>{label(i, "name") || label(i, "item_type")}</span>
                  <span className="text-muted">
                    {label(i, "condition")} {label(i, "quantity") ? <span className={ui.num}>{label(i, "quantity")}</span> : null}
                  </span>
                </div>
                <PhotoStrip docs={photosOf(i.id)} itemTitle={itemTitle("items", i, tRole)} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section step="notes" title={t("summary.notes")}>
        {p.notes.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {p.notes.map((n) => (
              <li key={n.id} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  {label(n, "category") ? <span className={ui.badge}>{opt("notes", "category", label(n, "category"))}</span> : null}
                  {n.is_internal ? <span className={ui.badgeWarning}>{t("summary.internal")}</span> : null}
                  {label(n, "due_date") ? (
                    <span className="text-muted">
                      {t("summary.dueDate")} {formatDate(label(n, "due_date"))}
                    </span>
                  ) : null}
                </div>
                <p className="whitespace-pre-wrap">{label(n, "text")}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section step="attachments" title={t("summary.attachments")}>
        {attachments.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {attachments.map((d) => (
              <li key={d.id}>
                <a href={`/api/handover-files/documents/${d.id}/content`} download={d.filename} className="inline-flex min-h-11 items-center underline">
                  {d.filename}
                </a>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted">{t("summary.photos", { count: photoCount })}</p>
      </Section>

      {p.changes?.length ? (
        <section className={`${ui.card} flex flex-col gap-2`} data-testid="summary-changes">
          <h2 className={ui.h3}>{t("changes.title")}</h2>
          <ul className="flex flex-col gap-1 text-sm">
            {p.changes.map((c) => (
              <li key={c.id}>
                {t("changes.entry", { date: formatDateTime(c.changed_at), user: c.changed_by_name || t("changes.unknownUser"), reason: c.reason })}
                <span className="text-muted"> ({t("changes.invalidated", { count: c.signatures_invalidated })})</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <Section step="signatures" title={t("summary.signatures")}>
        {p.signatures.length === 0 ? (
          <p className="text-sm text-muted">{t("summary.noSignature")}</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {p.signatures.map((s) => (
              <li key={s.id} className={`flex flex-col gap-1 rounded-md border border-border-soft p-3 text-sm ${s.invalidated_at ? "opacity-70" : ""}`}>
                {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
                <img src={`/api/handover-files/documents/${s.document_id}/content`} alt="" className="max-h-28 w-fit rounded border border-border bg-paper" />
                <span className="font-medium">{s.signer_name || t("signature.noName")}</span>
                <span className="text-muted">{s.signer_role ? tRole(s.signer_role) : ""}</span>
                <span className="text-muted">
                  {t("summary.signedAt")} {formatDateTime(s.signed_at)}
                  {s.signed_location ? `, ${s.signed_location}` : ""}
                </span>
                {s.invalidated_at ? <span className={ui.badgeWarning}>{t("signature.invalidated", { date: formatDateTime(s.invalidated_at) })}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className={ui.formActions}>
        <a className={`${ui.button} ${ui.actionFull}`} href={`/api/handover-files/handover/protocols/${p.id}/pdf`} data-testid="summary-pdf">
          {p.finalized ? t("summary.pdf") : t("summary.pdfDraft")}
        </a>
      </div>
    </div>
  );
}

function HintLink({ code, onGoTo, label: text }: { code: string; onGoTo: (step: Step) => void; label: string }) {
  const step = hintStep(code);
  if (!step) return null;
  return (
    <>
      {" "}
      <button type="button" className="min-h-11 underline" onClick={() => onGoTo(step)}>
        {text}
      </button>
    </>
  );
}

function hintStep(code: string): Step | null {
  const map: Record<string, Step> = {
    no_address: "object",
    no_date: "object",
    no_participants: "participants",
    no_meters: "meters",
    no_rooms: "rooms",
    no_keys: "keys",
    no_signature: "signatures",
    signatures_invalidated: "signatures",
    iban_invalid: "deposit",
  };
  return map[code] ?? null;
}

function DefectCard({ d, docs, opt, tRole }: { d: Item; docs: Doc[]; opt: (s: string, f: string, v: string) => string; tRole: (r: string) => string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-surface-2 p-2" data-testid="summary-defect">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{label(d, "title") || label(d, "category") || "Mangel"}</span>
        {label(d, "priority") ? <span className={label(d, "priority") === "urgent" || label(d, "priority") === "high" ? ui.badgeDanger : ui.badge}>{opt("defects", "priority", label(d, "priority"))}</span> : null}
        {label(d, "defect_status") ? <span className={ui.badge}>{opt("defects", "defect_status", label(d, "defect_status"))}</span> : null}
      </div>
      {label(d, "description") ? <p className="text-muted">{label(d, "description")}</p> : null}
      <PhotoStrip docs={docs} itemTitle={itemTitle("defects", d, tRole)} />
    </div>
  );
}
