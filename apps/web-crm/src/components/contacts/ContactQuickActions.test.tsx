import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ContactQuickActions } from "./ContactQuickActions";

describe("ContactQuickActions (GAI-615)", () => {
  it("renders nothing without phone and mail", () => {
    const { container } = renderIntl(<ContactQuickActions phone={null} email="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("builds tel and mailto links and strips blanks from the number", () => {
    renderIntl(<ContactQuickActions phone="+49 30 1234 567" email="a@example.invalid" />);
    expect(screen.getByTestId("contact-call")).toHaveAttribute("href", "tel:+49301234567");
    expect(screen.getByTestId("contact-mail")).toHaveAttribute("href", "mailto:a@example.invalid");
  });

  it("offers only the existing channel", () => {
    renderIntl(<ContactQuickActions email="a@example.invalid" />);
    expect(screen.queryByTestId("contact-call")).not.toBeInTheDocument();
    expect(screen.getByTestId("contact-mail")).toBeInTheDocument();
  });
});
