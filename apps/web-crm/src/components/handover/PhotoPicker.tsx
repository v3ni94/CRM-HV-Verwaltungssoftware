"use client";

import { useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef } from "react";

import { ui } from "@/lib/ui";

export type PhotoPickerProps = {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
  /** One file at a time (the camera input is always single). */
  single?: boolean;
};

const GALLERY_ACCEPT = "image/jpeg,image/png,image/heic,image/heif";

/** Camera and gallery inputs for a new entry (M31 WP2, capture first): the files live only in
 *  the component state until the parent uploads them; previews use object URLs that are
 *  revoked on unmount. No browser storage. */
export function PhotoPicker({ files, onChange, disabled = false, single = false }: PhotoPickerProps) {
  const t = useTranslations("Handover");
  const id = useId();
  const previews = useMemo(() => files.map((f) => ({ file: f, url: URL.createObjectURL(f) })), [files]);
  const previewsRef = useRef(previews);
  previewsRef.current = previews;
  useEffect(
    () => () => {
      for (const p of previewsRef.current) URL.revokeObjectURL(p.url);
    },
    [],
  );
  useEffect(() => {
    // Revoke the URLs of a previous file list once a new one replaces it.
    return () => {
      for (const p of previews) URL.revokeObjectURL(p.url);
    };
  }, [previews]);

  function add(list: FileList | null) {
    if (!list?.length) return;
    const picked = Array.from(list);
    onChange(single ? picked.slice(0, 1) : [...files, ...picked]);
  }

  return (
    <div className="flex flex-col gap-2" data-testid="photo-picker">
      <div className={ui.formActions}>
        <label className={`${ui.button} ${ui.actionFull} cursor-pointer`}>
          {t("photos.capture")}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            disabled={disabled}
            data-testid="photo-capture"
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        <label className={`${ui.button} ${ui.actionFull} cursor-pointer`}>
          {t("photos.pick")}
          <input
            type="file"
            accept={GALLERY_ACCEPT}
            multiple={!single}
            className="sr-only"
            disabled={disabled}
            data-testid="photo-pick"
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {previews.length ? (
        <ul className="grid grid-cols-3 gap-2 sm:flex sm:flex-wrap" aria-label={t("photos.pending")}>
          {previews.map((p, index) => (
            <li key={`${id}-${index}`} className="relative h-24 w-24">
              {/* eslint-disable-next-line @next/next/no-img-element -- local object URL preview */}
              <img src={p.url} alt={p.file.name} className="h-24 w-24 rounded-md border border-border object-cover" />
              <button
                type="button"
                className="absolute -right-2 -top-2 flex h-11 w-11 items-center justify-center rounded-full text-fg"
                aria-label={`${t("photos.removeFile")}: ${p.file.name}`}
                disabled={disabled}
                onClick={() => onChange(files.filter((_, i) => i !== index))}
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-surface text-sm shadow-card" aria-hidden="true">
                  ×
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
