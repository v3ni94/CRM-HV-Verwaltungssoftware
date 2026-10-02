import { render, screen } from "@testing-library/react";

import { PageLoading } from "./PageLoading";

vi.mock("next-intl/server", async () => {
  const { createTranslator } = await import("next-intl");
  const { default: messages } = await import("../../../messages/de.json");
  return { getTranslations: async (ns: string) => createTranslator({ locale: "de", messages, namespace: ns as never }) };
});

describe("PageLoading", () => {
  it("announces the loading state to screen readers and hides the placeholders", async () => {
    render(await PageLoading());
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status.querySelector(".sr-only")).toHaveTextContent(/\S/);
    expect(status.querySelector("[aria-hidden='true']")!.children).toHaveLength(3);
  });
});
