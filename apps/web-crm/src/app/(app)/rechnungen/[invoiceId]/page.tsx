import { getTranslations } from "next-intl/server";

import { InvoiceActions } from "@/components/invoices/InvoiceForms";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Review = { step: string; result: string; reason: string; decided_at: string; version: number };
type Line = { text: string | null; net: string; vat: string };

export default async function InvoicePage({ params }: { params: Promise<{ invoiceId: string }> }) {
  const { invoiceId } = await params;
  const t = await getTranslations("Invoices");
  const { data, error, response } = await serverApi().GET("/api/v1/accounting/invoices/{invoice_id}", {
    params: { path: { invoice_id: invoiceId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const d = data as Record<string, unknown>;
  const findings = (d.findings ?? []) as string[];
  const reviews = (d.reviews ?? []) as Review[];
  const lines = (d.lines ?? []) as Line[];
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">
        {t("invoice")} {String(d.number)} · V{String(d.version)}
      </h1>
      <p className="text-sm text-muted">
        {formatDate(String(d.invoice_date))} · {formatEur(String(d.gross))} · {t(`reviewStatus.${String(d.review_status)}`)} ·{" "}
        {t(`postingStatus.${String(d.posting_status)}`)}
        {d.payee_iban_suffix ? ` · IBAN …${String(d.payee_iban_suffix)}` : ""}
      </p>
      {findings.length ? (
        <section className={ui.notice} data-testid="findings">
          <h2 className="font-medium">{t("hintsTitle")}</h2>
          <ul className="list-inside list-disc">
            {findings.map((f) => <li key={f}>{f}</li>)}
          </ul>
        </section>
      ) : null}
      <table className="w-full border-collapse text-sm">
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} className="border-b border-border">
              <td className="py-1.5 pr-3">{l.text}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(l.net)}</td>
              <td className="py-1.5 text-right tabular-nums">{formatEur(l.vat)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <section className="flex flex-col gap-1">
        <h2 className="font-medium">{t("reviews")}</h2>
        <ul className="text-sm">
          {reviews.map((r, i) => (
            <li key={i}>
              {formatDateTime(r.decided_at)} · V{r.version} · {t(`steps.${r.step}`)}: {t(`results.${r.result}`)} · {r.reason}
            </li>
          ))}
        </ul>
      </section>
      <InvoiceActions
        id={invoiceId}
        reviewStatus={String(d.review_status)}
        postingStatus={String(d.posting_status)}
        released={Boolean(d.released)}
        ibanOpen={Boolean(d.payee_iban_suffix) && !d.iban_confirmed && findings.some((f) => f.startsWith("IBAN"))}
      />
    </div>
  );
}
