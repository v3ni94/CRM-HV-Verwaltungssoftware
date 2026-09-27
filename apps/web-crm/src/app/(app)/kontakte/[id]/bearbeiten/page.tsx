import { getTranslations } from "next-intl/server";

import { ContactForm } from "@/components/contacts/ContactForm";

import { loadContact } from "../load";
import { loadRetentionProfiles } from "../../retention-profiles";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function EditContactPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, t, retentionProfiles] = await Promise.all([
    params,
    getTranslations("ContactForm"),
    loadRetentionProfiles(),
  ]);
  const contact = await loadContact(id);
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>
        {t("titleEdit")}: {contact.display_name}
      </h1>
      <ContactForm mode="edit" contact={contact} retentionProfiles={retentionProfiles} />
    </div>
  );
}
