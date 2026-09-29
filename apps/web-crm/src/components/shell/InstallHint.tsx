"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const DISMISSED_KEY = "mhvp-crm-install-hint-dismissed";

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

/** iPhone, iPod and iPad, including iPadOS 13 and later, which reports itself as a Mac
 *  ("MacIntel") but, unlike a Mac, has more than one touch point. */
export function isAppleTouchDevice(nav: Pick<Navigator, "userAgent" | "platform" | "maxTouchPoints">): boolean {
  if (/iphone|ipad|ipod/i.test(nav.userAgent)) return true;
  return nav.platform === "MacIntel" && nav.maxTouchPoints > 1;
}

/** Entry "Als App installieren" of the user menu (M31 WP5, M30-08): no banner on any page.
 *  With a remembered beforeinstallprompt the entry opens the browser prompt; on iPhone and
 *  iPad, where no such event exists, it shows the Safari steps once (Teilen, Zum Home
 *  Bildschirm). Hidden when the CRM already runs as an installed app or after a dismissal
 *  (remembered in this browser only, storage failures are ignored). */
export function InstallHint({ itemClassName = "" }: { itemClassName?: string }) {
  const t = useTranslations("Pwa");
  const [prompt, setPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [ios, setIos] = useState(false);
  const [showIosSteps, setShowIosSteps] = useState(false);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    if (readDismissed()) return;
    const standalone =
      window.matchMedia?.("(display-mode: standalone)").matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (standalone) return;
    if (isAppleTouchDevice(navigator)) {
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
    if (prompt) {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice.outcome === "accepted") writeDismissed();
      setHidden(true);
      return;
    }
    if (ios) setShowIosSteps((v) => !v);
  }

  function dismiss() {
    writeDismissed();
    setHidden(true);
  }

  return (
    <div data-testid="install-hint">
      <button type="button" role="menuitem" className={`${itemClassName} w-full`} onClick={() => void install()}>
        {t("install")}
      </button>
      {showIosSteps ? (
        <div className="px-3 pb-2 text-xs text-muted" role="note">
          <p>{t("iosHint")}</p>
          <button type="button" className="mt-1 underline" onClick={dismiss}>
            {t("dismiss")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
