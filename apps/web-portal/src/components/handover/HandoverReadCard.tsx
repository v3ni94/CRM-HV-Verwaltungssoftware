"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";

import { PhotoLightbox, type LightboxPhoto } from "./PhotoLightbox";
import { type Doc, type Full, type Item, type Section, itemTitle } from "./types";

type T = (key: string, values?: Record<string, string | number>) => string;

function germanDate(iso: string | null): string {
  if (!iso) return "";
  const [date] = iso.split("T");
  return (date ?? "").split("-").reverse().join(".");
}

function text(item: Item, key: string): string {
  const v = item[key];
  return v == null ? "" : String(v);
}

/** Read card for a participant in the 14 day read window (M31 WP5, scope M30-06): head,
 *  meters, rooms with their defects and photos, keys, items, remarks, signatures and the PDF
 *  link, all as plain text without a single input element. Internal fields, versions and
 *  cancellations are not part of the portal response and are not rendered here. */
export function HandoverReadCard({ p, files }: { p: Full; files: string }) {
  const t = useTranslations("Handover") as unknown as T;
  const [open, setOpen] = useState<number | null>(null);
  const photos = p.documents.filter((d) => d.kind === "photo");
  const gallery: LightboxPhoto[] = photos.map((d) => ({ id: d.id, src: `${files}/documents/${d.id}/content`, title: d.title }));
  const tRole = (r: string) => (r ? t(`roles.${r}`) : "");
  const photosOf = (itemId: string): Doc[] => photos.filter((d) => d.item_id === itemId);

  function Grid({ docs }: { docs: Doc[] }) {
    if (docs.length === 0) return null;
    return (
      <ul className="flex flex-wrap gap-2" aria-label={t("read.photos")}>
        {docs.map((d) => (
          <li key={d.id}>
            <button
              type="button"
              className="block rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              aria-label={t("photos.open", { title: d.title })}
              onClick={() => setOpen(gallery.findIndex((g) => g.id === d.id))}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
              <img src={`${files}/documents/${d.id}/${d.thumbnail_url ? "thumbnail" : "content"}`} alt={d.title} className="h-20 w-20 rounded-md border border-border object-cover" />
            </button>
          </li>
        ))}
      </ul>
    );
  }

  function Block({ section, title }: { section: Section; title: string }) {
    const items = p[section];
    if (items.length === 0) return null;
    return (
      <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby={`read-${section}`}>
        <h2 id={`read-${section}`} className={ui.h3}>
          {title}
        </h2>
        <ul className="flex flex-col gap-2 text-sm">
          {items.map((item) => (
            <li key={item.id} className="flex flex-col gap-1">
              <span>{itemTitle(section, item, tRole)}</span>
              {section === "meters" && text(item, "read_on") ? (
                <span className="text-xs text-muted">{germanDate(text(item, "read_on"))}</span>
              ) : null}
              {text(item, "comment") ? <span className="text-xs text-muted">{text(item, "comment")}</span> : null}
              <Grid docs={photosOf(item.id)} />
            </li>
          ))}
        </ul>
      </section>
    );
  }

  const defectsByRoom = new Map<string, Item[]>();
  for (const d of p.defects) {
    const key = text(d, "room_id") || "";
    defectsByRoom.set(key, [...(defectsByRoom.get(key) ?? []), d]);
  }

  return (
    <div className={ui.sectionGap} data-testid="handover-read">
      <p className={ui.notice}>{t("read.intro")}</p>
      <section className={`${ui.card} flex flex-col gap-1 text-sm`} aria-labelledby="read-head">
        <h2 id="read-head" className={ui.h3}>
          {t("read.object")}
        </h2>
        <span>{p.address}</span>
        {p.handover_date ? (
          <span className="text-muted">
            {t("read.date")} {germanDate(p.handover_date)}
            {!p.hide_time_information && p.handover_start ? `, ${p.handover_start.slice(0, 5)}` : ""}
          </span>
        ) : null}
        {p.general_note ? <span className="text-muted">{p.general_note}</span> : null}
      </section>
      <Block section="participants" title={t("read.participants")} />
      <Block section="meters" title={t("read.meters")} />
      {p.rooms.length > 0 || p.defects.length > 0 ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="read-rooms">
          <h2 id="read-rooms" className={ui.h3}>
            {t("read.rooms")}
          </h2>
          {[...p.rooms.map((r) => ({ id: r.id, title: itemTitle("rooms", r, tRole), room: r })), ...(defectsByRoom.has("") ? [{ id: "", title: t("read.withoutRoom"), room: null }] : [])].map(
            (group) => {
              const defects = defectsByRoom.get(group.id) ?? [];
              return (
                <div key={group.id || "none"} className="flex flex-col gap-1 text-sm">
                  <span className="font-medium">{group.title}</span>
                  {group.room && text(group.room, "condition") ? (
                    <span className="text-xs text-muted">{t(`options.rooms.condition.${text(group.room, "condition")}`)}</span>
                  ) : null}
                  {group.room ? <Grid docs={photosOf(group.room.id)} /> : null}
                  {defects.length === 0 ? (
                    <span className="text-xs text-muted">{t("read.noDefects")}</span>
                  ) : (
                    <ul className="flex flex-col gap-1 pl-3">
                      {defects.map((d) => (
                        <li key={d.id} className="flex flex-col gap-1">
                          <span>{itemTitle("defects", d, tRole)}</span>
                          {text(d, "description") ? <span className="text-xs text-muted">{text(d, "description")}</span> : null}
                          <Grid docs={photosOf(d.id)} />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            },
          )}
        </section>
      ) : null}
      <Block section="keys" title={t("read.keys")} />
      <Block section="items" title={t("read.items")} />
      <Block section="notes" title={t("read.notes")} />
      {p.signatures.length > 0 ? (
        <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="read-signatures">
          <h2 id="read-signatures" className={ui.h3}>
            {t("read.signatures")}
          </h2>
          <ul className="flex flex-col gap-2">
            {p.signatures.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 text-sm">
                {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
                <img
                  src={`${files}/documents/${s.document_id}/content`}
                  alt={s.signer_name ?? t("signature.noName")}
                  className="h-12 w-auto rounded border border-border bg-paper"
                />
                <span>
                  {s.signer_name ?? t("signature.noName")}
                  {s.signer_role ? `, ${t(`roles.${s.signer_role}`)}` : ""}
                </span>
                <span className="text-xs text-muted">{t("read.signedAt", { date: germanDate(s.signed_at) })}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <a href={`${files}/pdf`} className={ui.button}>
          {p.finalized ? t("pdfFinal") : t("pdfDraft")}
        </a>
      </div>
      {p.access.valid_to ? <p className={ui.help}>{t("access.read", { date: germanDate(p.access.valid_to) })}</p> : null}
      {open != null && open >= 0 ? <PhotoLightbox photos={gallery} index={open} onClose={() => setOpen(null)} onIndex={setOpen} /> : null}
    </div>
  );
}
