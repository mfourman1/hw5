import { useEffect, useMemo, useRef, type CSSProperties } from "react";
import type { AgentEvent, AgentName } from "../api";
import { AgentBadge } from "../agents";
import { clock, money, seconds, sinceStart, toolArgs, toolName, toolResult } from "../format";
import { useElapsed } from "../hooks";

const STATUS_WORD: Record<string, string> = {
  done: "done",
  needs_approval: "needs approval",
  blocked: "blocked",
  needs_info: "needs info",
};

// How long a gap between two steps has to be before the feed points it out.
const NOTE_MS = 5_000; // shown quietly
const SLOW_MS = 15_000; // amber
const STUCK_MS = 45_000; // red

function waitClass(ms: number): string {
  return ms >= STUCK_MS ? " stuck" : ms >= SLOW_MS ? " slow" : "";
}

/** Steps the feed shows (it hides the plumbing between them). */
function shown(e: AgentEvent): boolean {
  switch (e.event) {
    case "task_start":
    case "task_end":
    case "delegation_refused":
    case "agent_error":
      return true;
    case "agent_start":
    case "agent_end":
      return Boolean(e.agent);
    case "model_response":
      return Boolean(e.agent) && ((e.tools ?? []).some((t) => !t.tool.startsWith("ask_")) || Boolean(e.said && !e.final));
    default:
      return false;
  }
}

