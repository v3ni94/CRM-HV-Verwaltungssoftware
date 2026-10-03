import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { CreateEventInput } from "@/components/calendar/CreateEventDialog";
import { jsonResponse, renderIntl } from "@/test/intl";

import { AppointmentButton } from "./AppointmentButton";

type DialogProps = {
  onCreate: (input: CreateEventInput) => Promise<string | null>;
  onClose: () => void;
  defaultTarget: string;
  hasOwnMailbox: boolean;
  hasDefaultMailbox: boolean;
  prefill: Record<string, unknown>;
};
let lastProps: DialogProps | null = null;
let createResult: string | null | undefined;

vi.mock("@/components/calendar/CreateEventDialog", () => ({
  CreateEventDialog: (props: DialogProps) => {
    lastProps = props;
    return (
      <div data-testid="dialog">
        <button type="button" onClick={async () => { createResult = await props.onCreate({ title: "T", starts_on: "2026-10-09", all_day: true, target: "internal", notes: "", location: "", attendees: [] } as unknown as CreateEventInput); }}>
          create
        </button>
        <button type="button" onClick={props.onClose}>
          close
        </button>
      </div>
    );
  },
}));

describe("AppointmentButton", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    lastProps = null;
    createResult = undefined;
  });

  it("opens the dialog with the origin prefill and own mailbox detection", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ notices: [{ source: "own", connected: true }, { source: "default", connected: false }] }),
    );
    renderIntl(<AppointmentButton sourceType="ticket" sourceId="t1" title="Ortstermin" label="Termin anlegen" defaultDate="2026-10-08" location="Haus 1" />);
    expect(screen.queryByTestId("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Termin anlegen" }));
    expect(screen.getByTestId("dialog")).toBeInTheDocument();
    await waitFor(() => expect(lastProps?.hasOwnMailbox).toBe(true));
    expect(lastProps?.hasDefaultMailbox).toBe(false);
    expect(lastProps?.defaultTarget).toBe("own");
    expect(lastProps?.prefill).toMatchObject({ title: "Ortstermin", source_type: "ticket", source_id: "t1", starts_on: "2026-10-08", location: "Haus 1" });
  });

  it("posts the appointment with the origin link, maps internal to default and shows the link", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "POST" ? jsonResponse({ date: "2026-10-09" }) : jsonResponse({ notices: [] }),
    );
    renderIntl(
      <AppointmentButton sourceType="handover" sourceId="h1" title="Übergabe" label="Termin" createdLinkLabel={(d) => `Zum Termin am ${d}`} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Termin" }));
    await userEvent.click(screen.getByRole("button", { name: "create" }));
    const link = await screen.findByRole("link", { name: "Zum Termin am 09.10.2026" });
    expect(link).toHaveAttribute("href", "/kalender?datum=2026-10-09");
    expect(createResult).toBeNull();
    const post = fetchMock.mock.calls.find((c) => c[1]?.method === "POST")!;
    expect(String(post[0])).toBe("/api/bff/workspace/calendar");
    expect(JSON.parse(String(post[1]?.body))).toMatchObject({
      title: "T",
      starts_on: "2026-10-09",
      target: "default",
      notes: null,
      location: null,
      source_type: "handover",
      source_id: "h1",
    });
  });

  it("returns the API message to the dialog and shows no link on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "POST" ? jsonResponse({ title: "Fehler", status: 422, detail: "Ungültiges Datum" }, 422) : jsonResponse({ notices: [] }),
    );
    renderIntl(<AppointmentButton sourceType="ticket" sourceId="t1" title="x" label="Termin" createdLinkLabel={(d) => d} />);
    await userEvent.click(screen.getByRole("button", { name: "Termin" }));
    await userEvent.click(screen.getByRole("button", { name: "create" }));
    await waitFor(() => expect(createResult).toEqual(expect.any(String)));
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("closes the dialog", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ notices: [] }));
    renderIntl(<AppointmentButton sourceType="ticket" sourceId="t1" title="x" label="Termin" />);
    await userEvent.click(screen.getByRole("button", { name: "Termin" }));
    await userEvent.click(screen.getByRole("button", { name: "close" }));
    expect(screen.queryByTestId("dialog")).toBeNull();
  });
});
