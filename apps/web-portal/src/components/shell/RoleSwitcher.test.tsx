import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";

import de from "../../../messages/de.json";
import { RoleSwitcher } from "./RoleSwitcher";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

function renderSwitcher(roles: string[], current: string | null = null) {
  return render(
    <NextIntlClientProvider locale="de" messages={de}>
      <RoleSwitcher roles={roles} current={current} />
    </NextIntlClientProvider>,
  );
}

describe("RoleSwitcher", () => {
  it("renders nothing for an account with a single role", () => {
    const { container } = renderSwitcher(["owner"]);
    expect(container).toBeEmptyDOMElement();
  });

  it("stores the chosen view in a cookie and refreshes", async () => {
    const user = userEvent.setup();
    renderSwitcher(["tenant_resident", "owner"]);
    await user.selectOptions(screen.getByRole("combobox"), "owner");
    expect(document.cookie).toContain("portal_view=owner");
    expect(refresh).toHaveBeenCalled();
  });
});
