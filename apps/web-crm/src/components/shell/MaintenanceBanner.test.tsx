import { render, screen } from "@testing-library/react";

import { MaintenanceBanner } from "./MaintenanceBanner";

const fetchMaintenance = vi.fn();
let locale = "de";

vi.mock("@/lib/maintenance", async () => {
  const actual = await vi.importActual<typeof import("@/lib/maintenance")>("@/lib/maintenance");
  return { ...actual, fetchMaintenance: () => fetchMaintenance() };
});
vi.mock("next-intl/server", async () => {
  const { createTranslator } = await import("next-intl");
  const { default: messages } = await import("../../../messages/de.json");
  return {
    getLocale: async () => locale,
    getTranslations: async (ns: string) => createTranslator({ locale: "de", messages, namespace: ns as never }),
  };
});

const item = (over: Record<string, unknown> = {}) => ({
  id: "w1",
  starts_at: "2026-10-10T20:00:00Z",
  ends_at: "2026-10-10T22:00:00Z",
  text_de: "Datenbankumzug",
  text_en: "Database move",
  phase: "announced",
  ...over,
});

describe("MaintenanceBanner", () => {
  beforeEach(() => {
    fetchMaintenance.mockReset();
    locale = "de";
  });

  it("renders nothing without a maintenance window", async () => {
    fetchMaintenance.mockResolvedValue([]);
    const { container } = render((await MaintenanceBanner()) ?? <></>);
    expect(container).toBeEmptyDOMElement();
  });

  it("announces a planned window with Berlin time and the German text", async () => {
    fetchMaintenance.mockResolvedValue([item()]);
    render((await MaintenanceBanner())!);
    expect(screen.getByRole("status")).toHaveTextContent("Geplante Wartung.");
    expect(screen.getByRole("status")).toHaveTextContent("10.10.2026, 22:00");
    expect(screen.getByRole("status")).toHaveTextContent("Datenbankumzug");
  });

  it("shows the running notice and the English text for locale en", async () => {
    locale = "en";
    fetchMaintenance.mockResolvedValue([item({ phase: "active" })]);
    render((await MaintenanceBanner())!);
    expect(screen.getByRole("status")).toHaveTextContent("Wartung läuft.");
    expect(screen.getByRole("status")).toHaveTextContent("Database move");
    expect(screen.getByRole("status")).not.toHaveTextContent("Datenbankumzug");
  });
});
