"use client";
/** "Bemerkungen und Mahnsperre" of a contract edited in place via PATCH `/contracts/{id}/notes`
 *  (AP8, operator decision: only remarks and the dunning block change without a new contract
 *  version). A dunning block needs a reason: switching it on without one keeps the switch
 *  pending until the reason is entered, then both fields go out in one request. */
import { useState } from "react";
import { useTranslations } from "next-intl";

import { EditableSection } from "@/components/common/EditableSection";
import { InlineField } from "@/components/common/InlineField";
import { useAutosave } from "@/components/common/useAutosave";

export type ContractNotesValues = {
  id: string;
  notes?: string | null;
  dunning_block: boolean;
  dunning_block_reason?: string | null;
};

export function ContractNotesSection({ contract, canEdit }: { contract: ContractNotesValues; canEdit: boolean }) {
  const t = useTranslations("ContractForm");
  const [values, setValues] = useState<ContractNotesValues>(contract);
  // True while the block is switched on but the reason is still missing (not sent yet).
  const [pendingBlock, setPendingBlock] = useState(false);
  const autosave = useAutosave<ContractNotesValues & { version?: number }>({
    path: `contracts/${contract.id}/notes`,
    version: null,
    body: (field, value) => (field === "dunning_block_reason" && pendingBlock ? { dunning_block: true, dunning_block_reason: value } : { [field]: value }),
    onSaved: (data) => {
      setPendingBlock(false);
      setValues((prev) => ({ ...prev, ...data }));
    },
  });
  const blocked = values.dunning_block || pendingBlock;
  const reasonMissing = pendingBlock && !(values.dunning_block_reason ?? "").trim();

  const save = (name: string, value: unknown) => {
    if (name === "dunning_block") {
      if (value === true && !(values.dunning_block_reason ?? "").trim()) {
        setPendingBlock(true);
        return;
      }
      setPendingBlock(false);
    }
    autosave.save(name, value);
  };
  const reasonState = reasonMissing ? { status: "error" as const, message: t("notesSection.reasonRequired") } : autosave.fieldState("dunning_block_reason");

  return (
    <EditableSection
      title={t("notesSection.title")}
      description={t("notesSection.description")}
      canEdit={canEdit}
      status={autosave.status}
      conflict={autosave.conflict}
      onEditingChange={(editing) => {
        if (!editing) void autosave.flush();
      }}
      testId="contract-notes"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <InlineField name="dunning_block" label={t("fields.dunningBlock")} type="boolean" value={blocked} onSave={save} state={autosave.fieldState("dunning_block")} />
        <InlineField
          name="dunning_block_reason"
          label={t("fields.dunningBlockReason")}
          value={values.dunning_block_reason}
          onSave={save}
          state={reasonState}
          required={blocked}
          help={blocked ? t("notesSection.reasonHelp") : undefined}
          editing={reasonMissing ? true : undefined}
          maxLength={500}
        />
        <InlineField name="notes" label={t("fields.notes")} type="textarea" rows={4} value={values.notes} onSave={save} state={autosave.fieldState("notes")} className="flex flex-col gap-1 sm:col-span-2" />
      </div>
    </EditableSection>
  );
}
