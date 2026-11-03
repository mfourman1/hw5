import { useState } from "react";
import type { AgentEvent, AgentName, Ticket } from "../api";
import { AGENTS, AgentIcon } from "../agents";
import { money } from "../format";

const ORDER: AgentName[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];
const STATUS_WORD: Record<string, string> = {
  done: "Done",
  needs_approval: "Needs approval",
  blocked: "Blocked",
  needs_info: "Needs info",
};

/** "What each agent did": one card per agent, from its finished turns in this run. */
export function AgentSummaries({ events, finished }: { events: AgentEvent[]; finished: boolean }) {
  const turns = events.filter((e) => e.event === "agent_end" && e.agent);
  if (turns.length === 0) return null;
  return (
    <section className="summaries" aria-label="What each agent did">
      <div className="section-title">
        <h3>What each agent did</h3>
        <span className="hint">{finished ? "This run, start to finish" : "So far"}</span>
      </div>
      <div className="summary-grid">
        {ORDER.map((name) => {
          const mine = turns.filter((t) => t.agent === name);
          if (mine.length === 0) {
            return finished ? (
              <div key={name} className={`summary-card agent-${name} skipped`}>
                <div className="summary-head">
                  <span className="summary-icon"><AgentIcon name={name} size={18} /></span>
                  <strong>{AGENTS[name].title}</strong>
                </div>
                <p className="muted">Not needed on this ticket.</p>
              </div>
            ) : null;
          }
          const last = mine[mine.length - 1];
          const actions = mine.flatMap((t) => t.actions_taken ?? []);
          return (
            <div key={name} className={`summary-card agent-${name} voice-${name}`}>
              <div className="summary-head">
                <span className="summary-icon"><AgentIcon name={name} size={18} /></span>
                <strong>{AGENTS[name].title}</strong>
                {mine.length > 1 && <span className="desk-turns">asked {mine.length}×</span>}
                {last.status && <span className={`status-chip st-${last.status}`}>{STATUS_WORD[last.status] ?? last.status}</span>}
              </div>
              <p>{last.said}</p>
              {actions.length > 0 && (
                <ul className="summary-actions">
                  {actions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** The reply Customer Service drafted, shown as a letter a person can copy and send. */
export function CustomerDraft({ events, ticket }: { events: AgentEvent[]; ticket: Ticket }) {
  const [copied, setCopied] = useState(false);
  const draft = [...events].reverse().find((e) => e.event === "agent_end" && e.customer_message)?.customer_message;
  if (!draft) return null;
  const copy = async () => {
    await navigator.clipboard.writeText(draft);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  return (
    <section className="letter" aria-label="Draft reply">
      <div className="letter-head">
        <span>
          Draft reply to <strong>{ticket.requester}</strong>
        </span>
        <button className="btn small ghost" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className="letter-body">{draft}</div>
      <div className="letter-foot">Drafted by Customer Service · a person reviews and sends it</div>
    </section>
  );
}

/** The Boss's closing report: what a person must approve, if anything. */
export function BossApprovals({ events }: { events: AgentEvent[] }) {
  const boss = [...events].reverse().find((e) => e.event === "agent_end" && e.depth === 0);
  const items = boss?.approvals_needed ?? [];
  if (!items.length) return null;
  return (
    <ul className="boss-approvals">
      {items.map((a, i) => (
        <li key={i}>
          <strong>{a.action}</strong>
          {a.amount ? <span className="num"> {money(a.amount)}</span> : null}
          <span className="muted"> {a.reason}</span>
        </li>
      ))}
    </ul>
  );
}
