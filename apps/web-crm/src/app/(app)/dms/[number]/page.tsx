import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { DmsDocuments } from "@/components/dms/DmsDocuments";
import { DmsPersonExport } from "@/components/dms/DmsPersonExport";
import { DmsPersonProposal } from "@/components/dms/DmsPersonProposal";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import type { DmsObjectDetail } from "@/lib/objektakte-dms";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** M29 Stufe 4: detail of one object from objektakte: missing documents, open review cases by
 *  type, document list with the jump into Google Drive, owner and tenant list as import
 *  proposal. */
export default async function DmsObjectPage({ params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const t = await getTranslations("Dms");
  const { data, error, response } = await serverApi().GET("/api/v1/integrations/objektakte/objects/{number}", {
    params: { path: { number } },
  });
  redirectIfUnauthenticated(response);
  const detail = data as DmsObjectDetail | undefined;
  const breadcrumb = [{ href: "/dms", label: t("title") }, { label: number }];

  if (!detail) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader eyebrow={t("area")} title={t("detail.title", { number })} breadcrumb={breadcrumb} />
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      </div>
    );
  }

  const address = detail.address;
  const addressLine = address
    ? [[address.street, address.house_number].filter(Boolean).join(" "), [address.zip, address.city].filter(Boolean).join(" ")]
        .filter(Boolean)
        .join(", ")
    : "";
  const missing = detail.missing_documents ?? [];
  const cases = Object.entries(detail.open_cases_by_type ?? {});
  const c = detail.completeness;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={t("area")}
        title={`${detail.number} ${detail.name}`}
        description={addressLine || undefined}
        breadcrumb={breadcrumb}
        action={
          <div className={ui.formActions}>
            {detail.drive_folder_url ? (
              <a href={detail.drive_folder_url} target="_blank" rel="noopener noreferrer" className={ui.primary}>
                {t("detail.openDrive")}
              </a>
            ) : null}
            {detail.property_id ? (
              <Link href={`/objekte/${detail.property_id}`} className={ui.secondary}>
                {t("detail.openProperty")}
              </Link>
            ) : null}
          </div>
        }
      />
      {detail.property_id ? null : <p className={ui.notice}>{t("detail.noProperty")}</p>}
      <div className="grid gap-4 md:grid-cols-3">
        <section className={ui.card}>
          <h2 className="mhvp-label">{t("detail.status")}</h2>
          <p className="mt-2 text-sm font-medium">{detail.takeover_status}</p>
          <p className="mt-1 text-xs text-muted">{t("detail.crmDocuments", { count: detail.crm_document_count })}</p>
        </section>
        <section className={ui.card}>
          <h2 className="mhvp-label">{t("detail.completeness")}</h2>
          <p className="mt-2 text-sm font-medium tabular-nums">
            {t("tile.present", { present: c.present, required: c.required })}
          </p>
        </section>
        <section className={ui.card}>
          <h2 className="mhvp-label">{t("detail.openCases")}</h2>
          <p className="mt-2 text-sm font-medium tabular-nums">{detail.open_review_cases}</p>
          {cases.length > 0 ? (
            <ul className="mt-1 flex flex-col gap-0.5 text-xs text-muted">
              {cases.map(([type, count]) => (
                <li key={type}>
                  {type}: {count}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
      <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("detail.missing")}>
        <h2 className={ui.h2}>{t("detail.missing")}</h2>
        {missing.length === 0 ? (
          <p className="text-sm text-muted">{t("detail.noneMissing")}</p>
        ) : (
          <ul className="flex flex-col gap-1" data-testid="dms-missing">
            {missing.map((m, index) => (
              <li key={`${m.category}-${m.label}-${index}`} className="text-sm">
                {m.label}
                <span className="text-xs text-muted"> ({[m.category, m.subfolder].filter(Boolean).join(" / ")})</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <DmsDocuments number={detail.number} />
      {detail.property_id ? <DmsPersonExport number={detail.number} /> : null}
      {detail.property_id ? <DmsPersonProposal number={detail.number} /> : null}
    </div>
  );
}
