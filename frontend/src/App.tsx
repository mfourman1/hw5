import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_URL, api, type Cash, type Ticket, type TicketSource } from "./api";
import { DESK_LABEL, money } from "./format";
import { useRunEvents, useStoredState } from "./hooks";
import { TicketQueue, queueOrder } from "./components/TicketQueue";
import { TicketView } from "./components/TicketView";
import { TopBar, type CashEntry } from "./components/TopBar";

interface Toast {
  id: number;
  text: string;
  tone: "info" | "good" | "bad";
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [shopDate, setShopDate] = useState<string>();
  const [cash, setCash] = useState<Cash | null>(null);
  const [cashLog, setCashLog] = useState<CashEntry[]>([]);
  // The address can name a ticket (http://localhost:5173/#103), so a ticket can be linked or bookmarked.
  const [selectedId, setSelected] = useState<number | null>(() => Number(location.hash.slice(1)) || null);
  const setSelectedId = useCallback((update: number | null | ((id: number | null) => number | null)) => {
    setSelected((current) => {
      const next = typeof update === "function" ? update(current) : update;
      if (next !== null && location.hash !== `#${next}`) history.replaceState(null, "", `#${next}`);
      return next;
    });
  }, []);
  const [offline, setOffline] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [practice, setPractice] = useState(false);
  const [approver, setApprover] = useStoredState("cc-approver", "");
  // Runs this page just started, until /api/tickets shows them (the backend starts them a moment later).
  const [started, setStarted] = useState<Record<number, { taskId: string; at: string }>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const lastStates = useRef<Record<number, string>>({});

  const toast = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  const refreshCashLog = useCallback(async () => {
    const { events } = await api.events({ limit: 500 });
    const lastReset = events.map((e) => e.event).lastIndexOf("database_reset");
    setCashLog(
      events
        .slice(lastReset + 1)
        .filter((e) => e.event === "payment_approved")
        .map((e) => ({
          time: e.time,
          amount: e.amount ?? 0,
          payee: e.payee ?? "",
          label: `${e.kind === "rent" ? "Rent" : e.kind === "purchase" ? "Purchase order " + e.ref_id : "Invoice " + e.ref_id} · ${e.payee}`,
          approvedBy: e.approved_by ?? "",
          ticketId: e.ticket_id,
        })),
    );
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [t, c] = await Promise.all([api.tickets(), api.cash()]);
      setTickets(t.tickets);
      setShopDate(t.shop_date);
      setCash(c);
      setOffline(null);
      setSelectedId((id) => id ?? pickFirst(t.tickets));
      // Tell the person when a run they were waiting on comes back.
      for (const tk of t.tickets) {
        const before = lastStates.current[tk.id];
        if (before === "running" && tk.desk_state !== "running") {
          const tone = tk.desk_state === "resolved" ? "good" : tk.desk_state === "needs_attention" ? "bad" : "info";
          toast(
            tk.last_run?.dry_run
              ? `Ticket #${tk.id}: practice run finished. Nothing was saved.`
              : `Ticket #${tk.id}: the team finished — ${DESK_LABEL[tk.desk_state].toLowerCase()}.`,
            tone,
          );
        }
        lastStates.current[tk.id] = tk.desk_state;
      }
      setStarted((s) => {
        const next = { ...s };
        for (const tk of t.tickets) if (next[tk.id] && tk.last_run?.task_id === next[tk.id].taskId) delete next[tk.id];
        return next;
      });
    } catch (err) {
      setOffline(err instanceof Error ? err.message : String(err));
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
    void refreshCashLog().catch(() => undefined);
  }, [refresh, refreshCashLog]);

  const anyRunning = tickets.some((t) => t.desk_state === "running") || Object.keys(started).length > 0;
  // Refresh fast while the team works, retry every few seconds while the backend is down,
  // and otherwise check in every 15 seconds.
  useEffect(() => {
    const timer = window.setInterval(refresh, anyRunning ? 2000 : offline ? 3000 : 15000);
    return () => window.clearInterval(timer);
  }, [refresh, anyRunning, offline]);

