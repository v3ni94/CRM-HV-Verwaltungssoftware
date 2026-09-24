import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LevyCreate, LevySteps } from "./LevyForms";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
const LV = "0192abcd-0000-7000-8000-000000000070";

describe("Special levy forms", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a levy from the first of the chosen month", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: LV }, 201));
    renderIntl(<LevyCreate ledgerId="l1" keys={[{ id: "k1", code: "MEA", name: "Miteigentumsanteil" }]} basePath="/weg/p" />);
    await userEvent.type(screen.getByLabelText("Zweck"), "Dachsanierung");
    await userEvent.type(screen.getByLabelText("Gesamtsumme"), "10000");
    await userEvent.type(screen.getByLabelText("Erste Fälligkeit"), "2026-03");
    await userEvent.clear(screen.getByLabelText("Raten"));
    await userEvent.type(screen.getByLabelText("Raten"), "3");
    await userEvent.click(screen.getByText("Sonderumlage anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/weg/p/sonderumlage/${LV}`));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({ first_due: "2026-03-01", instalments: 3, total: "10000" });
  });

  it("binds the resolution to the snapshot before resolving", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse({ id: "r1" }, 201))
      .mockImplementationOnce(async () => jsonResponse({ status: "resolved" }));
    renderIntl(<LevySteps id={LV} status="calculated" legalEntityId="e1" snapshotHash={"b".repeat(64)} purpose="Dach" />);
    await userEvent.type(screen.getByLabelText("Beschlussdatum"), "2026-02-10");
    await userEvent.click(screen.getByText("Beschluss zu diesem Stand erfassen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({ subject_type: "special_levy", subject_id: LV, snapshot_hash: "b".repeat(64) });
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ resolution_id: "r1" });
  });
});
