import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { MeteringDisabledNotice } from "./MeteringDisabledNotice";

describe("MeteringDisabledNotice (GAI-615)", () => {
  it("names the locked module and links to the tenant settings", () => {
    renderIntl(<MeteringDisabledNotice />);
    expect(screen.getByTestId("metering-disabled")).toHaveTextContent("nicht aktiviert");
    expect(screen.getByRole("link", { name: "Zu den Mandanteneinstellungen" })).toHaveAttribute("href", "/einstellungen/mandant");
  });
});
