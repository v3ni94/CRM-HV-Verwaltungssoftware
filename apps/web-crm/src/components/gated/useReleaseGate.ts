"use client";

import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";

export type GateId = "G1" | "G2" | "G3" | "G4" | "G5";
type GateStateRow = { gate: string; label: string; open: boolean; scopes: string[]; partially_open?: boolean };

/** "loading" until the state is known, "unknown" when the call failed (treated as closed). */
export type GateState = { status: "loading" | "open" | "closed" | "unknown"; label: string | null };

/**
 * AJ28: reads GET /tenant/release-gates and reports whether the gate is fully open for the
 * tenant. Partial approvals count as closed here; the API decides per scope and stays the
 * authority (the CRM never opens a gate, ADR 0003).
 */
export function useReleaseGate(gate: GateId): GateState {
  const [state, setState] = useState<GateState>({ status: "loading", label: null });
  useEffect(() => {
    let active = true;
    void bff<GateStateRow[]>("/api/bff/tenant/release-gates").then((res) => {
      if (!active) return;
      if (!res.ok || !Array.isArray(res.data)) {
        setState({ status: "unknown", label: null });
        return;
      }
      const row = res.data.find((r) => r.gate === gate);
      setState({ status: row?.open ? "open" : "closed", label: row?.label ?? null });
    });
    return () => {
      active = false;
    };
  }, [gate]);
  return state;
}
