"use client";
/** Contact master data edited in place (ADR 0012, AP8): every field is one PATCH
 *  `/contacts/{id}` with `If-Match` from the contact version; a 412 shows the conflict notice.
 *  Addresses, phones, e-mails, bank accounts, types, roles and tags keep the form (PUT). */
import { useState } from "react";
import { useTranslations } from "next-intl";

import { EditableSection } from "@/components/common/EditableSection";
import { InlineField, type InlineOption } from "@/components/common/InlineField";
import { useAutosave } from "@/components/common/useAutosave";

export type ContactMasterDataValues = {
  id: string;
  version: number;
  kind: "person" | "company";
  salutation?: string | null;
  letter_salutation?: string | null;
  title?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  company_name?: string | null;
  legal_form?: string | null;
  position?: string | null;
  date_of_birth?: string | null;
  language?: string | null;
  preferred_channel?: "post" | "email" | "portal" | null;
  notes?: string | null;
};

const CHANNELS = ["post", "email", "portal"] as const;

export function ContactMasterData({ contact, canEdit }: { contact: ContactMasterDataValues; canEdit: boolean }) {
  const t = useTranslations("Contacts");
  const tf = useTranslations("ContactForm");
  const tl = useTranslations("Labels");
  const [values, setValues] = useState<ContactMasterDataValues>(contact);
  const autosave = useAutosave<ContactMasterDataValues>({
    path: `contacts/${contact.id}`,
    version: contact.version,
    onSaved: (data) => setValues((prev) => ({ ...prev, ...data })),
  });
  const channels: InlineOption[] = CHANNELS.map((value) => ({ value, label: tl(`channel.${value}`) }));
  const field = (name: keyof ContactMasterDataValues) => ({
    name,
    value: values[name] as string | null | undefined,
    onSave: autosave.save,
    state: autosave.fieldState(name),
  });
  const person = values.kind === "person";

  return (
    <EditableSection
      title={t("masterData.title")}
      description={t("masterData.description")}
      canEdit={canEdit}
      status={autosave.status}
      conflict={autosave.conflict}
      onEditingChange={(editing) => {
        if (!editing) void autosave.flush();
      }}
      testId="contact-master-data"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {person ? (
          <>
            <InlineField {...field("salutation")} label={tf("salutation")} maxLength={50} />
            <InlineField {...field("title")} label={tf("title")} maxLength={50} />
            <InlineField {...field("first_name")} label={tf("firstName")} maxLength={100} />
            <InlineField {...field("last_name")} label={tf("lastName")} maxLength={100} required />
            <InlineField {...field("date_of_birth")} label={tf("dateOfBirth")} type="date" />
          </>
        ) : (
          <>
            <InlineField {...field("company_name")} label={tf("companyName")} maxLength={200} required />
            <InlineField {...field("legal_form")} label={tf("legalForm")} maxLength={50} />
          </>
        )}
        <InlineField {...field("letter_salutation")} label={tf("letterSalutation")} maxLength={200} />
        <InlineField {...field("position")} label={tf("position")} maxLength={100} />
        <InlineField {...field("language")} label={tf("language")} maxLength={10} required />
        <InlineField {...field("preferred_channel")} label={tf("preferredChannel")} type="select" options={channels} />
        <InlineField {...field("notes")} label={tf("notes")} type="textarea" rows={4} className="flex flex-col gap-1 sm:col-span-2" />
      </div>
    </EditableSection>
  );
}
