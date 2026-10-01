import { fireEvent, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { renderIntl } from "@/test/intl";

import { WorkOrderWorkflowRef } from "./WorkOrderWorkflowRef";

describe("WorkOrderWorkflowRef", () => {
  afterEach(() => vi.restoreAllMocks());
  const id = "11111111-1111-4111-8111-111111111111";

  it("rejects a malformed id without calling the API", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<WorkOrderWorkflowRef orderId="o1" initial={null} canEdit />);
    fireEvent.change(screen.getByLabelText("Kennung des Freigabe-Workflows"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("status").textContent).toContain("Kennung");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("patches the reference and is read only without permission", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    const { unmount } = renderIntl(<WorkOrderWorkflowRef orderId="o1" initial={null} canEdit />);
    fireEvent.change(screen.getByLabelText("Kennung des Freigabe-Workflows"), { target: { value: id } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/work-orders/o1/approval-workflow");
    expect(JSON.parse(String((fetchMock.mock.calls[0]![1] as RequestInit).body))).toEqual({ approval_workflow_id: id });
    unmount();
    renderIntl(<WorkOrderWorkflowRef orderId="o1" initial={id} canEdit={false} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
