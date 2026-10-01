import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import de from "../../../messages/de.json";
import { OnlineMeetingSwitch } from "./OnlineMeetingSwitch";
import { VirtualDeadlines } from "./VirtualDeadlines";
import { MeetingSettings } from "./MeetingSettings";

const bff = vi.fn(async () => ({ ok: true }));
vi.mock("@/lib/bff", () => ({ bff: (...a: unknown[]) => (bff as (...x: unknown[]) => unknown)(...a) }));

const wrap = (ui: React.ReactElement) => (
  <NextIntlClientProvider locale="de" messages={de}>
    {ui}
  </NextIntlClientProvider>
);

describe("AE12", () => {
  it("sendet den Online-Schalter, Standard aus", async () => {
    render(wrap(<OnlineMeetingSwitch enabled={false} />));
    const box = screen.getByTestId("online-enabled") as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    fireEvent.submit(screen.getByTestId("online-meeting-switch"));
    await waitFor(() => expect(bff).toHaveBeenCalled());
    expect(JSON.parse((bff.mock.calls[0] as unknown as [string, { body: string }])[1].body)).toEqual({ enabled: true });
  });

  it("sendet den Stichtag der Übergangsregel", async () => {
    bff.mockClear();
    render(wrap(<MeetingSettings weeks={3} virtualEnabled={false} transitionDate="2025-06-30" />));
    fireEvent.submit(screen.getByTestId("meeting-settings"));
    await waitFor(() => expect(bff).toHaveBeenCalled());
    const body = JSON.parse((bff.mock.calls[0] as unknown as [string, { body: string }])[1].body);
    expect(body.virtual_basis_transition_date).toBe("2025-06-30");
  });

  it("zeigt die Fristhinweise", () => {
    render(
      wrap(
        <VirtualDeadlines
          data={{ decided_on: "2024-01-10", term_limit: "2027-01-10", valid_until: "2026-12-01", days_until_valid_until: 61, transition_date: null, transition_notice: null }}
        />,
      ),
    );
    expect(screen.getByTestId("virtual-deadlines").textContent).toContain("10.01.2027");
    expect(screen.getByTestId("virtual-deadlines").textContent).toContain("zu verifizieren");
  });
});
