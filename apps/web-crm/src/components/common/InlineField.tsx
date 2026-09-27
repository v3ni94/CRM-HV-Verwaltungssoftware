"use client";
/** One master data field that shows its value and, in edit mode, an input that saves itself
 *  (ADR 0012). Edit mode comes from the surrounding `EditableSection` ("Bearbeiten") or from the
 *  pencil next to the value. Text, number and date save on blur or Enter (Escape cancels),
 *  textarea on blur or Ctrl+Enter, select and boolean on change. The save state and the
 *  validation message (problem details, ADR 0004) appear under the field. */
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { PencilIcon, useEditableSection } from "./EditableSection";
import type { FieldState } from "./useAutosave";

export type InlineFieldType = "text" | "number" | "date" | "select" | "textarea" | "boolean";
export type InlineOption = { value: string; label: string };
export type InlineValue = string | number | boolean | null | undefined;

export type InlineFieldProps = {
  /** API field name; the key of the PATCH body. */
  name: string;
  label: string;
  type?: InlineFieldType;
  value: InlineValue;
  /** Choices of a select; the view mode shows the matching label. */
  options?: InlineOption[];
  /** Receives the converted value (string, number, boolean or null); usually `autosave.save`. */
  onSave: (name: string, value: unknown) => void;
  /** Save state of this field, usually `autosave.fieldState(name)`. */
  state?: FieldState;
  /** Forces the edit mode regardless of the section. */
  editing?: boolean;
  /** Overrides the write permission of the section. */
  canEdit?: boolean;
  /** Numbers are sent as string by default (NUMERIC fields, no float); `"number"` for integers. */
  numberAs?: "string" | "number";
  /** Custom view text; default: date formatted, boolean Ja/Nein, option label, else the value. */
  format?: (value: InlineValue) => string;
  /** Client side check before the save; returns the message or null. */
  validate?: (value: unknown) => string | null;
  /** Empty input is sent as null (default true) or as empty string. */
  emptyAsNull?: boolean;
  placeholder?: string;
  help?: string;
  required?: boolean;
  min?: number | string;
  max?: number | string;
  step?: number | string;
  maxLength?: number;
  rows?: number;
  className?: string;
  testId?: string;
};

function toDraft(value: InlineValue): string {
  if (value == null) return "";
  return String(value);
}

