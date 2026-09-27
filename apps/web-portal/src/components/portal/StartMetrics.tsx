"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { ui } from "@/lib/ui";

/** Kennzahlen der Startseite. Jede Kennzahl ist optional: schlägt der zugehörige Abruf auf der
 *  Server-Seite fehl oder passt er nicht zur Rolle, bleibt sie einfach weg und die Startseite
 *  rendert unverändert weiter. */
export type StartMetricsData = {
  /** Eigene Meldungen, deren Status nicht abgeschlossen ist (M21). */
  openTickets?: number;
  /** Offene Terminvorschläge (Status proposed) zu eigenen Meldungen (A58). */
  openProposals?: number;
  /** Summe der offenen Posten des Kontoauszugs, fertig formatiert als 1.234,56 EUR. */
  openBalance?: string;
  /** Freigegebene Dokumente. */
  documents?: number;
  /** Aufträge des Dienstleisters, die noch nicht begonnen wurden (M22). */
  ordersOpen?: number;
  /** Aufträge des Dienstleisters in Ausführung (M22). */
  ordersInProgress?: number;
  /** Prüfaufträge des Verwaltungsbeirats (A52). */
  boardEngagements?: number;
};

type MetricKey = keyof StartMetricsData;

const METRIC_LINKS: Record<MetricKey, string> = {
  openTickets: "/meldungen",
  openProposals: "/meldungen",
  openBalance: "/konto",
  documents: "/dokumente",
  ordersOpen: "/auftraege",
  ordersInProgress: "/auftraege",
  boardEngagements: "/pruefung",
};

const METRIC_ORDER: MetricKey[] = [
  "openTickets",
  "openProposals",
  "openBalance",
  "documents",
  "ordersOpen",
  "ordersInProgress",
  "boardEngagements",
];

/** Kompakte Kennzahlen-Kacheln über den Rollenkacheln: Zahl plus Beschriftung, jede Kachel
 *  verlinkt auf die zugehörige Seite. Ohne eine einzige Kennzahl wird nichts gerendert. */
export function StartMetrics({ metrics }: { metrics: StartMetricsData }) {
  const t = useTranslations("Dashboard");
  const cards = METRIC_ORDER.filter((key) => metrics[key] !== undefined).map((key) => ({
    key,
    href: METRIC_LINKS[key],
    value: String(metrics[key]),
    label: t(key),
  }));
  if (cards.length === 0) return null;
  return (
    <section aria-labelledby="start-metrics-heading" data-testid="start-metrics">
      <h2 id="start-metrics-heading" className={ui.srOnly}>
        {t("heading")}
      </h2>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {cards.map((card) => (
          <li key={card.key}>
            <Link href={card.href} className={`${ui.cardLink} flex h-full flex-col gap-1`}>
              <span className="text-2xl font-semibold tabular-nums">{card.value}</span>
              <span className="text-sm text-muted">{card.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
