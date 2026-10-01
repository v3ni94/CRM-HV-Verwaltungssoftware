import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ProfileSettings } from "./ProfileSettings";

const MEMBERSHIP = "01920000-0000-7000-8000-00000000f010";
const catalogue = ["Geschäftsführer", "Prokurist", "Assistenz", "Objektbetreuung"];
const profile = { membership_id: MEMBERSHIP, position: null, phone: null, mobile_phone: null, catalogue };
const preview = { membership_id: MEMBERSHIP, text: "-- \nIna Brink\nHausverwaltung Müller GmbH", html: "<!-- mhvp-signature --><table></table>" };

function render(extra: Partial<React.ComponentProps<typeof ProfileSettings>> = {}) {
  return renderIntl(
    <ProfileSettings
      displayName="Ina Brink"
      email="brink@muellerhv.de"
      roles={["standard"]}
      tenantName="Hausverwaltung Müller GmbH"
      initialSessions={[]}
      initialDevices={[]}
      totpEnabled={false}
      signatureProfile={profile}
      signaturePreview={preview}
      {...extra}
    />,
  );
}

function signatureSection() {
  const section = screen.getByRole("heading", { name: "E-Mail-Signatur" }).closest("section");
  if (!section) throw new Error("signature section missing");
  return within(section);
}

describe("ProfileSettings signature", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the server rendered preview and the position catalogue", () => {
    render();
    expect(screen.getByTestId("signature-text")).toHaveTextContent("Ina Brink");
    const select = screen.getByLabelText("Position") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      "Keine Position",
      ...catalogue,
      "Andere Position (manuell anlegen)",
    ]);
  });

  it("saves a catalogue position and refreshes the preview", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/mail/signature/profile") && init?.method === "PUT") {
        calls.push({ url, body: JSON.parse(String(init.body)) });
        return jsonResponse({ ...profile, position: "Objektbetreuung", phone: "02173 1" });
      }
      if (url.endsWith("/api/bff/mail/signature/preview")) {
        return jsonResponse({ ...preview, text: "-- \nIna Brink\nObjektbetreuung\nHausverwaltung Müller GmbH" });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    render();
    await userEvent.selectOptions(screen.getByLabelText("Position"), "Objektbetreuung");
    await userEvent.type(screen.getByLabelText("Telefon (Durchwahl)"), "02173 1");
    await userEvent.click(signatureSection().getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(calls[0]?.body).toEqual({ position: "Objektbetreuung", phone: "02173 1" });
    expect(screen.getByTestId("signature-text")).toHaveTextContent("Objektbetreuung");
  });

  it("lets the user enter a free text position", async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "PUT") {
        bodies.push(JSON.parse(String(init.body)));
        return jsonResponse({ ...profile, position: "Empfang", catalogue: [...catalogue, "Empfang"] });
      }
      if (url.endsWith("/preview")) return jsonResponse(preview);
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    render();
    await userEvent.selectOptions(screen.getByLabelText("Position"), "__custom__");
    await userEvent.type(screen.getByLabelText("Positionsbezeichnung"), "Empfang");
    await userEvent.click(signatureSection().getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(bodies).toEqual([{ position: "Empfang", phone: null }]));
    // Die manuell angelegte Position kehrt im Dropdown wieder.
    await waitFor(() => expect(screen.getByRole("option", { name: "Empfang" })).toBeInTheDocument());
  });

  it("renders without a signature block when the profile is unavailable", () => {
    render({ signatureProfile: null, signaturePreview: null });
    expect(screen.queryByText("E-Mail-Signatur")).not.toBeInTheDocument();
  });

  it("names the password form for assistive technology", () => {
    render();
    expect(screen.getByRole("form", { name: "Passwort ändern" })).toBeInTheDocument();
  });
});

describe("ProfileSettings second factor policy (M2-04)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("hides the switch off and explains the policy when the factor is mandatory", () => {
    render({ totpEnabled: true, mfaRequired: true });
    expect(screen.getByText(/durch die Richtlinie des Mandanten vorgeschrieben/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Zweiten Faktor ausschalten" })).not.toBeInTheDocument();
  });

  it("keeps the switch off under a voluntary policy", () => {
    render({ totpEnabled: true, mfaRequired: false });
    expect(screen.queryByText(/durch die Richtlinie des Mandanten vorgeschrieben/)).not.toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Zweiten Faktor ausschalten" })).toBeInTheDocument();
  });
});
