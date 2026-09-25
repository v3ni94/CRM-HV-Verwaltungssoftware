import type { SVGProps } from "react";

/** Small inline icon set for the sidebar navigation. No icon library is installed; these are
 *  intentionally minimal 20x20 stroke icons that inherit `currentColor`. */
function Base(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    />
  );
}

type IconComponent = (props: SVGProps<SVGSVGElement>) => React.ReactElement;

const icons: Record<string, IconComponent> = {
  dashboard: (p) => (
    <Base {...p}>
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="11" y="3" width="6" height="4" rx="1" />
      <rect x="11" y="9" width="6" height="8" rx="1" />
      <rect x="3" y="11" width="6" height="6" rx="1" />
    </Base>
  ),
  properties: (p) => (
    <Base {...p}>
      <path d="M3 9.5 10 3l7 6.5" />
      <path d="M5 8.5V17h10V8.5" />
      <path d="M8 17v-4.5h4V17" />
    </Base>
  ),
  contacts: (p) => (
    <Base {...p}>
      <circle cx="10" cy="7" r="3" />
      <path d="M4 17c0-3 2.7-5 6-5s6 2 6 5" />
    </Base>
  ),
  calendar: (p) => (
    <Base {...p}>
      <rect x="3" y="4.5" width="14" height="12" rx="1.5" />
      <path d="M3 8h14M7 3v3M13 3v3" />
    </Base>
  ),
  rental: (p) => (
    <Base {...p}>
      <path d="M4 17V8l6-4 6 4v9" />
      <path d="M9 17v-5h2v5" />
    </Base>
  ),
  hoa: (p) => (
    <Base {...p}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4l3 2" />
    </Base>
  ),
  sev: (p) => (
    <Base {...p}>
      <rect x="4" y="3" width="12" height="14" rx="1.5" />
      <path d="M7 7h6M7 10.5h6M7 14h3" />
    </Base>
  ),
  letting: (p) => (
    <Base {...p}>
      <path d="M4 10h12M11 5l5 5-5 5" />
    </Base>
  ),
  broker: (p) => (
    <Base {...p}>
      <path d="M4 16V8l6-4 6 4v8" />
      <path d="M9 16v-4a1 1 0 0 1 2 0v4" />
    </Base>
  ),
  tickets: (p) => (
    <Base {...p}>
      <path d="M3 8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1.2a1.6 1.6 0 0 0 0 3.6V14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1.2a1.6 1.6 0 0 0 0-3.6Z" />
    </Base>
  ),
  mail: (p) => (
    <Base {...p}>
      <rect x="3" y="5" width="14" height="10" rx="1.5" />
      <path d="m3.5 6 6.5 5 6.5-5" />
    </Base>
  ),
  protocol: (p) => (
    <Base {...p}>
      <rect x="5" y="4" width="10" height="13" rx="1.5" />
      <path d="M8 3.5h4v2H8Z" />
      <path d="m7.5 10 1.8 1.8L12.7 8.4" />
    </Base>
  ),
  accounting: (p) => (
    <Base {...p}>
      <path d="M6 3v14M14 3v14M4 6h4M12 6h4M4 14h4M12 14h4" />
    </Base>
  ),
  billing: (p) => (
    <Base {...p}>
      <rect x="4" y="3" width="12" height="14" rx="1.5" />
      <path d="M7 7h6M7 10.5h6M7 14h4" />
    </Base>
  ),
  invoices: (p) => (
    <Base {...p}>
      <path d="M6 3h6l3 3v11H6z" />
      <path d="M12 3v3h3M8 11h4M8 14h4" />
    </Base>
  ),
  bank: (p) => (
    <Base {...p}>
      <path d="M3 8 10 3l7 5" />
      <path d="M4 8h12v8H4z" />
      <path d="M8 11v3M12 11v3" />
    </Base>
  ),
  assistant: (p) => (
    <Base {...p}>
      <path d="M10 3v2M10 15v2M3 10h2M15 10h2" />
      <circle cx="10" cy="10" r="4" />
    </Base>
  ),
  dms: (p) => (
    <Base {...p}>
      <path d="M3.5 5.5h5l1.5 1.5h6.5v8h-13z" />
      <path d="M3.5 9h13" />
    </Base>
  ),
  imports: (p) => (
    <Base {...p}>
      <path d="M10 3v9M6.5 8.5 10 12l3.5-3.5" />
      <path d="M4 15h12" />
    </Base>
  ),
  settings: (p) => (
    <Base {...p}>
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 3.5v2M10 14.5v2M16.5 10h-2M5.5 10h-2M14.6 5.4l-1.4 1.4M6.8 13.2l-1.4 1.4M14.6 14.6l-1.4-1.4M6.8 6.8 5.4 5.4" />
    </Base>
  ),
  platform: (p) => (
    <Base {...p}>
      <ellipse cx="10" cy="6" rx="6" ry="2.5" />
      <path d="M4 6v8c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V6" />
      <path d="M4 10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5" />
    </Base>
  ),
};

/** Looks up an icon by name, falling back to a neutral dashboard glyph. */
export function navIcon(name: string | undefined): IconComponent {
  return (name && icons[name]) || icons.dashboard!;
}

/** Chevron used to indicate an expandable group; rotates via a caller supplied class. */
export function ChevronIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <path d="M5.5 7.5 10 12l4.5-4.5" />
    </Base>
  );
}
