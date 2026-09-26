import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TicketsPagination } from "./TicketsPagination";

const href = (page: number) => `/tickets?status=new&page=${page}`;

describe("TicketsPagination", () => {
  it("shows the range and only a next link on the first page", () => {
    renderIntl(<TicketsPagination page={1} pageSize={50} total={120} shown={50} buildHref={href} />);
    expect(screen.getByText("1 bis 50 von 120")).toBeInTheDocument();
    expect(screen.getByText("Seite 1 von 3")).toBeInTheDocument();
    expect(screen.queryByText("Zurück")).not.toBeInTheDocument();
    expect(screen.getByText("Weiter")).toHaveAttribute("href", "/tickets?status=new&page=2");
  });

  it("shows both links in the middle and only back on the last page", () => {
    const { unmount } = renderIntl(<TicketsPagination page={2} pageSize={50} total={120} shown={50} buildHref={href} />);
    expect(screen.getByText("51 bis 100 von 120")).toBeInTheDocument();
    expect(screen.getByText("Zurück")).toHaveAttribute("href", "/tickets?status=new&page=1");
    expect(screen.getByText("Weiter")).toHaveAttribute("href", "/tickets?status=new&page=3");
    unmount();
    renderIntl(<TicketsPagination page={3} pageSize={50} total={120} shown={20} buildHref={href} />);
    expect(screen.getByText("101 bis 120 von 120")).toBeInTheDocument();
    expect(screen.queryByText("Weiter")).not.toBeInTheDocument();
  });

  it("handles an empty result without links", () => {
    renderIntl(<TicketsPagination page={1} pageSize={50} total={0} shown={0} buildHref={href} />);
    expect(screen.getByText("0 bis 0 von 0")).toBeInTheDocument();
    expect(screen.queryByText("Weiter")).not.toBeInTheDocument();
  });
});
