import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderIntl } from "@/test/intl";

import { ProviderInfo } from "./ProviderInfo";

describe("ProviderInfo (GA11-04)", () => {
  it("shows contracts and availability windows read only", () => {
    renderIntl(
      <ProviderInfo
        contracts={[{ id: "1", title: "Winterdienst 2026", starts_at: "2026-01-01", ends_at: null, cancelled_at: null, active: true }]}
        windows={[{ id: "2", starts_at: "2026-10-05T07:00:00Z", ends_at: "2026-10-05T15:00:00Z", kind: "unavailable", note: "Urlaub" }]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Rahmenverträge und Verfügbarkeit" })).toBeInTheDocument();
    expect(screen.getByText("Winterdienst 2026")).toBeInTheDocument();
    expect(screen.getByText("Aktiv")).toBeInTheDocument();
    expect(screen.getByText("Nicht verfügbar")).toBeInTheDocument();
    expect(screen.getByText("Urlaub")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows empty states", () => {
    renderIntl(<ProviderInfo contracts={[]} windows={[]} />);
    expect(screen.getByText("Keine Rahmenverträge hinterlegt.")).toBeInTheDocument();
    expect(screen.getByText("Keine Zeitfenster eingetragen.")).toBeInTheDocument();
  });
});
