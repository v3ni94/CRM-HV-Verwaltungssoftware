import { render, screen } from "@testing-library/react";

import { AuthCard } from "./AuthCard";

vi.mock("next-intl/server", async () => {
  const { createTranslator } = await import("next-intl");
  const { default: messages } = await import("../../../messages/de.json");
  return { getTranslations: async (ns: string) => createTranslator({ locale: "de", messages, namespace: ns as never }) };
});

describe("AuthCard", () => {
  it("frames the step content with the title as the only h1", async () => {
    render(await AuthCard({ title: "Anmeldung", children: <button type="button">Weiter</button> }));
    expect(screen.getByRole("heading", { level: 1, name: "Anmeldung" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weiter" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("shows the help text only when given", async () => {
    const { unmount } = render(await AuthCard({ title: "A", children: null }));
    expect(screen.queryByText("Hilfe zum Login")).not.toBeInTheDocument();
    unmount();
    render(await AuthCard({ title: "A", helpText: "Hilfe zum Login", children: null }));
    expect(screen.getByText("Hilfe zum Login")).toBeInTheDocument();
  });
});
