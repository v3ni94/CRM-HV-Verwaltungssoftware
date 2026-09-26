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

  it("adds the owner tiles only with the owner role", () => {
    renderIntl(<StartTiles me={me({ roles: ["owner", "tenant_or_owner"] })} />);
    expect(screen.getByText("Beschlüsse der Gemeinschaft einsehen")).toBeInTheDocument();
    expect(screen.getByText("Ansprechpartner des Objekts")).toBeInTheDocument();
    expect(screen.getByText("Hausgeldkonto ansehen")).toBeInTheDocument();
  });

  it("hides the owner tiles for tenants", () => {
    renderIntl(<StartTiles me={me()} />);
    expect(screen.queryByText("Hausgeldkonto ansehen")).not.toBeInTheDocument();
  });

  it("links to the notice board and shows a hint on new notices", () => {
    renderIntl(<StartTiles me={me()} newNotices={2} />);
    expect(screen.getByText("Aushänge lesen")).toBeInTheDocument();
    expect(screen.getByTestId("new-notices")).toHaveTextContent("2 neue Aushänge am Schwarzen Brett.");
  });

  it("shows no notice hint without new notices or for providers", () => {
    renderIntl(<StartTiles me={me()} />);
    expect(screen.queryByTestId("new-notices")).not.toBeInTheDocument();
    renderIntl(<StartTiles me={me({ roles: ["provider"] })} newNotices={3} />);
    expect(screen.queryByTestId("new-notices")).not.toBeInTheDocument();
  });

  it("shows only the orders tile for providers", () => {
    renderIntl(<StartTiles me={me({ roles: ["provider"] })} />);
    expect(screen.getByText("Aufträge bearbeiten")).toBeInTheDocument();
    expect(screen.queryByText("Dokumente einsehen und herunterladen")).not.toBeInTheDocument();
    expect(screen.queryByText("Kontoauszug ansehen")).not.toBeInTheDocument();
  });

  it("shows only the audit room for a pure board account and adds it for an owner on the board", () => {
    renderIntl(<StartTiles me={me({ roles: ["board"] })} />);
    expect(screen.getByText("Prüfungsraum des Beirats öffnen")).toBeInTheDocument();
    expect(screen.queryByText("Kontoauszug ansehen")).not.toBeInTheDocument();
    expect(screen.queryByText("Aufträge bearbeiten")).not.toBeInTheDocument();
  });

  it("adds the audit room tile for an owner who is on the board", () => {
    renderIntl(<StartTiles me={me({ roles: ["board", "owner"] })} />);
    expect(screen.getByText("Prüfungsraum des Beirats öffnen")).toBeInTheDocument();
    expect(screen.getByText("Kontoauszug ansehen")).toBeInTheDocument();
  });
});
