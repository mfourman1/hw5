import { useEffect, useRef, useState } from "react";
import type { Cash } from "../api";
import { money, wholeMoney } from "../format";
import { useTweened } from "../hooks";

export interface CashEntry {
  time: string;
  amount: number;
  payee: string;
  label: string;
  approvedBy: string;
  ticketId?: number;
}

interface Props {
  shopDate?: string;
  cash: Cash | null;
  startBalance?: number;
  cashLog: CashEntry[];
  onReset: () => void;
  resetDisabled: boolean;
}

export function TopBar({ shopDate, cash, startBalance, cashLog, onReset, resetDisabled }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark" aria-hidden>
          CC
        </div>
        <div>
          <div className="brand-name">Campus Customs</div>
          <div className="brand-sub">Operations Desk · Chapel Street, New Haven</div>
        </div>
      </div>
      <div className="topbar-right">
        {shopDate && (
          <div className="shop-date" title="The shop's date (desk.date_today). Every agent counts days from here.">
            <span className="label">Shop date</span>
            {new Date(shopDate + "T12:00:00").toLocaleDateString("en-US", {
              weekday: "short",
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </div>
        )}
        <CashCard cash={cash} startBalance={startBalance} cashLog={cashLog} />
        <button className="btn ghost-light" onClick={onReset} disabled={resetDisabled} title="Put the working database back to the original values">
          Reset desk
        </button>
      </div>
    </header>
  );
}

function CashCard({ cash, startBalance, cashLog }: { cash: Cash | null; startBalance?: number; cashLog: CashEntry[] }) {
  const shown = useTweened(cash?.balance);
  const [flash, setFlash] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const previous = useRef<number | undefined>(undefined);

  // Show the change (e.g. −$840.00) for a few seconds after the balance moves.
  useEffect(() => {
    if (cash === null) return;
    if (previous.current !== undefined && previous.current !== cash.balance) {
      setFlash(cash.balance - previous.current);
      const t = window.setTimeout(() => setFlash(null), 4500);
      previous.current = cash.balance;
      return () => window.clearTimeout(t);
    }
    previous.current = cash.balance;
  }, [cash]);

  if (!cash) return <div className="cash-card loading">Checking …</div>;
  const scale = Math.max(startBalance ?? cash.balance, cash.balance, cash.cash_buffer * 2);
  const fill = Math.max(0, Math.min(100, (cash.balance / scale) * 100));
  const bufferAt = (cash.cash_buffer / scale) * 100;
  // Money set aside for priority payments (rent) waiting for approval, shaded red at the end of the fill.
  const earmarked = Math.min(cash.earmarked ?? 0, cash.balance);
  const earmarkWidth = (earmarked / scale) * 100;
  const short = (cash.earmarked ?? 0) > cash.balance;
  const earmarkTitle = (cash.earmarks ?? [])
    .map((e) => `${money(e.amount)} ${e.kind} to ${e.payee} (#${e.ticket_id})`)
    .join(", ");

  return (
    <div className={`cash-card${cash.below_buffer ? " low" : ""}${earmarked > 0 ? " earmarked" : ""}`}>
      <button className="cash-main" onClick={() => setOpen((o) => !o)} aria-expanded={open} title="Show the cash log">
        <span className="label">Checking</span>
        <span className="cash-amount">{money(shown ?? cash.balance)}</span>
        {flash !== null && <span className={`cash-delta ${flash < 0 ? "down" : "up"}`}>{flash < 0 ? "−" : "+"}{money(Math.abs(flash))}</span>}
      </button>
      <div className="cash-meter" title={`The shop keeps at least ${wholeMoney(cash.cash_buffer)} in checking`}>
        <div className="cash-fill" style={{ width: `${fill}%` }} />
        {earmarked > 0 && (
          <div
            className="cash-earmark"
            style={{ left: `${fill - earmarkWidth}%`, width: `${earmarkWidth}%` }}
            title={`Earmarked for priority payments: ${earmarkTitle}`}
          />
        )}
        <div className="cash-buffer-line" style={{ left: `${bufferAt}%` }} />
      </div>
      <div className="cash-foot">
        {earmarked > 0 ? (
          <span className="earmark-text">
            {short ? "Short for priority payments: " : `${money(cash.earmarked)} earmarked for priority · `}
            {short ? money(cash.earmarked) : `${money(cash.free_after_earmarks)} free`}
          </span>
        ) : cash.below_buffer ? (
          `Below the ${wholeMoney(cash.cash_buffer)} buffer`
        ) : (
          `${wholeMoney(cash.cash_buffer)} buffer`
        )}
      </div>
      {open && (
        <div className="cash-log" role="dialog" aria-label="Cash log">
          <div className="cash-log-title">Cash since the last reset</div>
          {startBalance !== undefined && (
            <div className="cash-log-row muted">
              <span>Starting balance</span>
              <span className="num">{money(startBalance)}</span>
            </div>
          )}
          {cashLog.length === 0 && <div className="cash-log-empty">No payments approved yet.</div>}
          {cashLog.map((e) => (
            <div key={e.time} className="cash-log-row">
              <span>
                {e.label}
                <small>
                  {e.ticketId ? `#${e.ticketId} · ` : ""}approved by {e.approvedBy}
                </small>
              </span>
              <span className="num down">−{money(e.amount)}</span>
            </div>
          ))}
          <div className="cash-log-row total">
            <span>Now</span>
            <span className="num">{money(cash.balance)}</span>
          </div>
          {(cash.earmarks ?? []).map((e) => (
            <div key={`${e.kind}-${e.ref_id}`} className="cash-log-row earmark">
              <span>
                Earmarked: {e.kind === "rent" ? "Rent" : e.kind} · {e.payee}
                <small>#{e.ticket_id} · priority payment waiting for your approval</small>
              </span>
              <span className="num">{money(e.amount)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