export function LiveFeed({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const scroller = useRef<HTMLDivElement>(null);
  const results = useMemo(() => {
    const map = new Map<string, unknown>();
    for (const e of events) for (const r of e.tool_results ?? []) map.set(r.call_id, r.result);
    return map;
  }, [events]);
  const started = events.find((e) => e.event === "task_start")?.time;
  const lastTime = events.length ? events[events.length - 1].time : started;

  // Each step's time since the run started, and how long it came after the step before it.
  const rows = useMemo(() => {
    const start = started ? new Date(started).getTime() : undefined;
    let previous: number | undefined;
    return events.filter(shown).map((e) => {
      const at = new Date(e.time).getTime();
      const gap = previous === undefined ? 0 : at - previous;
      previous = at;
      return { e, sinceStart: start === undefined ? 0 : at - start, gap };
    });
  }, [events, started]);

  // Follow the newest line while the run is live, unless the reader has scrolled up.
  useEffect(() => {
    const el = scroller.current;
    if (!el || !running) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  }, [events.length, running]);

  return (
    <section className="feed" aria-label="Live agent feed">
      <div className="section-title">
        <h3>Live feed</h3>
        {running && (
          <span className="live-tag">
            <span className="pulse-dot" aria-hidden /> live
          </span>
        )}
      </div>
      <div className="feed-scroll" ref={scroller}>
        {events.length === 0 && (
          <div className="feed-empty">
            {running ? "Waking the team…" : "Nothing yet. Send the ticket to the team and every step shows up here."}
          </div>
        )}
        {rows.map(({ e, sinceStart: at, gap }) => (
          <div key={e.seq} className={`feed-row${gap >= NOTE_MS ? waitClass(gap) || " noted" : ""}`}>
            <div
              className="feed-time"
              title={`${clock(e.time)}${gap ? ` · ${Math.round(gap / 1000)}s after the step before` : ""}`}
            >
              <span className="feed-clock">{sinceStart(at)}</span>
              {gap >= NOTE_MS && <span className="feed-wait">{Math.round(gap / 1000)}s wait</span>}
            </div>
            <div className="feed-item">
              <FeedItem e={e} results={results} started={started} />
            </div>
          </div>
        ))}
        {running && events.length > 0 && <StillWorking since={lastTime} />}
      </div>
    </section>
  );
}

/** The live "waiting for the next step" line: it counts up and turns amber, then red, if a step hangs. */
function StillWorking({ since }: { since?: string }) {
  const waited = useElapsed(since, true);
  const ms = waited * 1000;
  return (
    <div className={`feed-row live${waitClass(ms)}`}>
      <div className="feed-time">
        <span className="feed-wait">{waited}s</span>
      </div>
      <div className="feed-item still-working">
        <span className="feed-typing" aria-hidden>
          <span />
          <span />
          <span />
        </span>
        {ms >= STUCK_MS
          ? `No new step for ${waited}s. This one is taking unusually long.`
          : ms >= SLOW_MS
            ? `Still on the same step (${waited}s)…`
            : "Waiting for the next step…"}
      </div>
    </div>
  );
}

function FeedItem({ e, results, started }: { e: AgentEvent; results: Map<string, unknown>; started?: string }) {
  const indent = { "--depth": e.depth ?? 0 } as CSSProperties;
  const agent = e.agent as AgentName | undefined;
  switch (e.event) {
    case "task_start":
      return (
        <div className="feed-sys">
          Run started {clock(e.time)}
          {e.dry_run && <span className="practice-tag">practice run · nothing saved</span>}
        </div>
      );
    case "agent_start":
      if (!agent) return null;
      if ((e.depth ?? 0) === 0) {
        return (
          <div className="feed-line" style={indent}>
            <AgentBadge name={agent} /> <span className="feed-verb">picks up the ticket</span>
          </div>
        );
      }
      return (
        <div className="feed-handoff" style={indent}>
          <div className="handoff-route">
            {e.asked_by && e.asked_by !== "manager" && <AgentBadge name={e.asked_by} small />}
            <span className="arrow" aria-hidden>→</span>
            <AgentBadge name={agent} small />
          </div>
          <blockquote>{e.said}</blockquote>
        </div>
      );
    case "model_response": {
      const own = (e.tools ?? []).filter((t) => !t.tool.startsWith("ask_"));
      const said = e.said && !e.final ? e.said : null;
      if (!agent || (!own.length && !said)) return null;
      return (
        <div className={`feed-step voice-${agent}`} style={indent}>
          <AgentBadge name={agent} small />
          {own.length > 0 && (
            <div className="tool-chips">
              {own.map((t, i) => {
                const result = t.call_id ? toolResult(t.tool, results.get(t.call_id)) : null;
                return (
                  <span className="tool-chip" key={t.call_id ?? i}>
                    <span className="tool-name">{toolName(t.tool)}</span>
                    {toolArgs(t.tool, t.args) && <span className="tool-args">{toolArgs(t.tool, t.args)}</span>}
                    {result && <span className="tool-result">→ {result}</span>}
                  </span>
                );
              })}
            </div>
          )}
          {said && <p className="feed-said">{said}</p>}
        </div>
      );
    }
    case "agent_end":
      if (!agent) return null;
      return (
        <div className={`feed-bubble voice-${agent}`} style={indent}>
          <div className="bubble-head">
            <AgentBadge name={agent} small />
            {e.status && <span className={`status-chip st-${e.status}`}>{STATUS_WORD[e.status] ?? e.status}</span>}
          </div>
          <p>{e.said}</p>
          {e.approvals_needed && e.approvals_needed.length > 0 && (
            <ul className="bubble-approvals">
              {e.approvals_needed.map((a, i) => (
                <li key={i}>
                  Needs a person: {a.action}
                  {a.amount ? ` (${money(a.amount)})` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    case "delegation_refused":
      return (
        <div className="feed-warn" style={indent}>
          {agent && <AgentBadge name={agent} small />} couldn't hand off: {e.said}
        </div>
      );
    case "agent_error":
      return (
        <div className="feed-error" style={indent}>
          {agent && <AgentBadge name={agent} small />} hit an error: {e.said}
        </div>
      );
    case "task_end": {
      const took = started ? new Date(e.time).getTime() - new Date(started).getTime() : undefined;
      return (
        <div className={`feed-sys end${e.stop_reason === "final_answer" ? "" : " bad"}`}>
          {e.stop_reason === "final_answer" ? "Run finished" : `Run stopped (${e.stop_reason})`}
          {took ? ` in ${seconds(took)}` : ""}
          {e.usage && ` · ${e.usage.requests} model requests · ${Math.round(e.usage.total_tokens / 1000)}k tokens`}
        </div>
      );
    }
    default:
      return null;
  }
}
