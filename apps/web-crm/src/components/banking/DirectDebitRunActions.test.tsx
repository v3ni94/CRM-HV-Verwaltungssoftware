import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DirectDebitRunActions } from "./DirectDebitRunActions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("DirectDebitRunActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers approval and cancel for a draft and no file button", () => {
    renderIntl(<DirectDebitRunActions id="r1" status="draft" approvals={1} />);
    expect(screen.getByRole("button", { name: "Freigeben" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verwerfen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Datei als Dokument ablegen" })).toBeNull();
  });

  it("offers the file only after two approvals and never a download", () => {
    renderIntl(<DirectDebitRunActions id="r1" status="approved" approvals={2} />);
    expect(screen.getByRole("button", { name: "Datei als Dokument ablegen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /herunterladen/i })).toBeNull();
  });

  it("renders nothing for a cancelled or exported run", () => {
    const { container } = renderIntl(<DirectDebitRunActions id="r1" status="cancelled" approvals={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the problem detail when the second approval is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ title: "Freigabe nicht möglich", status: 409, detail: "Die zweite Freigabe muss eine andere Person erteilen." }, 409),
    );
    renderIntl(<DirectDebitRunActions id="r1" status="draft" approvals={1} />);
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Die zweite Freigabe muss eine andere Person erteilen."));
    expect(refresh).not.toHaveBeenCalled();
  });
});
