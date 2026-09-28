"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import type { ChatLink } from "@/lib/ai";

/** Only internal CRM paths are rendered as links; anything else is shown as text. */
export function isCrmPath(href: string): boolean {
  return href.startsWith("/") && !href.startsWith("//");
}

/** Records and pages the platform lookup found for an answer (rule AI-LOOKUP-01). The links
 *  come from the platform, never from the model. */
export function ChatLinks({ links }: { links: ChatLink[] | undefined | null }) {
  const t = useTranslations("AiChat");
  if (!links?.length) return null;
  return (
    <div className="mt-2" data-testid="chat-links">
      <p className="text-xs font-medium text-muted">{t("linksTitle")}</p>
      <ul className="mt-1 flex flex-col gap-1">
        {links.map((link) => (
          <li key={`${link.type}:${link.id}`} className="text-sm">
            <span className="mr-1 text-xs text-muted">{t(`linkType.${link.type}`)}</span>
            {isCrmPath(link.href) ? (
              <Link href={link.href} className="font-medium underline">
                {link.label}
              </Link>
            ) : (
              <span className="font-medium">{link.label}</span>
            )}
            {link.detail ? <span className="text-xs text-muted">{` (${link.detail})`}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
