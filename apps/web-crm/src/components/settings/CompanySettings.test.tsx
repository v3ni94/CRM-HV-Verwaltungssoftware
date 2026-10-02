import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CompanySettings } from "./CompanySettings";

const company = { name: "Muster GmbH", city: "Bernau" } as never;
const branding = { primary_color: "#112233", accent_color: null } as never;

describe("CompanySettings (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is read only without the update right", () => {
    renderIntl(<CompanySettings initial={company} branding={branding} canUpdate={false} />);
    expect(screen.getByLabelText("Firma")).toBeDisabled();
    expect(screen.getByText(/Nur zur Ansicht/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.getByText(/#112233/)).toBeInTheDocument();
  });

  it("saves the changed company data with PATCH", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ company: {} }));
    renderIntl(<CompanySettings initial={company} branding={branding} canUpdate />);
    const input = screen.getByLabelText("Ort");
    await userEvent.clear(input);
    await userEvent.type(input, "Berlin");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("/api/bff/tenant/settings");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body)).company.city).toBe("Berlin");
  });

  it("shows the error of the API", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Nicht erlaubt", status: 403 }, 403));
    renderIntl(<CompanySettings initial={company} branding={branding} canUpdate />);
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.queryByText("Gespeichert.")).not.toBeInTheDocument());
    expect(await screen.findByText(/Nicht erlaubt/)).toBeInTheDocument();
  });
});
