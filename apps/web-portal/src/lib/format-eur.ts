/** Server safe EUR formatter (no "use client"): shared by server pages and client components. */
export function formatEur(value: string | number): string {
  return `${new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))} EUR`;
}
