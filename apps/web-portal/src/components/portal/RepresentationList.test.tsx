import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { RepresentationList } from "./RepresentationList";
import type { PortalRepresentation } from "./types";

function rep(overrides: Partial<PortalRepresentation> = {}): PortalRepresentation {
  return {
    id: "r1",
    principal_contact_id: "c1",
    principal_name: "Erika Muster",
    valid_from: "2026-01-01",
    valid_to: "2026-12-31",
    state: "active",
    expires_in_days: 91,
    ...overrides,
  };
}

describe("RepresentationList", () => {
  it("shows the empty state", () => {
    renderIntl(<RepresentationList rows={[]} />);
    expect(screen.getByText("Keine Vertretungen hinterlegt.")).toBeInTheDocument();
  });

  it("shows principal, period and remaining days of an active power of attorney", () => {
    renderIntl(<RepresentationList rows={[rep()]} />);
    expect(screen.getByText("Erika Muster")).toBeInTheDocument();
    expect(screen.getByText("Gültig vom 01.01.2026 bis 31.12.2026")).toBeInTheDocument();
    expect(screen.getByTestId("expires-in")).toHaveTextContent("Läuft in 91 Tagen ab");
  });

  it("marks an expired power of attorney as without access", () => {
    renderIntl(<RepresentationList rows={[rep({ state: "expired", expires_in_days: null })]} />);
    expect(screen.getByText("Abgelaufen")).toBeInTheDocument();
    expect(screen.getByText("Kein Zugriff mehr.")).toBeInTheDocument();
    expect(screen.queryByTestId("expires-in")).toBeNull();
  });

  it("handles an open end date", () => {
    renderIntl(<RepresentationList rows={[rep({ valid_to: null, expires_in_days: null })]} />);
    expect(screen.getByText("Gültig ab 01.01.2026, ohne Enddatum")).toBeInTheDocument();
  });
});
