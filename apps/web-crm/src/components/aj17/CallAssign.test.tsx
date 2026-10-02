import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { CallAssign } from "./CallAssign";

describe("CallAssign (GAI-420)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("assigns the chosen candidate", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ contact_name: "Erika Muster" }));
    renderIntl(<CallAssign callId="01920000-0000-7000-8000-0000000a1701" canEdit candidates={[{ id: "01920000-0000-7000-8000-0000000a1702", name: "Erika Muster" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Kontakt zuordnen"), "01920000-0000-7000-8000-0000000a1702");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Zugeordnet: Erika Muster");
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("/api/bff/communication/calls/01920000-0000-7000-8000-0000000a1701/assign");
    expect(JSON.parse(String(init?.body))).toEqual({ contact_id: "01920000-0000-7000-8000-0000000a1702" });
  });

  it("validates a typed contact id, hides without the right and shows API errors", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Nicht gefunden", status: 404 }, 404));
    const { unmount } = renderIntl(<CallAssign callId="01920000-0000-7000-8000-0000000a1701" canEdit />);
    await userEvent.type(screen.getByLabelText("Kontakt-ID"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gültige Kontakt-ID");
    expect(f).not.toHaveBeenCalled();
    await userEvent.clear(screen.getByLabelText("Kontakt-ID"));
    await userEvent.type(screen.getByLabelText("Kontakt-ID"), "01920000-0000-7000-8000-0000000a1702");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnen" }));
    await screen.findByRole("alert");
    expect(f).toHaveBeenCalledTimes(1);
    unmount();
    const { container } = renderIntl(<CallAssign callId="01920000-0000-7000-8000-0000000a1701" canEdit={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
