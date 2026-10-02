/* eslint-disable jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions, jsx-a11y/no-noninteractive-element-interactions -- backdrop/stop-propagation clicks and swipe are pointer shortcuts only; the keyboard path is Escape, focus trap and the labelled buttons */
"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ui } from "@/lib/ui";

export type LightboxPhoto = { id: string; src: string; title: string };

/** Full screen photo viewer (M31 WP5): the portal must not leave the installed app for a photo
 *  (a `target="_blank"` tab loses the session on iOS in standalone mode), so photos open in a
 *  modal dialog with previous and next, Escape and a close button. The image is the same
 *  protected same origin blob as in the grid, never cached (no-store on portal-files). */
export function PhotoLightbox({
  photos,
  index,
  onClose,
  onIndex,
}: {
  photos: LightboxPhoto[];
  index: number;
  onClose: () => void;
  onIndex: (next: number) => void;
}) {
  const t = useTranslations("Handover");
  const closeRef = useRef<HTMLButtonElement>(null);
  const [touchX, setTouchX] = useState<number | null>(null);
  const photo = photos[index];
  const count = photos.length;

  useEffect(() => {
    closeRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
      if (e.key === "ArrowRight" && index < count - 1) onIndex(index + 1);
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [index, count, onClose, onIndex]);

  if (!photo) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={photo.title}
      data-testid="photo-lightbox"
      className="fixed inset-0 z-50 flex flex-col bg-black/90 text-white"
      style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}
      onClick={onClose}
      onTouchStart={(e) => setTouchX(e.touches[0]?.clientX ?? null)}
      onTouchEnd={(e) => {
        const end = e.changedTouches[0]?.clientX;
        if (touchX == null || end == null) return;
        if (end - touchX > 50 && index > 0) onIndex(index - 1);
        if (touchX - end > 50 && index < count - 1) onIndex(index + 1);
        setTouchX(null);
      }}
    >
      <div className="flex items-center justify-between gap-2 px-4 py-2" onClick={(e) => e.stopPropagation()}>
        <span className="truncate text-sm">
          {photo.title}
          {count > 1 ? ` · ${t("lightbox.counter", { index: index + 1, count })}` : ""}
        </span>
        <button
          ref={closeRef}
          type="button"
          className={`${ui.button} border-white/30 bg-transparent text-white hover:bg-white/10`}
          onClick={onClose}
        >
          {t("lightbox.close")}
        </button>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center p-2">
        {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
        <img src={photo.src} alt={photo.title} className="max-h-full max-w-full object-contain" onClick={(e) => e.stopPropagation()} />
      </div>
      {count > 1 ? (
        <div className="flex justify-between gap-2 px-4 py-2" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            className={`${ui.button} border-white/30 bg-transparent text-white hover:bg-white/10`}
            disabled={index === 0}
            onClick={() => onIndex(index - 1)}
          >
            {t("lightbox.previous")}
          </button>
          <button
            type="button"
            className={`${ui.button} border-white/30 bg-transparent text-white hover:bg-white/10`}
            disabled={index === count - 1}
            onClick={() => onIndex(index + 1)}
          >
            {t("lightbox.next")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
