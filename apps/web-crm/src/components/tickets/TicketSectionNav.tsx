"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ui } from "@/lib/ui";

export const TICKET_SECTIONS = [
  "bearbeiten",
  "checkliste",
  "mail",
  "anhaenge",
  "auftraege",
  "vorschlaege",
  "schaden",
  "beirat",
  "kommentare",
  "verlauf",
  "dokumente",
] as const;
export type TicketSection = (typeof TICKET_SECTIONS)[number];

/** Anchor navigation of the ticket detail (M31 WP3): one swipeable row on phones that sticks
 *  below the app header up to `lg`, so comments and history are two taps away. An
 *  IntersectionObserver marks the section in view; without one (old browsers, jsdom) the
 *  links still work as plain anchors. Nothing is stored. */
export function TicketSectionNav({ sections }: { sections: readonly TicketSection[] }) {
  const t = useTranslations("Tickets.sections");
  const [active, setActive] = useState<TicketSection | null>(null);

  useEffect(() => {
    if (sections.length === 0) return;
    let observer: IntersectionObserver | null = null;
    try {
      if (typeof IntersectionObserver === "undefined") return;
      observer = new IntersectionObserver(
        (entries) => {
          const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
          const first = visible[0];
          if (first && sections.includes(first.target.id as TicketSection)) setActive(first.target.id as TicketSection);
        },
        { rootMargin: "-120px 0px -60% 0px", threshold: 0 },
      );
      for (const id of sections) {
        const node = document.getElementById(id);
        if (node) observer.observe(node);
      }
    } catch {
      observer = null;
    }
    return () => observer?.disconnect();
  }, [sections]);

  if (sections.length === 0) return null;
  return (
    <nav
      aria-label={t("label")}
      className={`${ui.tabBar} sticky top-[var(--mhvp-header-h)] z-20 border-b border-border-soft bg-bg py-1 lg:static lg:border-0 lg:py-0`}
      data-testid="ticket-section-nav"
    >
      {sections.map((id) => (
        <a key={id} href={`#${id}`} className={id === active ? ui.tabActive : ui.tab} aria-current={id === active ? "location" : undefined} data-testid={`ticket-section-link-${id}`}>
          {t(id)}
        </a>
      ))}
    </nav>
  );
}
