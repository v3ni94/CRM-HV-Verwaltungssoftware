import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { JournalPropertyFilter } from "./JournalPropertyFilter";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const properties = [
  { id: "p1", label: "Objekt Eins" },
  { id: "p 2", label: "Objekt Zwei" },
];

describe("JournalPropertyFilter", () => {
  afterEach(() => push.mockReset());

  it("lists the properties and preselects the current one", () => {
    renderIntl(<JournalPropertyFilter ledgerId="l1" current="p1" properties={properties} />);
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("p1");
    expect(screen.getAllByRole("option")).toHaveLength(3);
  });

  it("navigates with the encoded property parameter", async () => {
    renderIntl(<JournalPropertyFilter ledgerId="l1" current="" properties={properties} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "p 2");
    await userEvent.click(screen.getByRole("button"));
    expect(push).toHaveBeenCalledWith("/buchhaltung/l1?property=p%202");
  });

  it("navigates to the unfiltered journal for the empty option", async () => {
    renderIntl(<JournalPropertyFilter ledgerId="l1" current="p1" properties={properties} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "");
    await userEvent.click(screen.getByRole("button"));
    expect(push).toHaveBeenCalledWith("/buchhaltung/l1");
  });
});
