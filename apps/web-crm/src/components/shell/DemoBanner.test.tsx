import { render, screen } from "@testing-library/react";

import de from "../../../messages/de.json";

import { DemoBanner } from "./DemoBanner";

vi.mock("next-intl/server", () => ({
  getTranslations: async () => (key: string) => (key === "demo.banner" ? de.AF19.demo.banner : key),
}));

describe("DemoBanner", () => {
  it("shows the notice for a demo tenant", async () => {
    render(await DemoBanner({ isDemo: true }));
    expect(screen.getByTestId("demo-banner")).toHaveTextContent("Demo-Mandant");
    expect(screen.getByRole("note")).toBeInTheDocument();
  });

  it("renders nothing for a productive tenant", async () => {
    const { container } = render(await DemoBanner({ isDemo: false }));
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("demo-banner")).toBeNull();
  });
});
