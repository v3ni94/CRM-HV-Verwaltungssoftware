"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";

/** Einladungslink zum Portal als Text und QR-Code (A56). Der QR-Code wird im Browser mit der
 *  bereits vorhandenen Bibliothek "qrcode" erzeugt (dieselbe wie beim zweiten Faktor); ohne
 *  konfigurierte Portaladresse gibt es keinen Link und die Komponente zeigt nichts. Die
 *  Beschriftungen kommen vom Aufrufer, damit die Komponente ohne Übersetzungskontext läuft. */
export function InvitationQr({ url, title, alt }: { url: string | null | undefined; title: string; alt: string }) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDataUrl(null);
    if (!url) return;
    QRCode.toDataURL(url, { margin: 1, width: 180 })
      .then((png) => {
        if (!cancelled) setDataUrl(png);
      })
      .catch(() => {
        if (!cancelled) setDataUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (!url) return null;
  return (
    <div className="mt-2 flex flex-col gap-1" data-testid="invitation-qr">
      <p className="text-xs text-muted">{title}</p>
      <a href={url} className="break-all text-xs underline" target="_blank" rel="noreferrer">
        {url}
      </a>
      {dataUrl ? (
        // The QR image is generated locally as a data URL; next/image adds nothing here.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={dataUrl} width={180} height={180} alt={alt} className="mt-1 rounded bg-white p-1" />
      ) : null}
    </div>
  );
}
