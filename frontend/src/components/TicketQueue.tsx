import type { Ticket } from "../api";
import { DESK_LABEL, SOURCE_LABEL, TYPE_LABEL, URGENCY_LABEL, dueLine } from "../format";

/** Exact deadline time for sorting: the reply-by time for inquiries, otherwise the due date. */
function deadlineMs(t: Ticket): number {
  const u = t.urgency;
  if (u.reply_by && u.deadline_source?.includes("reply window")) return new Date(u.reply_by).getTime();
  return u.deadline ? new Date(u.deadline + "T23:59:59").getTime() : Number.POSITIVE_INFINITY;
}

/** Open tickets by deadline: overdue first, then the ones due soonest, then later ones, then
 *  tickets with no deadline. Resolved tickets sink to the bottom. */
export function queueOrder(tickets: Ticket[]): Ticket[] {
  return [...tickets].sort((a, b) => Number(!a.open) - Number(!b.open) || deadlineMs(a) - deadlineMs(b) || a.id - b.id);
}

export function TicketQueue({ tickets, selectedId, onSelect }: { tickets: Ticket[]; selectedId: number | null; onSelect: (id: number) => void }) {
  const sorted = queueOrder(tickets);
  const resolved = tickets.filter((t) => !t.open).length;

  return (
    <nav className="queue" aria-label="Ticket queue">
      <div className="queue-head">
        <h2>Ticket queue</h2>
        <span className="queue-count">
          {resolved}/{tickets.length} resolved
        </span>
      </div>
      <div className="queue-progress" aria-hidden>
        {tickets.map((t) => (
          <span key={t.id} className={t.open ? "" : "done"} />
        ))}
      </div>
      <div className="queue-sort">Sorted by deadline · overdue first</div>
      <ul>
        {sorted.map((t) => {
          const due = dueLine(t);
          return (
            <li key={t.id}>
              <button
                className={`ticket-card state-${t.desk_state}${t.id === selectedId ? " selected" : ""}`}
                onClick={() => onSelect(t.id)}
                aria-current={t.id === selectedId}
              >
                <div className="ticket-card-top">
                  <span className="ticket-id">#{t.id}</span>
                  <span className="ticket-type">{TYPE_LABEL[t.type] ?? t.type}</span>
                  {t.open && <span className={`urgency-chip ${t.urgency.urgency}`}>{URGENCY_LABEL[t.urgency.urgency] ?? t.urgency.urgency}</span>}
                </div>
                <div className="ticket-subject">{t.subject}</div>
                <div className="ticket-requester">
                  {t.requester}
                  {t.source && <span className="source-chip">{SOURCE_LABEL[t.source]}</span>}
                </div>
                {t.open && (
                  <div className={`ticket-due ${t.urgency.urgency}`}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                      <circle cx="12" cy="12" r="9" />
                      <path d="M12 7v5l3 2" />
                    </svg>
                    {due ? (
                      <span>
                        {due.text}
                        <strong> · {due.when}</strong>
                      </span>
                    ) : (
                      <span>No due date</span>
                    )}
                  </div>
                )}
                <div className="ticket-card-foot">
                  <span className={`state-pill ${t.desk_state}`}>
                    {t.desk_state === "running" && <span className="pulse-dot" aria-hidden />}
                    {DESK_LABEL[t.desk_state]}
                  </span>
                  {t.priority && <span className="priority-chip">Priority payment</span>}
                </div>
                {!t.open && (
                  <span className="stamp" aria-hidden>
                    Resolved
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
