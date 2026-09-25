import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { StartTiles } from "./StartTiles";
import type { Me } from "./types";

function me(overrides: Partial<Me> = {}): Me {
  return { contact_id: "c1", roles: ["tenant"], contracts: [], ...overrides };
}

describe("StartTiles", () => {
  it("shows the tenant and owner tiles by default", () => {
    renderIntl(<StartTiles me={me()} />);
    expect(screen.getByText("Dokumente einsehen und herunterladen")).toBeInTheDocument();
    expect(screen.getByText("Schäden und Anliegen melden")).toBeInTheDocument();
    expect(screen.getByText("Kontoauszug ansehen")).toBeInTheDocument();
    expect(screen.getByText("Zählerstand melden")).toBeInTheDocument();
    expect(screen.getByText("Stammdaten ändern lassen")).toBeInTheDocument();
    expect(screen.queryByText("Ihre Aufträge der Hausverwaltung.")).not.toBeInTheDocument();
  });

  it("shows only the orders tile for providers", () => {
    renderIntl(<StartTiles me={me({ roles: ["provider"] })} />);
    expect(screen.getByText("Aufträge bearbeiten")).toBeInTheDocument();
    expect(screen.queryByText("Dokumente einsehen und herunterladen")).not.toBeInTheDocument();
    expect(screen.queryByText("Kontoauszug ansehen")).not.toBeInTheDocument();
  });
});
