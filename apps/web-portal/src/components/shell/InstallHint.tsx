"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ui } from "@/lib/ui";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const DISMISSED_KEY = "mhvp-portal-install-hint-dismissed";

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(): void {
  try {
    window.localStorage.setItem(DISMISSED_KEY, "1");
  } catch {
    // Per viewer convenience only.
  }
}

/** Installationshinweis (A57): shown when the browser offers "Add to home screen"
 *  (beforeinstallprompt) and the portal is not already running as an installed app. On iOS
 *  Safari no event exists; a short manual hint is shown instead. Dismissal is remembered in
 *  the browser only. */
export function InstallHint() {
  const t = useTranslations("Pwa");
  const [prompt, setPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [ios, setIos] = useState(false);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    if (readDismissed()) return;
    const standalone =
      window.matchMedia?.("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (standalone) return;
    const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
    if (isIos) {
      setIos(true);
      setHidden(false);
    }
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPrompt(event as BeforeInstallPromptEvent);
      setHidden(false);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  if (hidden) return null;

  async function install() {
    if (!prompt) return;
    await prompt.prompt();
    const choice = await prompt.userChoice;
    if (choice.outcome === "accepted") writeDismissed();
    setHidden(true);
  }

  function dismiss() {
    writeDismissed();
    setHidden(true);
  }

  return (
    <div className={`${ui.notice} flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between`} role="region" aria-label={t("title")} data-testid="install-hint">
      <div>
        <p className="font-medium text-fg">{t("title")}</p>
        <p>{ios ? t("iosHint") : t("hint")}</p>
      </div>
      <div className="flex gap-2">
        {prompt ? (
          <button type="button" className={ui.buttonSm} onClick={install}>
            {t("install")}
          </button>
        ) : null}
        <button type="button" className={ui.buttonSm} onClick={dismiss}>
          {t("dismiss")}
        </button>
      </div>
    </div>
  );
}
