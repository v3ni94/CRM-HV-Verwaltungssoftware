import { getTranslations } from "next-intl/server";

import { ContactForm } from "@/components/contacts/ContactForm";
import { ui } from "@/lib/ui";

import { loadRetentionProfiles } from "../retention-profiles";

export const dynamic = "force-dynamic";

export default async function NewContactPage() {
  const [t, retentionProfiles] = await Promise.all([
    getTranslations("ContactForm"),
    loadRetentionProfiles(),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("titleNew")}</h1>
      <ContactForm mode="create" retentionProfiles={retentionProfiles} />
    </div>
  );
}
