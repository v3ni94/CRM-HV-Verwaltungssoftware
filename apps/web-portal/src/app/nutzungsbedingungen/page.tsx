import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { AuthCard } from "@/components/auth/AuthCard";
import { TermsAcceptForm } from "@/components/auth/TermsAcceptForm";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Annahme der Nutzungsbedingungen nach der Anmeldung (AC06, GA02-06). Ohne veröffentlichte
 *  Fassung oder bei bereits erfolgter Annahme geht es direkt zur Startseite. */
export default async function TermsPage() {
  const t = await getTranslations("Terms");
  const response = await serverFetch("/api/v1/portal/terms");
  redirectIfUnauthenticated(response);
  if (!response.ok) {
    return (
      <AuthCard title={t("title")}>
        <p role="alert" className="text-sm">
          {t("loadFailed")}
        </p>
      </AuthCard>
    );
  }
  const status = (await response.json()) as { terms_version: string | null; accepted: boolean };
  if (!status.terms_version || status.accepted) redirect("/start");
  return (
    <AuthCard title={t("title")}>
      <TermsAcceptForm version={status.terms_version} />
    </AuthCard>
  );
}
