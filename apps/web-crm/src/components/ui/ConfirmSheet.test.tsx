import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { renderIntl } from "@/test/intl";

import { ConfirmSheet, useConfirm } from "./ConfirmSheet";

vi.mock("next/navigation", () => ({ usePathname: () => "/makler/uebergabe", useSearchParams: () => new URLSearchParams() }));

function Host({ danger = false }: { danger?: boolean }) {
  const { confirm, confirmSheet } = useConfirm();
  const [result, setResult] = useState<string>("");
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          void confirm({ title: "Foto entfernen?", text: "Die Datei wird endgültig gelöscht.", confirmLabel: "Entfernen", danger }).then((ok) => setResult(ok ? "ja" : "nein"));
        }}
      >
        Löschen
      </button>
      <output>{result}</output>
      {confirmSheet}
    </div>
  );
}

describe("ConfirmSheet and useConfirm", () => {
  it("resolves true on confirm", async () => {
    renderIntl(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    const dialog = screen.getByRole("dialog", { name: "Foto entfernen?" });
    expect(dialog).toHaveTextContent("Die Datei wird endgültig gelöscht.");
    const confirmButton = screen.getByRole("button", { name: "Entfernen" });
    expect(confirmButton).toHaveFocus();
    expect(confirmButton).toHaveClass("w-full", "sm:w-auto");
    await userEvent.click(confirmButton);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("ja"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("resolves false on cancel and on Escape, focusing cancel for a danger action", async () => {
    renderIntl(<Host danger />);
    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    const cancel = screen.getByRole("button", { name: "Abbrechen" });
    expect(cancel).toHaveFocus();
    expect(screen.getByRole("button", { name: "Entfernen" })).toHaveClass("bg-danger-bg");
    await userEvent.click(cancel);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("nein"));
    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("nein");
  });

  it("renders the controlled component with default labels", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    renderIntl(<ConfirmSheet open title="Abschließen?" onConfirm={onConfirm} onCancel={onCancel} />);
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
