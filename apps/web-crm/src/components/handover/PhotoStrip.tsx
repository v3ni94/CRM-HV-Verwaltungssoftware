"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { useConfirm } from "@/components/ui/ConfirmSheet";

import { PhotoGallery } from "./PhotoGallery";
import type { Doc } from "./types";

export type PhotoStripProps = {
  docs: Doc[];
  /** Title of the entry the photos belong to (gallery caption). */
  itemTitle?: string;
  /** Remove handler; absent on locked protocols. Called after the confirmation. */
  onRemove?: (doc: Doc) => Promise<void>;
};

/** Thumbnails of one entry (M31 WP2): 96 px tiles from the derived thumbnail path (no
 *  browser cache), a tap opens the gallery, removing asks with the exact deletion text
 *  (link of this version only, file deleted once no version links it). */
export function PhotoStrip({ docs, itemTitle, onRemove }: PhotoStripProps) {
  const t = useTranslations("Handover");
  const { confirm, confirmSheet } = useConfirm();
  const [openAt, setOpenAt] = useState<number | null>(null);
  if (docs.length === 0) return null;
  return (
    <div data-testid="photo-strip">
      <ul className="grid grid-cols-3 gap-2 sm:flex sm:flex-wrap">
        {docs.map((d, index) => (
          <li key={d.id} className="relative h-24 w-24">
            <button
              type="button"
              className="block h-24 w-24 overflow-hidden rounded-md border border-border"
              onClick={() => setOpenAt(index)}
              aria-label={`${t("photos.open")}: ${d.title}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
              <img
                src={`/api/handover-files/${(d.thumbnail_url ?? `/api/v1/documents/${d.id}/content`).replace(/^\/api\/v1\//, "")}`}
                alt={d.title}
                className="h-24 w-24 object-cover"
                loading="lazy"
                decoding="async"
              />
            </button>
            {onRemove ? (
              <button
                type="button"
                className="absolute -right-2 -top-2 flex h-11 w-11 items-center justify-center rounded-full text-fg"
                aria-label={`${t("photos.remove")}: ${d.title}`}
                onClick={async () => {
                  const ok = await confirm({
                    title: t("photos.confirmRemoveTitle"),
                    text: t("photos.confirmRemove"),
                    confirmLabel: t("delete"),
                    danger: true,
                  });
                  if (ok) await onRemove(d);
                }}
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-surface text-sm shadow-card" aria-hidden="true">
                  ×
                </span>
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {confirmSheet}
      <PhotoGallery open={openAt !== null} onClose={() => setOpenAt(null)} docs={docs} index={openAt ?? 0} itemTitle={itemTitle} />
    </div>
  );
}
