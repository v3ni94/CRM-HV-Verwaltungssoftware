"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

const REMOTE_IMAGE = /<img\b[^>]*\bsrc\s*=\s*["']?\s*(?:https?:)?\/\//i;

/** Builds the document shown in the frame. The CSP allows no script, no frame, no font and no
 *  network request; images with a web address load only after the clerk asked for it (P12-02,
 *  tracking pixels). Exported for tests. */
export function mailFrameDocument(html: string, showImages: boolean): string {
  const images = showImages ? "https: data: cid:" : "data: cid:";
  const csp = `default-src 'none'; img-src ${images}; style-src 'unsafe-inline'`;
  return (
    `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${csp}">` +
    `<base target="_blank">` +
    `<style>body{margin:0;font:14px/1.5 system-ui,sans-serif;overflow-wrap:anywhere;word-break:break-word}` +
    `img{max-width:100%;height:auto}table{max-width:100%}pre{white-space:pre-wrap}</style>` +
    `</head><body>${html}</body></html>`
  );
}

/** Sanitised HTML mail in a sandboxed frame without scripts and without external resources.
 *  The caller still passes server side sanitised markup (defence in depth). */
export function MailHtmlFrame({ html, className = "", testId }: { html: string; className?: string; testId?: string }) {
  const t = useTranslations("Tickets.mailThread");
  const [showImages, setShowImages] = useState(false);
  const [height, setHeight] = useState(160);
  const hasRemote = REMOTE_IMAGE.test(html);
  return (
    <div className={`flex min-w-0 flex-col gap-2 ${className}`.trim()}>
      {hasRemote && !showImages ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <span>{t("imagesBlocked")}</span>
          <button type="button" className="underline" onClick={() => setShowImages(true)}>
            {t("loadImages")}
          </button>
        </div>
      ) : null}
      <iframe
        key={showImages ? "images" : "plain"}
        title={t("htmlFrameTitle")}
        data-testid={testId}
        sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        referrerPolicy="no-referrer"
        srcDoc={mailFrameDocument(html, showImages)}
        style={{ height, width: "100%", border: 0 }}
        onLoad={(e) => {
          try {
            const h = e.currentTarget.contentDocument?.documentElement.scrollHeight;
            if (h) setHeight(Math.min(Math.max(h + 4, 40), 4000));
          } catch {
            /* keep the default height */
          }
        }}
      />
    </div>
  );
}
