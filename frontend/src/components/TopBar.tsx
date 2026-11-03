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

  return (
    <div className={`cash-card${cash.below_buffer ? " low" : ""}`}>
      <button className="cash-main" onClick={() => setOpen((o) => !o)} aria-expanded={open} title="Show the cash log">
        <span className="label">Checking</span>
        <span className="cash-amount">{money(shown ?? cash.balance)}</span>
        {flash !== null && <span className={`cash-delta ${flash < 0 ? "down" : "up"}`}>{flash < 0 ? "−" : "+"}{money(Math.abs(flash))}</span>}
      </button>
      <div className="cash-meter" title={`The shop keeps at least ${wholeMoney(cash.cash_buffer)} in checking`}>
        <div className="cash-fill" style={{ width: `${fill}%` }} />
        <div className="cash-buffer-line" style={{ left: `${bufferAt}%` }} />
      </div>
      <div className="cash-foot">
        {cash.below_buffer ? `Below the ${wholeMoney(cash.cash_buffer)} buffer` : `${wholeMoney(cash.cash_buffer)} buffer`}
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
        </div>
      )}
    </div>
  );
}
