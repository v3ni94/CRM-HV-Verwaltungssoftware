import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { OutdatedNotice } from "./OutdatedNotice";

describe("OutdatedNotice", () => {
  it("shows nothing without outdated items", () => {
    renderIntl(<OutdatedNotice count={0} />);
    expect(screen.queryByTestId("audit-outdated-notice")).toBeNull();
  });

  it("warns with the count (singular and plural)", () => {
    const { unmount } = renderIntl(<OutdatedNotice count={1} />);
    expect(screen.getByTestId("audit-outdated-notice")).toHaveTextContent("1 Position ist veraltet");
    unmount();
    renderIntl(<OutdatedNotice count={3} />);
    expect(screen.getByTestId("audit-outdated-notice")).toHaveTextContent("3 Positionen sind veraltet");
  });
});
