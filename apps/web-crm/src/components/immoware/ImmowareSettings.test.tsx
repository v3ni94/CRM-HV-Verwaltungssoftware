import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ImmowareSettings, type ImmowareConnection } from "./ImmowareSettings";

const baseConnection: ImmowareConnection = {
  base_url: "https://x.dav.immoware24.de/dav/",
  carddav_url: null,
  caldav_url: null,
  webdav_root_url: null,
  carddav_url_discovered: false,
  caldav_url_discovered: false,
  webdav_root_discovered: false,
  username: "hvm",
  has_password: true,
  enabled: true,
  verify_tls: true,
  poll_minutes: 30,
  last_check_at: null,
  last_check_ok: null,
  last_error: null,
  last_diagnosis: null,
  last_diagnosis_at: null,
};

describe("ImmowareSettings diagnose", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("runs the diagnose call and shows the step table with the not-booked notice", async () => {
    const diagnosis = {
      steps: [
        {
          name: ".well-known/carddav",
          url: "https://x.dav.immoware24.de/.well-known/carddav",
          status: 404,
          ok: false,
          note: "404: Ressource nicht vorhanden.",
          collections: [],
        },
        {
          name: "current-user-principal (base)",
          url: "https://x.dav.immoware24.de/dav/",
          status: 404,
          ok: false,
          note: "404: Ressource nicht vorhanden.",
          collections: [],
        },
      ],
      carddav_url: null,
      caldav_url: null,
      webdav_url: null,
      dav_module_likely_not_booked: true,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(diagnosis))
      .mockResolvedValueOnce(
        jsonResponse({ ...baseConnection, last_diagnosis: diagnosis, last_diagnosis_at: "2026-09-25T10:00:00Z" }),
      );
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<ImmowareSettings connection={baseConnection} runs={[]} canManage={true} />);

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Verbindung diagnostizieren" }));
    });

    expect(screen.getByText(/DAV-Modul ist bei Immoware24 vermutlich nicht gebucht/)).toBeInTheDocument();
    expect(screen.getByTestId("immoware-diagnosis-steps")).toBeInTheDocument();
    expect(screen.getAllByText("404")).not.toHaveLength(0);
  });

  it("offers to apply a discovered URL without touching a manually configured one", async () => {
    const diagnosis = {
      steps: [
        {
          name: "addressbook-home-set",
          url: "https://x.dav.immoware24.de/dav/principals/hvm/",
          status: 207,
          ok: true,
          note: "gefunden: https://x.dav.immoware24.de/dav/addressbooks/hvm/",
          collections: [],
        },
      ],
      carddav_url: "https://x.dav.immoware24.de/dav/addressbooks/hvm/default/",
      caldav_url: null,
      webdav_url: null,
      dav_module_likely_not_booked: false,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(diagnosis))
      .mockResolvedValueOnce(jsonResponse({ ...baseConnection, last_diagnosis: diagnosis }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<ImmowareSettings connection={baseConnection} runs={[]} canManage={true} />);

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Verbindung diagnostizieren" }));
    });

    expect(screen.getByText(/CardDAV-URL gefunden/)).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Uebernehmen" }));
    });
    expect(screen.getByLabelText("CardDAV-URL")).toHaveValue(
      "https://x.dav.immoware24.de/dav/addressbooks/hvm/default/",
    );
  });
});
