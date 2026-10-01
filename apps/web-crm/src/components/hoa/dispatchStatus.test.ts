import { createTranslator } from "next-intl";

import de from "../../../messages/de.json";
import en from "../../../messages/en.json";

import { dispatchStatusLabel } from "./dispatchStatus";

const tr = (locale: "de" | "en", messages: typeof de) => {
  const t = createTranslator({ locale, messages, namespace: "HoaProvision" });
  return (key: string) => (t as unknown as (k: string) => string)(key);
};

describe("dispatchStatusLabel", () => {
  it("translates the known statuses in German and English", () => {
    const d = tr("de", de);
    const e = tr("en", en as typeof de);
    expect(["prepared", "sent", "delivered", "failed"].map((s) => dispatchStatusLabel(d, s))).toEqual([
      "vorbereitet",
      "versendet",
      "zugegangen",
      "fehlgeschlagen",
    ]);
    expect(["prepared", "sent", "delivered", "failed"].map((s) => dispatchStatusLabel(e, s))).toEqual([
      "prepared",
      "sent",
      "delivered",
      "failed",
    ]);
  });

  it("returns an unknown status unchanged", () => {
    expect(dispatchStatusLabel(tr("de", de), "archived")).toBe("archived");
  });
});
