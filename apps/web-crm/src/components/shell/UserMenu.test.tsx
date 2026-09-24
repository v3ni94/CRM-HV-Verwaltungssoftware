import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { UserMenu } from "./UserMenu";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

describe("UserMenu", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows initials and opens a menu with name, e-mail and links", async () => {
    renderIntl(<UserMenu name="Timo Müller" email="timo@muellerhv.de" />);
    expect(screen.getByRole("button", { name: "Benutzermenü" })).toHaveTextContent("TM");
    await userEvent.click(screen.getByRole("button", { name: "Benutzermenü" }));
    expect(screen.getByText("Timo Müller")).toBeInTheDocument();
    expect(screen.getByText("timo@muellerhv.de")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Meine Daten" })).toHaveAttribute("href", "/einstellungen/profil");
    expect(screen.getByRole("menuitem", { name: "Einstellungen" })).toHaveAttribute("href", "/einstellungen");
  });

  it("closes on Escape", async () => {
    renderIntl(<UserMenu name="Timo Müller" email="timo@muellerhv.de" />);
    await userEvent.click(screen.getByRole("button", { name: "Benutzermenü" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });
});
