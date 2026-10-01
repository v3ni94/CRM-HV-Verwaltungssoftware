import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { JobSchedulesAdmin, type JobSchedule } from "./JobSchedulesAdmin";

const jobs: JobSchedule[] = [
  {
    job_key: "accounting-dunning-run",
    label: "Mahnlauf",
    enabled: true,
    run_at: null,
    configured: false,
  },
];

describe("JobSchedulesAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves switch and time of a job", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse({}, 200));
    renderIntl(<JobSchedulesAdmin initial={jobs} canManage={true} />);
    await userEvent.click(screen.getByLabelText("Aktiv Mahnlauf"));
    await userEvent.type(
      screen.getByLabelText("Uhrzeit (HH:MM) Mahnlauf"),
      "07:15",
    );
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/automation/job-schedules/accounting-dunning-run");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({
      enabled: false,
      run_at: "07:15",
    });
    expect(await screen.findByText("Gespeichert")).toBeInTheDocument();
  });

  it("is read only without manage permission", () => {
    renderIntl(<JobSchedulesAdmin initial={jobs} canManage={false} />);
    expect(screen.getByLabelText("Aktiv Mahnlauf")).toBeDisabled();
    expect(screen.queryByText("Speichern")).toBeNull();
  });
});
