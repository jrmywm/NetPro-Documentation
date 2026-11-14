import React, { useEffect, useState } from "react";
import { formatAgo, MAX_CUSTOM_MS } from "../hooks/usePacketTimeline";

const localInputValue = (time) => {
  if (!Number.isFinite(time)) return "";
  const date = new Date(time - new Date(time).getTimezoneOffset() * 60000);
  return date.toISOString().slice(0, 16);
};

export default function TimeRangeControls({ timeline }) {
  const { selection, paused, choosePreset, applyCustom, pause, resumeLive } = timeline;
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [validation, setValidation] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (selection.kind === "custom") {
      setStart(localInputValue(selection.start));
      setEnd(localInputValue(selection.end));
    }
  }, [selection]);

  const submitCustom = (event) => {
    event.preventDefault();
    const from = new Date(start).getTime();
    const to = new Date(end).getTime();
    const now = Date.now();
    if (!Number.isFinite(from) || !Number.isFinite(to) || from >= to) return setValidation("Choose a start before the end.");
    if (to > now) return setValidation("The end time must not be in the future.");
    if (to - from > MAX_CUSTOM_MS) return setValidation("Custom ranges are limited to 24 hours.");
    setValidation("");
    applyCustom(from, to);
  };

  return (
    <section className="my-4 rounded border border-gray-200 bg-white p-4" aria-label="Chart time window">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">Time window</span>
        {[ ["5m", "Last 5 minutes"], ["15m", "Last 15 minutes"], ["1h", "Last hour"] ].map(([key, label]) => (
          <button key={key} type="button" aria-pressed={selection.kind === "preset" && selection.preset === key}
            className={`rounded border px-3 py-1 ${selection.kind === "preset" && selection.preset === key ? "bg-blue-700 text-white" : "bg-white"}`} onClick={() => choosePreset(key)}>{label}</button>
        ))}
        {paused
          ? <button type="button" className="rounded bg-green-700 px-3 py-1 text-white" onClick={resumeLive}>Live</button>
          : <button type="button" className="rounded border px-3 py-1" onClick={pause}>Pause</button>}
        <span className="text-sm text-gray-600">{paused ? "Paused" : "Live · refreshes every 5 seconds"}</span>
      </div>
      <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={submitCustom}>
        <label className="text-sm">Custom start (local time)
          <input aria-label="Custom start" type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} className="ml-2 rounded border p-1" />
        </label>
        <label className="text-sm">Custom end (local time)
          <input aria-label="Custom end" type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} className="ml-2 rounded border p-1" />
        </label>
        <button type="submit" className="rounded border px-3 py-1">Apply custom range</button>
      </form>
      {selection.kind === "custom" && <p className="mt-2 text-sm">Custom range · paused · local timezone</p>}
      {validation && <p role="alert" className="mt-2 text-sm text-red-700">{validation}</p>}
      <div className="mt-2 text-sm" aria-live="polite">
        <span>Last sample: {formatAgo(timeline.lastSampleAt, now)}</span>
        {timeline.refreshedAt && <span className="ml-4">Updated {formatAgo(timeline.refreshedAt, now)}</span>}
      </div>
      {timeline.loading && <p className="mt-2 text-sm">Loading samples…</p>}
      {timeline.error && <p role="alert" className="mt-2 text-sm text-red-700">Timeline request failed: {timeline.error}</p>}
      {!timeline.loading && !timeline.error && !timeline.samples.length && <p className="mt-2 text-sm">No samples in this time window.</p>}
      {timeline.partial && <p role="status" className="mt-2 text-sm text-amber-800">History limit reached (20,000 samples); this time window is only partially covered.</p>}
    </section>
  );
}
