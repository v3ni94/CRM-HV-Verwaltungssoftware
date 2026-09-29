"use client";

import { useEffect, useSyncExternalStore } from "react";

import type { ChatPageContext } from "./chat-suggestions";

/**
 * Explicit page context override for the chat bubble (rule AI-LOOKUP-01). The route mapping in
 * chat-suggestions.ts covers every page; a page that knows better (a tab, a selected row, a
 * record loaded by number instead of id) sets single fields with `useChatContext({...})`. The
 * override is cleared when the component unmounts. A page without client code may instead
 * render `data-chat-context='{"subArea":"..."}'` on any element; the widget reads it on
 * navigation.
 */
export type ChatContextOverride = Partial<Pick<ChatPageContext, "area" | "subArea" | "entityType" | "entityId" | "contextType" | "contextId">>;

let current: ChatContextOverride | null = null;
const listeners = new Set<() => void>();

export function setChatContextOverride(value: ChatContextOverride | null): void {
  current = value;
  for (const notify of listeners) notify();
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  return () => listeners.delete(notify);
}

export function useChatContextOverride(): ChatContextOverride | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}

/** Declares what the page knows about itself; cleared on unmount. */
export function useChatContext(value: ChatContextOverride): void {
  const key = JSON.stringify(value);
  useEffect(() => {
    setChatContextOverride(JSON.parse(key) as ChatContextOverride);
    return () => setChatContextOverride(null);
  }, [key]);
}

/** The `data-chat-context` attribute of the page, if any (server rendered pages). */
export function readChatContextAttribute(root: ParentNode | null | undefined): ChatContextOverride | null {
  const raw = root?.querySelector?.("[data-chat-context]")?.getAttribute("data-chat-context");
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as ChatContextOverride;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function mergeChatContext(base: ChatPageContext, override: ChatContextOverride | null): ChatPageContext {
  if (!override) return base;
  const merged = { ...base, ...override };
  if (override.entityType && override.entityId) {
    if (override.entityType === "contact") {
      merged.contextType = "contact";
      merged.contextId = override.entityId;
    } else if (override.entityType === "property" || override.entityType === "hoa") {
      merged.contextType = "property";
      merged.contextId = override.entityId;
    }
  }
  return merged;
}