  const ticket = tickets.find((t) => t.id === selectedId) ?? null;
  const pendingStart = ticket ? started[ticket.id] : undefined;
  const taskId = pendingStart?.taskId ?? ticket?.last_run?.task_id;
  const running = Boolean(pendingStart) || ticket?.desk_state === "running";
  const events = useRunEvents(taskId, running);
  const startBalance = useMemo(
    () => (cash ? cash.balance + cashLog.reduce((sum, e) => sum + e.amount, 0) : undefined),
    [cash, cashLog],
  );

  async function act(name: string, work: () => Promise<void>) {
    setBusy(name);
    try {
      await work();
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), "bad");
    } finally {
      setBusy(null);
    }
  }

  const run = () =>
    ticket &&
    act("run", async () => {
      const res = await api.run(ticket.id, practice);
      setStarted((s) => ({ ...s, [ticket.id]: { taskId: res.task_id, at: new Date().toISOString() } }));
      lastStates.current[ticket.id] = "running";
      toast(`Ticket #${ticket.id} is with the team${practice ? " (practice run)" : ""}.`);
    });

  const approve = () =>
    ticket &&
    act("approve", async () => {
      const paid = await api.approve(ticket.id, approver.trim());
      toast(
        `${paid.kind === "purchase" ? "Bought" : "Paid"} ${money(paid.amount)} ${paid.kind === "purchase" ? "from" : "to"} ${paid.payee}.${paid.ticket_resolved ? ` Ticket #${ticket.id} is resolved.` : ""}`,
        "good",
      );
      await Promise.all([refresh(), refreshCashLog()]);
    });

  const setSource = (source: TicketSource | null) =>
    ticket &&
    act("source", async () => {
      await api.setSource(ticket.id, source);
      await refresh();
    });

  const resolve = (note: string) =>
    ticket &&
    act("resolve", async () => {
      await api.resolve(ticket.id, approver.trim(), note || undefined);
      toast(`Ticket #${ticket.id} signed off and resolved.`, "good");
      await refresh();
    });

  const reset = () =>
    act("reset", async () => {
      if (!window.confirm("Reset the desk? This puts every ticket, payment and the checking balance back to the original values. The audit trail is kept.")) return;
      const res = await api.reset();
      setStarted({});
      toast(`Desk reset. Checking is back to ${money(res.checking_balance)}.`, "good");
      await Promise.all([refresh(), refreshCashLog()]);
    });

  return (
    <div className="app">
      <TopBar shopDate={shopDate} cash={cash} startBalance={startBalance} cashLog={cashLog} onReset={reset} resetDisabled={busy !== null || anyRunning} />
      {offline && (
        <div className="offline" role="alert">
          <strong>The desk can't reach the backend.</strong> {offline} Start it from <code>backend/</code> with{" "}
          <code>uvicorn main:app --reload --port 8000</code>. Looking for it at {API_URL}.
        </div>
      )}
      <div className="layout">
        <TicketQueue tickets={tickets} selectedId={selectedId} onSelect={setSelectedId} />
        <main className="workspace">
          {ticket ? (
            <TicketView
              key={ticket.id}
              ticket={ticket}
              events={events}
              running={running}
              runStarted={pendingStart?.at ?? (running ? ticket.last_run?.started : undefined)}
              approver={approver}
              setApprover={setApprover}
              practice={practice}
              setPractice={setPractice}
              busy={busy}
              onRun={run}
              onApprove={approve}
              onResolve={resolve}
              onSetSource={setSource}
            />
          ) : (
            !offline && <div className="empty-workspace">Loading the desk…</div>
          )}
        </main>
      </div>
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Start on the top of the queue: the open ticket with the nearest deadline. */
function pickFirst(tickets: Ticket[]): number | null {
  return queueOrder(tickets)[0]?.id ?? null;
}
