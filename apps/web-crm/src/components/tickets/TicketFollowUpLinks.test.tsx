import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import { renderIntl } from "@/test/intl";

import en from "../../../messages/en.json";

import { TicketFollowUpLinks } from "./TicketFollowUpLinks";

describe("TicketFollowUpLinks", () => {
  it("renders nothing without predecessor and follow ups", () => {
    const { container } = renderIntl(<TicketFollowUpLinks predecessor={null} successors={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links the follow up ticket to its predecessor", () => {
    renderIntl(<TicketFollowUpLinks predecessor={{ id: "t-1", number: 412, title: "Fenster klemmt" }} successors={[]} />);
    const notice = screen.getByTestId("ticket-follow-up-of");
    expect(notice).toHaveTextContent("Folgevorgang zu Ticket #412 Fenster klemmt");
    expect(screen.getByRole("link", { name: "#412 Fenster klemmt" })).toHaveAttribute("href", "/tickets/t-1");
    expect(screen.queryByTestId("ticket-follow-ups")).not.toBeInTheDocument();
  });

  it("links the closed predecessor to its follow up tickets", () => {
    renderIntl(
      <TicketFollowUpLinks
        predecessor={null}
        successors={[
          { id: "t-2", number: 500, title: "Re: Fenster klemmt" },
          { id: "t-3", number: 501, title: null },
        ]}
      />,
    );
    expect(screen.getByTestId("ticket-follow-ups")).toHaveTextContent("Folgevorgänge");
    expect(screen.getByRole("link", { name: "#500 Re: Fenster klemmt" })).toHaveAttribute("href", "/tickets/t-2");
    expect(screen.getByRole("link", { name: "#501" })).toHaveAttribute("href", "/tickets/t-3");
    expect(screen.queryByTestId("ticket-follow-up-of")).not.toBeInTheDocument();
  });

  it("shows one follow up in the singular and uses the English texts", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en} timeZone="Europe/Berlin">
        <TicketFollowUpLinks predecessor={null} successors={[{ id: "t-2", number: 500, title: "Neu" }]} />
      </NextIntlClientProvider>,
    );
    expect(screen.getByTestId("ticket-follow-ups")).toHaveTextContent("Follow up ticket #500 Neu");
  });
});
