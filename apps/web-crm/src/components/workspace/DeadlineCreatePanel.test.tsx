import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DeadlineCreatePanel, type DeadlineEntry, type DeadlineType } from "./DeadlineCreatePanel";

const TYPE_WITH_DURATION: DeadlineType = {
  id: "01920000-0000-7000-8000-0000000000a1",
  code: "kautionsabrechnung",
  name: "Kautionsabrechnung",
  trigger: "handover_done",
  duration_months: null,
  duration_days: 90,
  responsible_role: null,
  source_note: "zu verifizieren",
  is_system: true,
  is_active: true,
};
const TYPE_WITHOUT_DURATION: DeadlineType = { ...TYPE_WITH_DURATION, id: "01920000-0000-7000-8000-0000000000a2", code: "mieterhoehung", name: "Mieterhöhung", duration_days: null };
const ENTRY: DeadlineEntry = {
  id: "01920000-0000-7000-8000-0000000000e1",
  type_id: TYPE_WITH_DURATION.id,
  type_name: "Kautionsabrechnung",
  title: "Kautionsabrechnung Vertrag M-1",
  trigger_on: "2026-09-30",
  due_on: "2026-12-29",
  due_computed: true,
  verify: true,
  responsible_user_id: "u1",
  responsible_name: "Anna Beispiel",
  source_type: "contract",
  source_id: "01920000-0000-7000-8000-0000000000c1",
  href: "/vertraege/01920000-0000-7000-8000-0000000000c1",
  status: "open",
  done_at: null,
  warnings: [],
};

describe("DeadlineCreatePanel", () => {
  const calls: { url: string; method: string; body: unknown }[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.includes("/deadline-entries/compute")) return jsonResponse({ due_on: "2026-12-29" });
      if (url.includes("/deadline-entries/") && url.endsWith("/done")) return jsonResponse({ ...ENTRY, status: "done" });
      if (url.includes("/deadline-entries") && method === "POST") return jsonResponse({ ...ENTRY, id: "new" }, 201);
      if (url.includes("/deadline-entries")) return jsonResponse([ENTRY]);
      if (url.includes("/deadline-types")) return jsonResponse([TYPE_WITH_DURATION, TYPE_WITHOUT_DURATION]);
      if (url.includes("/assignable-users")) return jsonResponse([{ user_id: "u1", display_name: "Anna Beispiel" }]);
      return jsonResponse([]);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("lists the deadlines of the record with the verification badge and the responsible person", async () => {
    renderIntl(<DeadlineCreatePanel sourceType="contract" sourceId={ENTRY.source_id} canCreate={false} canUpdate={false} />);
    expect(await screen.findByText("Kautionsabrechnung: Kautionsabrechnung Vertrag M-1")).toBeInTheDocument();
    expect(screen.getByText("29.12.2026")).toBeInTheDocument();
    expect(screen.getAllByText("zu verifizieren").length).toBeGreaterThan(0);
    expect(screen.getByText(/Anna Beispiel/)).toBeInTheDocument();
    expect(screen.queryByTestId("deadline-create-form")).not.toBeInTheDocument();
    expect(calls[0]!.url).toContain("source_type=contract&source_id=" + ENTRY.source_id + "&status=open");
  });

  it("computes the due date from the type and posts the new deadline", async () => {
    renderIntl(<DeadlineCreatePanel sourceType="ticket" sourceId="01920000-0000-7000-8000-0000000000t1" canCreate canUpdate />);
    const type = await screen.findByTestId("deadline-type");
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(2));
    await userEvent.selectOptions(type, TYPE_WITH_DURATION.id);
    await userEvent.type(screen.getByTestId("deadline-trigger"), "2026-09-30");
    expect(await screen.findByText(/Aus dem Fristtyp berechnet: 29.12.2026/)).toBeInTheDocument();
    expect(screen.getByText("Erfassungsstandard ES-10: Fristen mit verantwortlicher Person anlegen.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByTestId("deadline-responsible"), "u1");
    await userEvent.click(screen.getByRole("button", { name: "Frist anlegen" }));
    expect(await screen.findByText("Frist angelegt. Sie erscheint in der Fristenliste und im Kalender.")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({
      type_id: TYPE_WITH_DURATION.id,
      source_type: "ticket",
      trigger_on: "2026-09-30",
      due_on: null,
      responsible_user_id: "u1",
    });
  });

  it("requires an entered due date for a type without duration and finishes entries", async () => {
    renderIntl(<DeadlineCreatePanel sourceType="unit" sourceId="01920000-0000-7000-8000-0000000000u1" canCreate canUpdate />);
    const type = await screen.findByTestId("deadline-type");
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(2));
    await userEvent.selectOptions(type, TYPE_WITHOUT_DURATION.id);
    expect(screen.getByText("Der Fristtyp hat keine Dauer. Fälligkeit bitte eintragen.")).toBeInTheDocument();
    expect(screen.getByTestId("deadline-due")).toBeRequired();
    await userEvent.click(await screen.findByTestId(`deadline-done-${ENTRY.id}`));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith(`/deadline-entries/${ENTRY.id}/done`))).toBe(true));
  });
});