export function InlineField({
  name,
  label,
  type = "text",
  value,
  options = [],
  onSave,
  state,
  editing: editingProp,
  canEdit: canEditProp,
  numberAs = "string",
  format,
  validate,
  emptyAsNull = true,
  placeholder,
  help,
  required = false,
  min,
  max,
  step,
  maxLength,
  rows = 3,
  className,
  testId,
}: InlineFieldProps) {
  const t = useTranslations("Inline");
  const section = useEditableSection();
  const id = useId();
  const canEdit = canEditProp ?? section.canEdit;
  const [local, setLocal] = useState(false);
  const editing = canEdit && (editingProp ?? (section.editing || local));
  const [draft, setDraft] = useState(toDraft(value));
  const [clientError, setClientError] = useState<string | null>(null);
  const lastSent = useRef<string | null>(null);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null>(null);

  // Server values (e.g. after a save of another field) refresh the draft while nothing is typed.
  useEffect(() => {
    if (document.activeElement !== inputRef.current) setDraft(toDraft(value));
  }, [value]);

  useEffect(() => {
    if (local && editing) inputRef.current?.focus();
  }, [local, editing]);

  const convert = (raw: string): unknown => {
    const text = raw.trim();
    if (text === "") return emptyAsNull ? null : "";
    if (type === "number") return numberAs === "number" ? Number(text) : text;
    return type === "textarea" ? raw : text;
  };

  const commit = (raw: string) => {
    if (raw === toDraft(value) || raw === lastSent.current) return;
    if (required && raw.trim() === "") {
      setClientError(t("required"));
      return;
    }
    const next = convert(raw);
    if (type === "number" && typeof next === "string" && next !== "" && Number.isNaN(Number(next))) {
      setClientError(t("invalidNumber"));
      return;
    }
    const message = validate?.(next) ?? null;
    setClientError(message);
    if (message) return;
    lastSent.current = raw;
    onSave(name, next);
  };

  const cancel = () => {
    setDraft(toDraft(value));
    setClientError(null);
    setLocal(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      cancel();
      return;
    }
    const enter = event.key === "Enter" && (type !== "textarea" || event.ctrlKey || event.metaKey);
    if (enter) {
      event.preventDefault();
      commit(draft);
      if (local) setLocal(false);
    }
  };

  const onBlur = () => {
    commit(draft);
    if (local) setLocal(false);
  };

  const viewText = (): string => {
    if (format) return format(value);
    if (value == null || value === "") return t("empty");
    if (type === "boolean") return value ? t("yes") : t("no");
    if (type === "date") return formatDate(String(value));
    if (type === "select") return options.find((o) => o.value === String(value))?.label ?? String(value);
    return String(value);
  };

  const status = state?.status ?? "idle";
  const message = clientError ?? (status === "error" || status === "conflict" ? state?.message : null);
  const statusText = status === "saving" || status === "saved" ? t(`status.${status}`) : null;
  const inputClass = `${ui.input}${message ? " border-danger-fg" : ""}`;
  const describedBy = [help ? `${id}-help` : null, message ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;

  let control: React.ReactNode;
  if (!editing) {
    control = (
      <div className="flex min-h-10 items-center gap-2">
        <span className="text-sm text-fg" data-testid={testId ? `${testId}-value` : undefined}>
          {viewText()}
        </span>
        {canEdit ? (
          <button
            type="button"
            className="rounded p-1 text-muted transition hover:text-fg focus:outline-none focus:ring-2 focus:ring-gold/40"
            aria-label={t("editField", { label })}
            onClick={() => setLocal(true)}
          >
            <PencilIcon />
          </button>
        ) : null}
      </div>
    );
  } else if (type === "boolean") {
    control = (
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          ref={(el) => {
            inputRef.current = el;
          }}
          id={id}
          type="checkbox"
          checked={value === true}
          disabled={status === "saving"}
          aria-describedby={describedBy}
          onChange={(event) => {
            lastSent.current = null;
            onSave(name, event.target.checked);
            if (local) setLocal(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") cancel();
          }}
        />
        <span>{value ? t("yes") : t("no")}</span>
      </label>
    );
  } else if (type === "select") {
    control = (
      <select
        ref={(el) => {
          inputRef.current = el;
        }}
        id={id}
        className={inputClass}
        value={draft}
        aria-invalid={message ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => {
          setDraft(event.target.value);
          commit(event.target.value);
          if (local) setLocal(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") cancel();
        }}
        onBlur={() => {
          if (local) setLocal(false);
        }}
      >
        {!required || draft === "" ? <option value="">{t("empty")}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  } else if (type === "textarea") {
    control = (
      <textarea
        ref={(el) => {
          inputRef.current = el;
        }}
        id={id}
        className={inputClass}
        rows={rows}
        value={draft}
        placeholder={placeholder}
        maxLength={maxLength}
        aria-invalid={message ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={onBlur}
      />
    );
  } else {
    control = (
      <input
        ref={(el) => {
          inputRef.current = el;
        }}
        id={id}
        type={type === "number" ? "text" : type}
        inputMode={type === "number" ? "decimal" : undefined}
        className={inputClass}
        value={draft}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        maxLength={maxLength}
        aria-invalid={message ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={onBlur}
      />
    );
  }

  return (
    <div className={className ?? "flex flex-col gap-1"} data-testid={testId} data-field={name}>
      {editing && type !== "boolean" ? (
        <label htmlFor={id} className={ui.label}>
          {label}
        </label>
      ) : (
        <span className={ui.label}>{label}</span>
      )}
      {control}
      {help ? (
        <p id={`${id}-help`} className={ui.help}>
          {help}
        </p>
      ) : null}
      {message ? (
        <p id={`${id}-error`} role="alert" className={ui.error}>
          {message}
        </p>
      ) : statusText ? (
        <p role="status" aria-live="polite" className={ui.help}>
          {statusText}
        </p>
      ) : null}
    </div>
  );
}
