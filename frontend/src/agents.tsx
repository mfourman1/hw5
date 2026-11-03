import type { AgentName } from "./api";

/** How each agent looks and "sounds" on the desk. Colors match --agent-* in styles.css. */
export interface AgentLook {
  name: AgentName;
  title: string;
  role: string; // one line under the name
  voice: string; // how its lines read in the feed (see design.md)
}

export const AGENTS: Record<AgentName, AgentLook> = {
  boss: { name: "boss", title: "Boss", role: "Runs the queue, routes the work", voice: "memo" },
  inventory: { name: "inventory", title: "Inventory", role: "Counts the shelves", voice: "count" },
  accounting: { name: "accounting", title: "Accounting", role: "Prices, bills and cash", voice: "ledger" },
  facilities: { name: "facilities", title: "Facilities", role: "The shop, lease and landlord", voice: "check" },
  customer_service: { name: "customer_service", title: "Customer Service", role: "Drafts every reply", voice: "letter" },
};

export const SPECIALISTS: AgentName[] = ["inventory", "accounting", "facilities", "customer_service"];

export function AgentIcon({ name, size = 22 }: { name: AgentName; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (name) {
    case "boss": // a compass: sets direction
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M15.5 8.5 13 13l-4.5 2.5L11 11z" />
        </svg>
      );
    case "inventory": // a box
      return (
        <svg {...common}>
          <path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z" />
          <path d="M3 7.5 12 12l9-4.5M12 12v9" />
        </svg>
      );
    case "accounting": // a ledger with a dollar sign
      return (
        <svg {...common}>
          <rect x="4" y="3" width="16" height="18" rx="2" />
          <path d="M14.5 8.5c-.5-.9-1.5-1.3-2.5-1.3-1.4 0-2.5.7-2.5 1.8 0 2.6 5 1.4 5 4 0 1.1-1.1 1.8-2.5 1.8-1.1 0-2.1-.5-2.6-1.4M12 6v1.2M12 14.8V16" />
        </svg>
      );
    case "facilities": // a storefront
      return (
        <svg {...common}>
          <path d="M3 10h18M4 10l1.5-5h13L20 10M5 10v10h14V10" />
          <path d="M10 20v-5h4v5" />
        </svg>
      );
    case "customer_service": // a speech bubble
      return (
        <svg {...common}>
          <path d="M4 5h16v11H9l-5 4z" />
          <path d="M8 9.5h8M8 12.5h5" />
        </svg>
      );
  }
}

export function AgentBadge({ name, small = false }: { name: AgentName; small?: boolean }) {
  return (
    <span className={`agent-badge agent-${name}${small ? " small" : ""}`}>
      <AgentIcon name={name} size={small ? 13 : 15} />
      {AGENTS[name].title}
    </span>
  );
}
