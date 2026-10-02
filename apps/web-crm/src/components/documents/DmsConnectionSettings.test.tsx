import { act, fireEvent, screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DmsConnectionSettings } from "./DmsConnectionSettings";

const oauth = { connected: false } as never;
const paperless = { kind: "paperless", enabled: true, base_url: "https://dms.example", has_secret: true, options: {} };

describe("DmsConnectionSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders both connection forms", () => {
    const { container } = renderIntl(<DmsConnectionSettings paperless={paperless} googleDrive={null} oauth={oauth} />);
    expect(container.querySelectorAll("form")).toHaveLength(2);
    expect((screen.getByLabelText(/Webhook/i, { selector: "input[type=password]" }) as HTMLInputElement).value).toBe("");
  });

  it("saves the Paperless connection and never sends an unchanged secret", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(paperless));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderIntl(<DmsConnectionSettings paperless={paperless} googleDrive={null} oauth={oauth} />);
    await act(async () => {
      fireEvent.submit(container.querySelectorAll("form")[0] as HTMLFormElement);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/dms-connections/paperless");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body.base_url).toBe("https://dms.example");
    expect(body).not.toHaveProperty("secret");
  });

  it("shows the API error for a forbidden save (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    const { container } = renderIntl(<DmsConnectionSettings paperless={paperless} googleDrive={null} oauth={oauth} />);
    await act(async () => {
      fireEvent.submit(container.querySelectorAll("form")[0] as HTMLFormElement);
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("saves the Google Drive connection via PUT /dms-connections/google_drive", async () => {
    const gd = { kind: "google_drive", enabled: false, base_url: null, has_secret: false, options: {} };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(gd));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderIntl(<DmsConnectionSettings paperless={null} googleDrive={gd} oauth={oauth} />);
    const forms = container.querySelectorAll("form");
    await act(async () => {
      fireEvent.submit(forms[forms.length - 1] as HTMLFormElement);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/dms-connections/google_drive");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
  });
});
