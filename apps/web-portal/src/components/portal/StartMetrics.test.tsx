import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { StartMetrics } from "./StartMetrics";

describe("StartMetrics", () => {
  it("shows the tenant and owner figures with number, label and link", () => {
    renderIntl(<StartMetrics metrics={{ openTickets: 3, openBalance: "1.234,56 EUR", documents: 12 }} />);
    expect(screen.getByTestId("start-metrics")).toBeInTheDocument();
    const tickets = screen.getByRole("link", { name: /Offene Meldungen/ });
    expect(tickets).toHaveAttribute("href", "/meldungen");
    expect(tickets).toHaveTextContent("3");
    const account = screen.getByRole("link", { name: /Offene Posten/ });
    expect(account).toHaveAttribute("href", "/konto");
    expect(account).toHaveTextContent("1.234,56 EUR");
    const documents = screen.getByRole("link", { name: /Dokumente/ });
    expect(documents).toHaveAttribute("href", "/dokumente");
    expect(documents).toHaveTextContent("12");
  });

  it("omits figures without a value", () => {
    renderIntl(<StartMetrics metrics={{ openTickets: 0 }} />);
    expect(screen.getByRole("link", { name: /Offene Meldungen/ })).toHaveTextContent("0");
    expect(screen.queryByText("Offene Posten")).not.toBeInTheDocument();
    expect(screen.queryByText("Dokumente")).not.toBeInTheDocument();
    expect(screen.queryByText("Offene Terminvorschläge")).not.toBeInTheDocument();
  });

  it("renders nothing without any figure", () => {
    renderIntl(<StartMetrics metrics={{}} />);
    expect(screen.queryByTestId("start-metrics")).not.toBeInTheDocument();
  });

  it("shows the provider figures with links to the orders", () => {
    renderIntl(<StartMetrics metrics={{ ordersOpen: 2, ordersInProgress: 1 }} />);
    expect(screen.getByRole("link", { name: /Offene Aufträge/ })).toHaveAttribute("href", "/auftraege");
    expect(screen.getByRole("link", { name: /Aufträge in Ausführung/ })).toHaveAttribute("href", "/auftraege");
    expect(screen.queryByText("Offene Meldungen")).not.toBeInTheDocument();
  });

  it("shows the board engagements with a link to the audit room", () => {
    renderIntl(<StartMetrics metrics={{ boardEngagements: 4 }} />);
    const audit = screen.getByRole("link", { name: /Prüfaufträge/ });
    expect(audit).toHaveAttribute("href", "/pruefung");
    expect(audit).toHaveTextContent("4");
  });

  it("shows open appointment proposals linking to the tickets", () => {
    renderIntl(<StartMetrics metrics={{ openTickets: 1, openProposals: 2 }} />);
    expect(screen.getByRole("link", { name: /Offene Terminvorschläge/ })).toHaveAttribute("href", "/meldungen");
  });
});
