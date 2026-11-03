import { useEffect, useRef, useState } from "react";
import { api, type AgentEvent } from "./api";

/** Every audit event of one run. While `live`, new events are fetched every 1.2 seconds. */
export function useRunEvents(taskId: string | undefined, live: boolean): AgentEvent[] {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const lastSeq = useRef(-1);
  const busy = useRef(false);

  useEffect(() => {
    setEvents([]);
    lastSeq.current = -1;
    if (!taskId) return;
    let stopped = false;
    const load = async () => {
      if (busy.current) return;
      busy.current = true;
      try {
        const res = await api.events({ taskId, after: lastSeq.current });
        if (!stopped && res.events.length) {
          lastSeq.current = res.events[res.events.length - 1].seq;
          setEvents((prev) => [...prev, ...res.events]);
        }
      } catch {
        /* the next poll tries again */
      } finally {
        busy.current = false;
      }
    };
    void load();
    if (!live) return () => void (stopped = true);
    const timer = window.setInterval(load, 1200);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [taskId, live]);

  return events;
}

/** A value saved in the browser, so the approver's name survives a refresh. */
export function useStoredState(key: string, initial: string): [string, (v: string) => void] {
  const [value, setValue] = useState(() => localStorage.getItem(key) ?? initial);
  const set = (v: string) => {
    setValue(v);
    localStorage.setItem(key, v);
  };
  return [value, set];
}

/** Glides a number to its new value, so a payment visibly drains the balance. */
export function useTweened(target: number | undefined, ms = 1100): number | undefined {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (target === undefined) return;
    const start = from.current;
    from.current = target;
    if (start === undefined || start === target) {
      setShown(target);
      return;
    }
    const t0 = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / ms);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(start + (target - start) * eased);
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, ms]);
  return shown;
}

/** Seconds since `iso`, ticking once a second while `on`. */
export function useElapsed(iso: string | undefined, on: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [on]);
  return iso ? Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000)) : 0;
}
