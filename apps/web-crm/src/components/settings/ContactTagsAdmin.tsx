"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ContactTag = { id: string; name: string; contacts: number };

/** Tag management of the tenant (M3-04, 6.1 contact_tag): list with usage, rename, merge into
 *  another tag, delete. Reading needs contacts:read, every change contacts:update (delete:
 *  contacts:delete); the API decides, the buttons only hide. Tags are created as free text in
 *  the contact form; merging keeps every contact link and removes the source tag. */
export function ContactTagsAdmin({ canUpdate, canDelete }: { canUpdate: boolean; canDelete: boolean }) {
  const t = useTranslations("ContactTagsAdmin");
  const [tags, setTags] = useState<ContactTag[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [merging, setMerging] = useState<string | null>(null);
  const [target, setTarget] = useState("");

  const load = useCallback(async () => {
    const res = await bff<ContactTag[]>("/api/bff/contact-tags");
    if (res.ok) setTags(res.data ?? []);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(call: () => Promise<{ ok: boolean; message?: string }>) {
    setBusy(true);
    setError(null);
    const res = await call();
    setBusy(false);
    if (!res.ok) {
      setError(res.message ?? t("error"));
      return false;
    }
    await load();
    return true;
  }

  async function rename(tag: ContactTag) {
    const name = newName.trim();
    if (!name) return;
    const ok = await run(() =>
      bff(`/api/bff/contact-tags/${tag.id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
    );
    if (ok) setRenaming(null);
  }

  async function merge(tag: ContactTag) {
    const other = tags?.find((x) => x.id === target);
    if (!other) return;
    if (!window.confirm(t("mergeConfirm", { source: tag.name, target: other.name }))) return;
    const ok = await run(() =>
      bff(`/api/bff/contact-tags/${tag.id}/merge`, { method: "POST", body: JSON.stringify({ target_id: target }) }),
    );
    if (ok) {
      setMerging(null);
      setTarget("");
    }
  }

  async function remove(tag: ContactTag) {
    if (!window.confirm(t("deleteConfirm", { name: tag.name, count: tag.contacts }))) return;
    await run(() => bff(`/api/bff/contact-tags/${tag.id}`, { method: "DELETE" }));
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="contact-tags-title" data-testid="contact-tags-admin">
      <h2 id="contact-tags-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {tags === null ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : tags.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("name")}</th>
                <th className="num">{t("contacts")}</th>
                <th>{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {tags.map((tag) => (
                <tr key={tag.id} data-testid="contact-tag-row">
                  <td>
                    {renaming === tag.id ? (
                      <input
                        className={ui.input}
                        value={newName}
                        maxLength={63}
                        aria-label={t("newNameFor", { name: tag.name })}
                        onChange={(e) => setNewName(e.target.value)}
                      />
                    ) : (
                      tag.name
                    )}
                    {merging === tag.id ? (
                      <select
                        className={`${ui.input} mt-1`}
                        value={target}
                        aria-label={t("mergeTargetFor", { name: tag.name })}
                        onChange={(e) => setTarget(e.target.value)}
                      >
                        <option value="">{t("mergeTargetPlaceholder")}</option>
                        {tags
                          .filter((x) => x.id !== tag.id)
                          .map((x) => (
                            <option key={x.id} value={x.id}>
                              {x.name}
                            </option>
                          ))}
                      </select>
                    ) : null}
                  </td>
                  <td className="num">{tag.contacts}</td>
                  <td>
                    <span className="flex flex-wrap gap-2">
                      {canUpdate && renaming === tag.id ? (
                        <>
                          <button type="button" className={ui.buttonSm} disabled={busy || !newName.trim()} onClick={() => void rename(tag)}>
                            {t("save")}
                          </button>
                          <button type="button" className={ui.buttonSm} onClick={() => setRenaming(null)}>
                            {t("cancel")}
                          </button>
                        </>
                      ) : null}
                      {canUpdate && merging === tag.id ? (
                        <>
                          <button type="button" className={ui.buttonSm} disabled={busy || !target} onClick={() => void merge(tag)}>
                            {t("mergeRun")}
                          </button>
                          <button type="button" className={ui.buttonSm} onClick={() => setMerging(null)}>
                            {t("cancel")}
                          </button>
                        </>
                      ) : null}
                      {canUpdate && renaming !== tag.id && merging !== tag.id ? (
                        <>
                          <button
                            type="button"
                            className={ui.buttonSm}
                            disabled={busy}
                            aria-label={t("renameFor", { name: tag.name })}
                            onClick={() => {
                              setRenaming(tag.id);
                              setMerging(null);
                              setNewName(tag.name);
                            }}
                          >
                            {t("rename")}
                          </button>
                          <button
                            type="button"
                            className={ui.buttonSm}
                            disabled={busy || tags.length < 2}
                            aria-label={t("mergeFor", { name: tag.name })}
                            onClick={() => {
                              setMerging(tag.id);
                              setRenaming(null);
                              setTarget("");
                            }}
                          >
                            {t("merge")}
                          </button>
                        </>
                      ) : null}
                      {canDelete && renaming !== tag.id && merging !== tag.id ? (
                        <button
                          type="button"
                          className={ui.buttonSm}
                          disabled={busy}
                          aria-label={t("deleteFor", { name: tag.name })}
                          onClick={() => void remove(tag)}
                        >
                          {t("delete")}
                        </button>
                      ) : null}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
