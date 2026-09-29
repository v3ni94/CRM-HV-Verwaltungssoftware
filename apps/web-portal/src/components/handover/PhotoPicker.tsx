"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";

import { ui } from "@/lib/ui";

/** Upload state of one chosen file (M31 WP5, portal twin of the CRM picker). */
export type PhotoStatus = "queued" | "uploading" | "done" | "failed";
export type PhotoJob = { key: string; name: string; status: PhotoStatus; message?: string };

/** Two inputs on purpose: `capture="environment"` opens the camera straight away on phones,
 *  the second input opens the gallery (Fotos on iPhone, Google Fotos on Android). HEIC and
 *  HEIF are listed so iPhone photos appear in the picker; the server converts them (M30-04). */
export const ACCEPT = "image/jpeg,image/png,image/heic,image/heif";

export function PhotoPicker({
  onFiles,
  jobs = [],
  onRetry,
  disabled,
  compact,
}: {
  onFiles: (files: File[]) => void;
  jobs?: PhotoJob[];
  onRetry?: (job: PhotoJob) => void;
  disabled?: boolean;
  /** Small buttons inside a list card. */
  compact?: boolean;
}) {
  const t = useTranslations("Handover");
  const id = useId();
  const cls = compact ? ui.buttonSm : ui.button;
  function pick(list: FileList | null, input: HTMLInputElement) {
    const files = list ? Array.from(list) : [];
    input.value = "";
    if (files.length) onFiles(files);
  }
  return (
    <div className="flex flex-col gap-2" data-testid="photo-picker">
      <div className="flex flex-wrap gap-2">
        <label htmlFor={`${id}-camera`} className={`${cls} ${disabled ? "pointer-events-none opacity-50" : "cursor-pointer"}`}>
          {t("photos.camera")}
          <input
            id={`${id}-camera`}
            type="file"
            accept={ACCEPT}
            capture="environment"
            className="sr-only"
            data-testid="photo-input-camera"
            onChange={(e) => pick(e.target.files, e.target)}
            disabled={disabled}
          />
        </label>
        <label htmlFor={`${id}-gallery`} className={`${cls} ${disabled ? "pointer-events-none opacity-50" : "cursor-pointer"}`}>
          {t("photos.gallery")}
          <input
            id={`${id}-gallery`}
            type="file"
            accept={ACCEPT}
            multiple
            className="sr-only"
            data-testid="photo-input-gallery"
            onChange={(e) => pick(e.target.files, e.target)}
            disabled={disabled}
          />
        </label>
      </div>
      {jobs.length > 0 ? (
        <ul className="flex flex-col gap-1 text-xs" aria-live="polite">
          {jobs.map((job) => (
            <li key={job.key} className="flex flex-wrap items-center gap-2" data-status={job.status}>
              <span className="truncate">{job.name}</span>
              <span
                className={
                  job.status === "done"
                    ? ui.badgeSuccess
                    : job.status === "failed"
                      ? ui.badgeDanger
                      : job.status === "uploading"
                        ? ui.badgeInfo
                        : ui.badge
                }
              >
                {t(`photos.status.${job.status}`)}
              </span>
              {job.message ? <span className="text-danger-fg">{job.message}</span> : null}
              {job.status === "failed" && onRetry ? (
                <button type="button" className={ui.buttonSm} onClick={() => onRetry(job)}>
                  {t("photos.retry")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
