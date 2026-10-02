import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LocalModelStatus } from "./LocalModelStatus";

describe("LocalModelStatus (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the state, offers a proposal only to allowed users and posts the case id", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ enabled: true, version: "2", artifact: null }))
      .mockResolvedValueOnce(jsonResponse({ label: "mietvertrag" }));
    renderIntl(<LocalModelStatus canPropose />);
    expect(await screen.findByTestId("local-model-status")).toHaveTextContent("Eingeschaltet");
    expect(screen.getByTestId("local-model-status")).toHaveTextContent("Version 2");
    const submit = screen.getByRole("button", { name: "Vorschlag anfordern" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Prüffall (Kennung)"), " case-1 ");
    await userEvent.click(submit);
    expect(await screen.findByTestId("local-model-result")).toHaveTextContent("mietvertrag");
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/bff/objektakte/local-model/cases/case-1/propose");
  });

  it("hides the form when the model is off or the right is missing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ enabled: false, version: null, artifact: null }));
    renderIntl(<LocalModelStatus canPropose />);
    expect(await screen.findByText("Ausgeschaltet")).toBeInTheDocument();
    expect(screen.getByText("Keine Version hinterlegt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vorschlag anfordern" })).not.toBeInTheDocument();
  });

  it("shows a load error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Fehler", status: 500 }, 500));
    renderIntl(<LocalModelStatus canPropose={false} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
