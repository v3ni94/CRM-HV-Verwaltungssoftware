import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("renders only the title when nothing else is given", () => {
    renderIntl(<PageHeader title="Kontakte" />);
    expect(screen.getByRole("heading", { level: 1, name: "Kontakte" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("renders eyebrow, description, action and a breadcrumb with links for crumbs with href", () => {
    renderIntl(
      <PageHeader
        eyebrow="Verwaltung"
        title="Objekt"
        description="Stammdaten des Objekts"
        action={<button type="button">Neu</button>}
        breadcrumb={[{ href: "/objekte", label: "Objekte" }, { label: "Musterstraße 1" }]}
      />,
    );
    expect(screen.getByRole("navigation", { name: "Brotkrümelnavigation" })).toBeInTheDocument();
    expect(screen.getByText("Verwaltung")).toBeInTheDocument();
    expect(screen.getByText("Stammdaten des Objekts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Neu" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Objekte" })).toHaveAttribute("href", "/objekte");
    expect(screen.getByText("Musterstraße 1").closest("a")).toBeNull();
  });

  it("omits the breadcrumb for an empty list", () => {
    renderIntl(<PageHeader title="Titel" breadcrumb={[]} />);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
