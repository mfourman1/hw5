// Talks to the FastAPI backend (backend/main.py). The URL comes from frontend/.env.
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";
export type TicketSource = "online" | "in_person" | "phone";
export type DeskState = "open" | "running" | "awaiting_approval" | "needs_signoff" | "needs_attention" | "resolved";

export interface Approval {
  action: string;
  amount?: number | null;
  ticket_id?: number | null;
  reason: string;
}

export interface Usage {
  requests: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

/** One agent's finished turn on a run (from its agent_end audit record). */
export interface AgentTurn {
  agent: AgentName;
  depth: number;
  status?: string;
  summary?: string;
  actions_taken?: string[];
  approvals_needed?: Approval[];
  customer_message?: string;
  time?: string;
}

export interface LastRun {
  task_id: string;
  started: string;
  dry_run: boolean;
  status: "running" | "finished" | "failed" | "interrupted";
  stop_reason?: string | null;
  error?: string | null;
  usage?: Usage | null;
  delegations?: number | null;
  duration_ms?: number | null;
  report: AgentTurn | null;
  agents: AgentTurn[];
}

/** Something waiting for a person: a bill to pay (invoice, rent) or a purchase order to approve. */
export interface PaymentProposal {
  ticket_id: number;
  kind: "invoice" | "rent" | "purchase";
  ref_id: number; // invoice id, lease id, or purchase order id
  payee: string;
  amount: number;
  due_date: string | null;
  days_until_due: number | null;
  balance_before: number;
  balance_after: number;
  below_cash_buffer: boolean;
  cash_buffer: number;
  ok: boolean;
  problems: string[];
  proposal_note: string;
  // purchase orders only
  sku?: string;
  size?: string;
  qty?: number;
  unit_cost?: number;
  expected_arrival?: string | null;
}

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: string;
  notes: string | null;
  created_at: string;
  source: TicketSource | null; // where it came from; null = not recorded
  open: boolean;
  state: "open" | "resolved";
  desk_state: DeskState;
  urgency: {
    urgency: string;
    deadline: string | null;
    deadline_source: string | null;
    days_until_deadline: number | null;
    reply_by?: string | null; // inquiries: 24 hours after the ticket came in
  };
  pending_payments: PaymentProposal[];
  last_run: LastRun | null;
}

export interface Cash {
  account: string;
  balance: number;
  as_of: string;
  shop_date: string;
  cash_buffer: number;
  below_buffer: boolean;
}

export interface ToolCall {
  tool: string;
  call_id?: string;
  args: Record<string, unknown>;
}

/** One audit-trail record, as /api/events returns it. */
export interface AgentEvent {
  seq: number;
  time: string;
  event: string;
  task_id?: string;
  agent?: AgentName;
  depth?: number;
  step?: number;
  said?: string;
  final?: boolean; // a model_response that is the agent's final report (its summary repeats in agent_end)
  asked_by?: AgentName | "manager";
  tools?: ToolCall[];
  tool_results?: { tool: string; call_id: string; result: unknown }[];
  status?: string;
  to?: AgentName;
  approvals_needed?: Approval[];
  actions_taken?: string[];
  customer_message?: string;
  stop_reason?: string;
  usage?: Usage;
  ticket_id?: number;
  dry_run?: boolean;
  // payment_approved / ticket_resolved / database_reset
  approved_by?: string;
  amount?: number;
  payee?: string;
  kind?: string;
  ref_id?: number;
  balance_after?: number;
  by?: string;
  how?: string;
}

export interface Payment {
  paid: boolean;
  amount: number;
  payee: string;
  kind: string;
  ref_id: number;
  balance_after: number;
  approved_by: string;
  ticket_resolved: boolean;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_URL}. Is uvicorn running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      detail = typeof d === "string" ? d : d?.problems?.join(" ") || d?.message || JSON.stringify(d);
    } catch {
      /* keep the status text */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  tickets: () => request<{ shop_date: string; tickets: Ticket[] }>("/api/tickets"),
  cash: () => request<Cash>("/api/cash"),
  run: (ticketId: number, dryRun: boolean) =>
    request<{ task_id: string }>(`/api/tickets/${ticketId}/run?dry_run=${dryRun}`, { method: "POST" }),
  events: (params: { taskId?: string; after?: number; limit?: number }) => {
    const q = new URLSearchParams({ limit: String(params.limit ?? 500), after: String(params.after ?? -1) });
    if (params.taskId) q.set("task_id", params.taskId);
    return request<{ last_seq: number; events: AgentEvent[] }>(`/api/events?${q}`);
  },
  approve: (ticketId: number, approvedBy: string, item: { kind: string; ref_id: number }) =>
    request<Payment>(
      "/api/payments/approve",
      post({ ticket_id: ticketId, approved_by: approvedBy, kind: item.kind, ref_id: item.ref_id }),
    ),
  setSource: (ticketId: number, source: TicketSource | null) =>
    request<{ source: TicketSource | null }>(`/api/tickets/${ticketId}/source`, post({ source })),
  resolve: (ticketId: number, approvedBy: string, note?: string) =>
    request<{ status: string }>(`/api/tickets/${ticketId}/resolve`, post({ approved_by: approvedBy, note })),
  reset: () => request<{ reset: boolean; checking_balance: number }>("/api/reset", post({ confirm: true })),
};
