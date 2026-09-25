"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export function LogoutButton() {
  const t = useTranslations("Portal");
  const router = useRouter();
  async function logout() {
    await bff<null>("/api/session/logout", { method: "POST" });
    router.push("/anmelden");
    router.refresh();
  }
  return (
    <button type="button" className={ui.buttonSm} onClick={() => void logout()}>
      {t("logout")}
    </button>
  );
}
