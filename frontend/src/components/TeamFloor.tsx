import type { AgentEvent, AgentName } from "../api";
import { AGENTS, AgentIcon, SPECIALISTS } from "../agents";
import { toolArgs, toolName } from "../format";

type DeskStatus = "idle" | "working" | "waiting" | "done";

interface Desk {
  state: DeskStatus;
  line?: string;
  tool?: string;
  turns: number;
  status?: string;
  waitingOn?: AgentName[];
}

const NAMES: AgentName[] = ["boss", ...SPECIALISTS];

/** Where each agent is right now, replayed from the run's events. */
export function deskStates(events: AgentEvent[]): Record<AgentName, Desk> {
  const desks = Object.fromEntries(NAMES.map((n) => [n, { state: "idle", turns: 0 } as Desk])) as Record<AgentName, Desk>;
  for (const e of events) {
    if (!e.agent || !desks[e.agent]) continue;
    const d = desks[e.agent];
    switch (e.event) {
      case "agent_start":
        d.state = "working";
        d.turns += 1;
        d.tool = undefined;
        d.line = e.asked_by && e.asked_by !== "manager" ? `Asked by ${AGENTS[e.asked_by].title}: ${e.said ?? ""}` : "Picked up the ticket";
        break;
      case "model_response": {
        const tools = e.tools ?? [];
        const asks = tools.filter((t) => t.tool.startsWith("ask_"));
        const own = tools.filter((t) => !t.tool.startsWith("ask_"));
        if (own.length) {
          const t = own[own.length - 1];
          d.tool = `${toolName(t.tool)} ${toolArgs(t.tool, t.args)}`.trim();
          d.line = own.length > 1 ? `Using ${own.length} tools` : `Using ${toolName(t.tool)}`;
        }
        if (asks.length) {
          d.state = "waiting";
          if (!own.length) d.tool = undefined;
          d.waitingOn = asks.map((t) => t.tool.slice(4) as AgentName);
          d.line = `Handed work to ${d.waitingOn.map((n) => AGENTS[n]?.title ?? n).join(" and ")}`;
        }
        if (e.said && !e.final) d.line = e.said;
        break;
      }
      case "model_request":
        if (d.state === "waiting") d.state = "working";
        break;
      case "agent_end":
        d.state = "done";
        d.status = e.status;
        d.line = e.said;
        d.tool = undefined;
        break;
      case "agent_error":
        d.state = "done";
        d.status = "error";
        d.line = e.said;
        break;
    }
  }
  return desks;
}

const STATUS_WORD: Record<string, string> = {
  done: "Done",
  needs_approval: "Needs approval",
  blocked: "Blocked",
  needs_info: "Needs info",
  error: "Error",
};

function DeskCard({ name, desk, finished }: { name: AgentName; desk: Desk; finished: boolean }) {
  const look = AGENTS[name];
  const skipped = finished && desk.turns === 0;
  const light =
    desk.state === "working" ? "Working" : desk.state === "waiting" ? "Waiting on a teammate" : desk.state === "done" ? STATUS_WORD[desk.status ?? "done"] ?? "Done" : skipped ? "Not needed" : "Ready";
  return (
    <div className={`desk-card agent-${name} is-${desk.state}${skipped ? " skipped" : ""}`}>
      <div className="desk-avatar">
        <AgentIcon name={name} size={24} />
      </div>
      <div className="desk-body">
        <div className="desk-name">
          {look.title}
          {desk.turns > 1 && <span className="desk-turns">asked {desk.turns}×</span>}
        </div>
        <div className="desk-role">{look.role}</div>
        <div className={`desk-light ${desk.state}${desk.status ? ` st-${desk.status}` : ""}`}>
          <span className="dot" aria-hidden />
          {light}
        </div>
        {desk.line && !skipped && <p className="desk-line">{desk.line}</p>}
        {desk.tool && desk.state !== "done" && <div className="desk-tool">{desk.tool}</div>}
        {skipped && <p className="desk-line muted">Not called on this ticket.</p>}
      </div>
    </div>
  );
}

export function TeamFloor({ events, finished }: { events: AgentEvent[]; finished: boolean }) {
  const desks = deskStates(events);
  const called = (n: AgentName) => desks[n].turns > 0;
  return (
    <section className="floor" aria-label="The team">
      <div className="section-title">
        <h3>The team</h3>
        <span className="hint">Boss routes the work; specialists light up when they're called.</span>
      </div>
      <div className="floor-boss">
        <DeskCard name="boss" desk={desks.boss} finished={finished} />
      </div>
      <div className="floor-wires" aria-hidden>
        {SPECIALISTS.map((n) => (
          <span key={n} className={`wire agent-${n}${called(n) ? " live" : ""}${desks[n].state === "working" ? " busy" : ""}`} />
        ))}
      </div>
      <div className="floor-specialists">
        {SPECIALISTS.map((n) => (
          <DeskCard key={n} name={n} desk={desks[n]} finished={finished} />
        ))}
      </div>
    </section>
  );
}
