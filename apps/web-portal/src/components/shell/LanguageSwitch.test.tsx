import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderIntl } from "@/test/intl";

import { LanguageSwitch } from "./LanguageSwitch";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const fetchMock = vi.fn();

beforeEach(() => {
  refresh.mockReset();
  fetchMock.mockReset().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
});

describe("LanguageSwitch (GA11-01)", () => {
  it("lists the available languages and marks the current one", () => {
    renderIntl(<LanguageSwitch />);
    const select = screen.getByRole("combobox", { name: "Sprache" });
    expect(select).toHaveValue("de");
    expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
  });

  it("stores the choice and reloads the page", async () => {
    renderIntl(<LanguageSwitch />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sprache" }), "en");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/locale",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ locale: "en" }) }),
    );
    expect(refresh).toHaveBeenCalled();
  });
});
