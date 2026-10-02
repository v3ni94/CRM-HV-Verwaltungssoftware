import { render, screen } from "@testing-library/react";

import { MaintenanceBanner } from "./MaintenanceBanner";

const fetchMaintenance = vi.fn();
let locale = "de";

vi.mock("@/lib/maintenance", async (orig) => ({
  ...(await orig<typeof import("@/lib/maintenance")>()),
  fetchMaintenance: () => fetchMaintenance(),
}));
vi.mock("next-intl/server", async () => {
  const { intlServerMock } = await import("@/test/serverPage");
  return { ...intlServerMock(), getLocale: async () => locale };
});

const item = {
  id: "m1",
  starts_at: "2026-10-10T20:00:00Z",
  ends_at: "2026-10-10T22:00:00Z",
  text_de: "Wir aktualisieren das System.",
  text_en: "We are updating the system.",
  phase: "announced" as const,
};

async function show() {
  return render(await MaintenanceBanner());
}

describe("MaintenanceBanner", () => {
  beforeEach(() => {
    locale = "de";
    fetchMaintenance.mockReset();
  });

  it("renders nothing without a maintenance window", async () => {
    fetchMaintenance.mockResolvedValue([]);
    const { container } = await show();
    expect(container).toBeEmptyDOMElement();
  });

  it("announces a planned window in Berlin time with the German text", async () => {
    fetchMaintenance.mockResolvedValue([item]);
    await show();
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Geplante Wartung.");
    expect(status).toHaveTextContent("Zeitraum: 10.10.2026, 22:00 bis 11.10.2026, 00:00 (Ortszeit Berlin)");
    expect(status).toHaveTextContent("Wir aktualisieren das System.");
  });

  it("marks a running window and shows the English text for the English locale", async () => {
    locale = "en";
    fetchMaintenance.mockResolvedValue([{ ...item, phase: "active" }]);
    await show();
    expect(screen.getByRole("status")).toHaveTextContent("Wartung läuft.");
    expect(screen.getByRole("status")).toHaveTextContent("We are updating the system.");
  });

  it("lists several windows", async () => {
    fetchMaintenance.mockResolvedValue([item, { ...item, id: "m2", text_de: "Zweites Fenster." }]);
    await show();
    expect(screen.getByText(/Zweites Fenster\./)).toBeInTheDocument();
    expect(screen.getAllByText(/Zeitraum:/)).toHaveLength(2);
  });
});
