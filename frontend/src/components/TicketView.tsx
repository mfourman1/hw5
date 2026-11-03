import { useState } from "react";
import type { AgentEvent, PaymentProposal, Ticket, TicketSource } from "../api";
import { DESK_LABEL, SOURCE_LABEL, TYPE_LABEL, URGENCY_LABEL, dueLine, money, wholeMoney } from "../format";
import { useElapsed } from "../hooks";
import { LiveFeed } from "./LiveFeed";
import { AgentSummaries, BossApprovals, CustomerDraft } from "./RunSummary";
import { TeamFloor } from "./TeamFloor";

interface Props {
  ticket: Ticket;
  events: AgentEvent[];
  running: boolean;
  runStarted?: string;
  approver: string;
  setApprover: (v: string) => void;
  practice: boolean;
  setPractice: (v: boolean) => void;
  busy: string | null;
  onRun: () => void;
  onApprove: () => void;
  onResolve: (note: string) => void;
  onSetSource: (source: TicketSource | null) => void;
}

export function TicketView(p: Props) {
  const { ticket, events, running } = p;
  const finished = !running && events.some((e) => e.event === "task_end");
  return (
    <div className="ticket-view">
      <TicketHeader {...p} />
      <TeamFloor events={events} finished={finished} />
      <div className="work-grid">
        <LiveFeed events={events} running={running} />
        <aside className="side">
          <YourMove {...p} />
          <CustomerDraft events={events} ticket={ticket} />
        </aside>
      </div>
      <AgentSummaries events={events} finished={finished} />
    </div>
  );
}

function request(t: Ticket): string {
  if (t.sku) return `${t.qty ?? ""} × ${t.sku}${t.size ? ` · size ${t.size}` : ""}`;
  if (t.lease_id) return `Lease ${t.lease_id}`;
  return "";
}

