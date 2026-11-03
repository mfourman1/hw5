import type { DeskState, Ticket, TicketSource } from "./api";

export const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

export const wholeMoney = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function seconds(ms?: number | null): string {
  if (!ms) return "";
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export const TYPE_LABEL: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Price inquiry",
  inquiry: "Inquiry",
  question: "Question",
};

export const SOURCE_LABEL: Record<TicketSource, string> = {
  online: "Online",
  in_person: "In person",
  phone: "Called in",
};

/** "+0:42" style time since the run started. */
export function sinceStart(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return `+${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const SHOP_TZ = "America/New_York";

/** The ticket's due date in words, e.g. "Due Fri, Aug 28 · 3 days late" or "Reply by Tue, Sep 1, 4:55 PM · tomorrow". */
export function dueLine(t: Ticket): { text: string; when: string } | null {
  const u = t.urgency;
  if (!u.deadline || u.days_until_deadline == null) return null;
  const d = u.days_until_deadline;
  const when = d < 0 ? `${-d} day${d === -1 ? "" : "s"} late` : d === 0 ? "today" : d === 1 ? "tomorrow" : `in ${d} days`;
  const isReply = Boolean(u.reply_by && u.deadline_source?.includes("reply window"));
  const text = isReply
    ? `Reply by ${new Date(u.reply_by!).toLocaleString("en-US", { timeZone: SHOP_TZ, weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
    : `Due ${new Date(u.deadline + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
  return { text, when };
}

export const DESK_LABEL: Record<DeskState, string> = {
  open: "Open",
  running: "Team working",
  awaiting_approval: "Needs your approval",
  needs_signoff: "Needs your sign-off",
  needs_attention: "Needs attention",
  resolved: "Resolved",
};

export const URGENCY_LABEL: Record<string, string> = {
  overdue: "Overdue",
  due_soon: "Due soon",
  upcoming: "Upcoming",
  no_deadline: "No deadline",
  not_open: "Closed",
};

const TOOL_NAMES: Record<string, string> = {
  list_open_tickets: "list open tickets",
  get_ticket: "read ticket",
  get_ticket_urgency: "check urgency",
  check_stock: "check stock",
  get_invoice: "read invoice",
  get_vendor_lead_time: "vendor lead time",
  get_pricing: "look up price",
  quote_bulk_price: "price a quote",
  get_cash_balance: "check cash",
  propose_payment: "propose payment",
  get_lease: "read lease",
  add_ticket_note: "write ticket note",
  propose_purchase_order: "propose purchase",
  list_purchase_orders: "list purchase orders",
};

export const toolName = (tool: string) => TOOL_NAMES[tool] ?? tool.replaceAll("_", " ");

/** The arguments of a tool call, short enough for a chip. */
export function toolArgs(tool: string, a: Record<string, unknown>): string {
  switch (tool) {
    case "check_stock":
      return `${a.sku} · ${a.size}`;
    case "get_ticket":
    case "get_ticket_urgency":
      return `#${a.ticket_id}`;
    case "get_lease":
      return `lease ${a.lease_id}`;
    case "get_invoice":
      return `invoice ${a.invoice_id}`;
    case "get_pricing":
      return String(a.sku);
    case "quote_bulk_price":
      return `${a.qty} × ${a.sku} @ ${a.discount_pct ?? 0}% off`;
    case "get_vendor_lead_time":
      return a.vendor_id != null ? `vendor ${a.vendor_id}` : `“${a.specialty}”`;
    case "propose_payment":
      return `${money(Number(a.amount))} · ${a.kind} ${a.ref_id}`;
    case "propose_purchase_order":
      return `${a.qty} × ${a.sku} · ${a.size} · vendor ${a.vendor_id}`;
    case "add_ticket_note":
      return a.new_status ? `#${a.ticket_id} → ${String(a.new_status).replaceAll("_", " ")}` : `#${a.ticket_id}`;
    default:
      return "";
  }
}

function parse(result: unknown): Record<string, any> | null {
  if (result && typeof result === "object") return result as Record<string, any>;
  if (typeof result === "string") {
    try {
      return JSON.parse(result);
    } catch {
      return null;
    }
  }
  return null;
}

/** What a tool sent back, in a few words (null when there's nothing worth showing). */
export function toolResult(tool: string, raw: unknown): string | null {
  const r = parse(raw);
  if (!r) return typeof raw === "string" && raw.startsWith("The ") ? raw : null;
  if (r.found === false) return r.message ?? "not found";
  switch (tool) {
    case "check_stock":
      return `${r.qty} on hand${r.in_stock ? "" : " — out of stock"} · ${r.location}`;
    case "get_ticket":
      return `${TYPE_LABEL[r.type] ?? r.type} from ${r.requester}`;
    case "get_ticket_urgency":
      return `${URGENCY_LABEL[r.urgency] ?? r.urgency}${r.days_until_deadline != null ? ` (${r.days_until_deadline} days)` : ""}`;
    case "get_lease":
      return `${money(r.monthly_rent)} to ${r.landlord}, due ${r.next_due}`;
    case "get_invoice":
      return `${money(r.amount)} · ${r.status}${r.overdue ? " · overdue" : ""}`;
    case "get_vendor_lead_time": {
      const v = r.vendors?.[0];
      if (!v) return null;
      return v.on_hold
        ? `${v.name}: on hold (unpaid invoice ${v.unpaid_invoices.map((i: { id: number }) => i.id).join(", ")}) · ${v.lead_days} days after it's paid`
        : `${v.name}: ${v.lead_days} days → ${v.earliest_arrival}`;
    }
    case "get_pricing":
      return `list ${money(r.list_price)} · cost ${money(r.unit_cost)}`;
    case "quote_bulk_price":
      return `${money(r.quote_total)} · ${String(r.decision).replaceAll("_", " ")}`;
    case "get_cash_balance":
      return r.accounts?.length ? `checking ${money(r.accounts[0].balance)}` : null;
    case "propose_payment":
      if (r.proposed) return `proposed · leaves ${money(r.balance_after)}`;
      if (r.dry_run) return "checks passed (practice run, not saved)";
      return r.problems?.length ? `refused: ${r.problems.join(" ")}` : null;
    case "propose_purchase_order":
      if (r.proposed) return `PO ${r.po_id} proposed · ${money(r.amount)} · leaves ${money(r.balance_after)}`;
      if (r.dry_run) return "checks passed (practice run, not saved)";
      return r.problems?.length ? `refused: ${r.problems.join(" ")}` : null;
    case "list_purchase_orders":
      return `${r.count} purchase order${r.count === 1 ? "" : "s"}`;
    case "add_ticket_note":
      return r.written ? "note saved" : r.dry_run ? "practice run, not saved" : null;
    case "list_open_tickets":
      return `${r.count} open`;
    default:
      return null;
  }
}
