"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Sheet } from "@/components/ui/Sheet";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { Doc } from "./types";

export type PhotoGalleryProps = {
  open: boolean;
  onClose: () => void;
  docs: Doc[];
  /** Index of the photo to show first. */
  index: number;
  /** Caption prefix (the entry the photos belong to). */
  itemTitle?: string;
};

/** Full screen photo viewer (M31 WP2): one photo of an entry at a time, swipe with pointer
 *  events and arrow keys, counter "3 von 12", caption from the entry and the upload time.
 *  The image comes from the protected same-origin proxy; nothing is cached or stored. */
export function PhotoGallery({ open, onClose, docs, index, itemTitle }: PhotoGalleryProps) {
  const t = useTranslations("Handover");
  const [current, setCurrent] = useState(index);
  const start = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => {
    if (open) setCurrent(Math.min(Math.max(0, index), Math.max(0, docs.length - 1)));
  }, [open, index, docs.length]);
  const total = docs.length;
  const prev = () => setCurrent((c) => (c - 1 + total) % total);
  const next = () => setCurrent((c) => (c + 1) % total);

  useEffect(() => {
    if (!open || total < 2) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // prev and next only depend on total.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, total]);

  const doc = docs[current];
  if (!doc) return null;
  const caption = [itemTitle, doc.title !== doc.filename ? doc.title : null, formatDateTime(doc.created_at)].filter(Boolean).join(", ");
  return (
    <Sheet open={open} onClose={onClose} title={t("gallery.title")} size="full" flush testId="photo-gallery">
      <div
        className="flex h-full min-h-[60dvh] flex-col bg-fg/95 text-primary-fg"
        onPointerDown={(e) => {
          start.current = { x: e.clientX, y: e.clientY };
        }}
        onPointerUp={(e) => {
          const s = start.current;
          start.current = null;
          if (!s || total < 2) return;
          const dx = e.clientX - s.x;
          if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(e.clientY - s.y)) (dx > 0 ? prev : next)();
        }}
        data-testid="gallery-stage"
      >
        <div className="flex flex-1 items-center justify-center overflow-hidden p-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
          <img
            key={doc.id}
            src={`/api/handover-files/documents/${doc.id}/content`}
            alt={doc.title}
            className="max-h-[75dvh] max-w-full object-contain"
            decoding="async"
            data-testid="gallery-image"
          />
        </div>
        <div className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
          <button type="button" className={ui.iconButton} onClick={prev} aria-label={t("gallery.prev")} disabled={total < 2}>
            ‹
          </button>
          <div className="min-w-0 text-center">
            <div className={ui.num} data-testid="gallery-counter">
              {t("gallery.counter", { index: current + 1, total })}
            </div>
            <div className="truncate text-xs opacity-80">{caption}</div>
          </div>
          <button type="button" className={ui.iconButton} onClick={next} aria-label={t("gallery.next")} disabled={total < 2}>
            ›
          </button>
        </div>
      </div>
    </Sheet>
  );
}