function TicketHeader({ ticket: t, running, practice, setPractice, onRun, onSetSource, busy }: Props) {
  const [showNotes, setShowNotes] = useState(false);
  const notes = (t.notes ?? "").split("\n").filter(Boolean);
  const original = notes.find((n) => !n.startsWith("[")) ?? "";
  const added = notes.filter((n) => n.startsWith("["));
  const canRun = t.open && !running && t.desk_state !== "awaiting_approval";
  const u = t.urgency;
  const due = dueLine(t);

  return (
    <section className={`ticket-header state-${t.desk_state}`}>
      <div className="ticket-header-main">
        <div className="ticket-kicker">
          <span className="ticket-id">#{t.id}</span>
          <span>{TYPE_LABEL[t.type] ?? t.type}</span>
          {t.open && (
            <span className={`urgency-chip ${u.urgency}`}>
              {URGENCY_LABEL[u.urgency] ?? u.urgency}
              {u.days_until_deadline != null && ` · ${u.days_until_deadline < 0 ? `${-u.days_until_deadline} days late` : `${u.days_until_deadline} days left`}`}
            </span>
          )}
          <span className={`state-pill ${t.desk_state}`}>{DESK_LABEL[t.desk_state]}</span>
        </div>
        <h1>{t.subject}</h1>
        <div className="ticket-meta">
          <span>
            From <strong>{t.requester}</strong>
          </span>
          {request(t) && <span>{request(t)}</span>}
          {t.invoice_id && <span>Invoice {t.invoice_id}</span>}
          <label className="source-picker" title="Where this ticket came from">
            Came in
            <select
              value={t.source ?? ""}
              onChange={(e) => onSetSource((e.target.value || null) as TicketSource | null)}
              disabled={busy !== null}
            >
              <option value="">Not recorded</option>
              {(Object.keys(SOURCE_LABEL) as TicketSource[]).map((s) => (
                <option key={s} value={s}>
                  {SOURCE_LABEL[s]}
                </option>
              ))}
            </select>
          </label>
        </div>
        {due && t.open && (
          <div className={`ticket-due big ${u.urgency}`}>
            {due.text}
            <strong> · {due.when}</strong>
            <span className="muted"> ({u.deadline_source})</span>
          </div>
        )}
        {original && <p className="ticket-quote">“{original}”</p>}
        {added.length > 0 && (
          <button className="link" onClick={() => setShowNotes((s) => !s)}>
            {showNotes ? "Hide" : "Show"} ticket notes ({added.length})
          </button>
        )}
        {showNotes && (
          <ol className="ticket-notes">
            {added.map((n, i) => {
              const m = n.match(/^\[(\S+) ([^\]]+)\] (.*)$/);
              return (
                <li key={i}>
                  {m ? (
                    <>
                      <span className="note-who">{m[2]}</span> {m[3]}
                    </>
                  ) : (
                    n
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
      {t.open && (
        <div className="run-box">
          <button className="btn primary big" onClick={onRun} disabled={!canRun || busy !== null}>
            {running ? "Team is working…" : t.last_run && !t.last_run.dry_run ? "Run the team again" : "Send to the team"}
          </button>
          <label className="practice-toggle">
            <input type="checkbox" checked={practice} onChange={(e) => setPractice(e.target.checked)} disabled={running} />
            Practice run <span className="muted">(nothing is saved)</span>
          </label>
        </div>
      )}
    </section>
  );
}

function Approver({ approver, setApprover }: { approver: string; setApprover: (v: string) => void }) {
  return (
    <label className="approver">
      <span>Approving as</span>
      <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Your full name" autoComplete="name" />
    </label>
  );
}

function PaymentCard({ pay, ...p }: { pay: PaymentProposal } & Props) {
  const ready = p.approver.trim().length >= 3;
  return (
    <div className={`pay-card${pay.below_cash_buffer ? " warn" : ""}`}>
      <div className="pay-title">{pay.kind === "purchase" ? "Approve purchase order" : "Approve payment"}</div>
      <div className="pay-amount">{money(pay.amount)}</div>
      <div className="pay-to">
        to <strong>{pay.payee}</strong> ·{" "}
        {pay.kind === "rent"
          ? `rent, lease ${pay.ref_id}`
          : pay.kind === "purchase"
            ? `PO ${pay.ref_id}: ${pay.qty} × ${pay.sku} size ${pay.size} at ${money(pay.unit_cost ?? 0)}`
            : `invoice ${pay.ref_id}`}
      </div>
      <dl className="pay-facts">
        {pay.due_date && pay.days_until_due != null && (
          <>
            <dt>Due</dt>
            <dd>
              {pay.due_date} ({pay.days_until_due < 0 ? `${-pay.days_until_due} days late` : `${pay.days_until_due} days left`})
            </dd>
          </>
        )}
        {pay.kind === "purchase" && pay.expected_arrival && (
          <>
            <dt>Arrives</dt>
            <dd>{pay.expected_arrival} at the earliest</dd>
          </>
        )}
        <dt>Checking</dt>
        <dd className="num">
          {money(pay.balance_before)} → <strong>{money(pay.balance_after)}</strong>
        </dd>
      </dl>
      {pay.below_cash_buffer && <div className="pay-warn">This leaves less than the {wholeMoney(pay.cash_buffer)} cash buffer.</div>}
      {!pay.ok && <div className="pay-warn">{pay.problems.join(" ")}</div>}
      <Approver approver={p.approver} setApprover={p.setApprover} />
      <button className="btn pay" onClick={p.onApprove} disabled={!ready || !pay.ok || p.busy !== null}>
        {p.busy === "approve" ? "Paying…" : `Approve & ${pay.kind === "purchase" ? "buy" : "pay"} ${money(pay.amount)}`}
      </button>
      <p className="fine">
        Agents can only propose a {pay.kind === "purchase" ? "purchase" : "payment"}. Your approval is what records it and moves the cash.
      </p>
    </div>
  );
}

function YourMove(p: Props) {
  const { ticket: t, events, running } = p;
  const [note, setNote] = useState("");
  const elapsed = useElapsed(p.runStarted, running);
  const boss = [...events].reverse().find((e) => e.event === "agent_end" && e.depth === 0);
  const lastLine = (t.notes ?? "").split("\n").filter(Boolean).pop() ?? "";
  const ready = p.approver.trim().length >= 3;

  let body;
  if (running) {
    body = (
      <>
        <div className="move-title">
          <span className="pulse-dot" aria-hidden /> The team is on it · {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
        </div>
        <p>Watch the floor and the feed. If anything needs a person, it will wait for you here.</p>
      </>
    );
  } else if (t.desk_state === "awaiting_approval") {
    body = (
      <>
        <div className="move-title attention">Your approval is needed</div>
        <BossApprovals events={events} />
        {t.pending_payments.map((pay) => (
          <PaymentCard key={`${pay.kind}-${pay.ref_id}`} pay={pay} {...p} />
        ))}
      </>
    );
  } else if (t.desk_state === "needs_signoff" || t.desk_state === "needs_attention") {
    body = (
      <>
        <div className="move-title attention">
          {t.desk_state === "needs_signoff" ? "The Boss is asking for your sign-off" : "The team couldn't finish this one"}
        </div>
        {boss?.said && <p>{boss.said}</p>}
        <BossApprovals events={events} />
        <Approver approver={p.approver} setApprover={p.setApprover} />
        <input className="note-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note for the ticket (optional)" maxLength={300} />
        <div className="move-buttons">
          <button className="btn primary" onClick={() => p.onResolve(note)} disabled={!ready || p.busy !== null}>
            Sign off & resolve
          </button>
          <button className="btn ghost" onClick={p.onRun} disabled={p.busy !== null}>
            Run again
          </button>
        </div>
      </>
    );
  } else if (t.desk_state === "resolved") {
    const m = lastLine.match(/^\[(\S+) ([^\]]+)\] (.*)$/);
    body = (
      <>
        <div className="move-title done">Resolved</div>
        {m ? (
          <p>
            {m[3]} <span className="muted">— {m[2]}</span>
          </p>
        ) : (
          boss?.said && <p>{boss.said}</p>
        )}
      </>
    );
  } else if (t.last_run?.dry_run && t.last_run.status === "finished") {
    body = (
      <>
        <div className="move-title">Practice run finished</div>
        <p>Nothing was saved. Untick “Practice run” and send it to the team for real to resolve it.</p>
      </>
    );
  } else {
    body = (
      <>
        <div className="move-title">Ready when you are</div>
        <p>
          The Boss reads the ticket, hands each question to the agent who owns it, and reports back. Anything that moves
          money waits here for your approval.
        </p>
      </>
    );
  }
  return (
    <section className={`your-move state-${running ? "running" : t.desk_state}`} aria-label="Your move">
      <div className="section-title">
        <h3>Your move</h3>
      </div>
      {body}
    </section>
  );
}
