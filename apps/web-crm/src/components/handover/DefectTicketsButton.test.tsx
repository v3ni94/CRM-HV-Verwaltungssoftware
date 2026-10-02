import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DefectTicketsButton } from "./DefectTicketsButton";

describe("DefectTicketsButton (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing without defects", () => {
    renderIntl(<DefectTicketsButton protocolId="p1" defectCount={0} />);
    expect(screen.queryByTestId("defect-tickets")).not.toBeInTheDocument();
  });

  it("creates tickets with a POST, locks the button while running and reports the count", async () => {
    let release: (r: Response) => void = () => undefined;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise((resolve) => (release = resolve)));
    renderIntl(<DefectTicketsButton protocolId="p1" defectCount={2} />);
    const button = screen.getByRole("button", { name: "Mängel als Tickets anlegen (2)" });
    await userEvent.click(button);
    expect(button).toBeDisabled();
    release(jsonResponse({ created: [{}, {}] }, 201));
    expect(await screen.findByText("2 Tickets angelegt.")).toBeInTheDocument();
    expect(button).toBeEnabled();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/handover/protocols/p1/defects/tickets");
    expect((init as RequestInit).method).toBe("POST");
  });

  it("shows the refusal of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Gesperrt", status: 403 }, 403));
    renderIntl(<DefectTicketsButton protocolId="p1" defectCount={1} />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
