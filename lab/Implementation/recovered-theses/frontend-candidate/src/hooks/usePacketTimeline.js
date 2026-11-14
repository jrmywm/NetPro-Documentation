import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";

export const PAGE_SIZE = 1000;
export const MAX_PAGES = 20;
export const POLL_MS = 5000;
export const MAX_CUSTOM_MS = 24 * 60 * 60 * 1000;
export const RANGE_MS = { "5m": 5 * 60000, "15m": 15 * 60000, "1h": 3600000 };

export function timestampOf(row) {
  const value = row?.time ?? row?.timestamp;
  const time = value == null ? NaN : new Date(value).getTime();
  return Number.isFinite(time) ? time : null;
}

export function packetKey(row) {
  const id = row?.packet_id ?? row?.packetId ?? row?.id;
  return id == null ? `${timestampOf(row)}:${JSON.stringify(row)}` : String(id);
}

export function normalizePackets(rows, start, end) {
  const seen = new Set();
  return (Array.isArray(rows) ? rows : []).flatMap((row) => {
    const time = timestampOf(row);
    if (!row || time == null || time < start || time > end) return [];
    const key = packetKey(row);
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ ...row, _time: time, _key: key }];
  }).sort((a, b) => a._time - b._time);
}

export function windowFor(selection, now = Date.now()) {
  if (selection.kind === "custom") return { start: selection.start, end: selection.end };
  const span = RANGE_MS[selection.preset] || RANGE_MS["5m"];
  return { start: now - span, end: now };
}

export function formatAgo(value, now = Date.now()) {
  if (!Number.isFinite(value)) return "No samples yet";
  const seconds = Math.max(0, Math.floor((now - value) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

export default function usePacketTimeline({ id, kind }) {
  const [selection, setSelection] = useState({ kind: "preset", preset: "5m" });
  const [paused, setPaused] = useState(false);
  const [windowBounds, setWindowBounds] = useState(() => windowFor({ kind: "preset", preset: "5m" }));
  const [samples, setSamples] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [partial, setPartial] = useState(false);
  const [lastSampleAt, setLastSampleAt] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const activeController = useRef(null);
  const samplesRef = useRef([]);
  const coverageFloor = useRef(null);
  const loadRef = useRef(null);
  const key = `${kind}:${id}:${selection.kind}:${selection.preset || ""}:${selection.start || ""}:${selection.end || ""}`;
  const rowsKey = kind === "npb" ? "npbPackets" : "psPackets";
  const endpoint = kind === "npb" ? "/npb/npb-packet-page/" : "/ps/ps-packet-page/";

  const load = useCallback(async (incremental = false, run = generation.current) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const controller = new AbortController();
    activeController.current = controller;
    const bounds = selection.kind === "custom" ? windowFor(selection) : windowFor(selection, Date.now());
    setWindowBounds(bounds);
    let rows = [];
    let total = null;
    let completed = false;
    let overlapped = false;
    let oldestSeen = null;
    const known = new Set(samplesRef.current.map(packetKey));
    try {
      for (let page = 1; page <= MAX_PAGES; page += 1) {
        const response = await axios.get(
          `${process.env.REACT_APP_BASE_URL}${endpoint}${id}?page=${page}&pageSize=${PAGE_SIZE}`,
          { signal: controller.signal, timeout: 15000 }
        );
        if (run !== generation.current || controller.signal.aborted) return;
        const batch = Array.isArray(response.data?.[rowsKey]) ? response.data[rowsKey] : [];
        total = Number(response.data?.count);
        rows = rows.concat(batch);
        const times = batch.map(timestampOf).filter(Number.isFinite);
        if (times.length) oldestSeen = Math.min(oldestSeen ?? Infinity, ...times);
        if (incremental && batch.some((row) => known.has(packetKey(row)))) {
          overlapped = true;
          completed = true;
          break;
        }
        if (times.length && Math.min(...times) < bounds.start) {
          completed = true;
          break;
        }
        if (batch.length < PAGE_SIZE || (Number.isFinite(total) && page * PAGE_SIZE >= total)) {
          completed = true;
          break;
        }
      }
      if (run !== generation.current || controller.signal.aborted) return;
      const incoming = normalizePackets(rows, bounds.start, bounds.end);
      const merged = incremental ? normalizePackets(incoming.concat(samplesRef.current), bounds.start, bounds.end) : incoming;
      samplesRef.current = merged;
      if (oldestSeen != null) coverageFloor.current = Math.min(coverageFloor.current ?? Infinity, oldestSeen);
      setSamples(merged);
      if (!incremental) setPartial(!completed && (coverageFloor.current == null || coverageFloor.current > bounds.start));
      else if (!completed && !overlapped) setPartial(true);
      if (coverageFloor.current != null && coverageFloor.current <= bounds.start) setPartial(false);
      setLastSampleAt(merged.length ? merged[merged.length - 1]._time : null);
      setRefreshedAt(Date.now());
      setError("");
    } catch (requestError) {
      if (run === generation.current && !controller.signal.aborted) {
        setError(requestError?.response?.data?.message || requestError.message || "Unable to fetch timeline data");
      }
    } finally {
      if (run === generation.current) {
        inFlight.current = false;
        if (activeController.current === controller) activeController.current = null;
        setLoading(false);
      }
    }
  }, [endpoint, id, rowsKey, selection]);

  loadRef.current = load;

  useEffect(() => {
    generation.current += 1;
    const run = generation.current;
    activeController.current?.abort();
    inFlight.current = false;
    samplesRef.current = [];
    coverageFloor.current = null;
    setSamples([]);
    setLoading(true);
    setError("");
    setPartial(false);
    setLastSampleAt(null);
    setRefreshedAt(null);
    loadRef.current?.(false, run);
    return () => {
      if (generation.current === run) generation.current += 1;
      activeController.current?.abort();
    };
  }, [id, key]);

  useEffect(() => {
    if (paused || selection.kind === "custom" || !id) return undefined;
    let timer;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      if (!inFlight.current) await loadRef.current?.(true, generation.current);
      if (!cancelled) timer = setTimeout(tick, POLL_MS);
    };
    timer = setTimeout(tick, POLL_MS);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, key, paused, selection.kind]);

  const choosePreset = (preset) => { setSelection({ kind: "preset", preset }); setPaused(false); };
  const applyCustom = (start, end) => {
    setSelection({ kind: "custom", start, end });
    setWindowBounds({ start, end });
    setPaused(true);
  };
  const pause = () => {
    setPaused(true);
    activeController.current?.abort();
  };
  const resumeLive = () => { setSelection({ kind: "preset", preset: "5m" }); setPaused(false); };
  const pauseForZoom = (start, end) => {
    setPaused(true);
    activeController.current?.abort();
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) setWindowBounds({ start, end });
  };

  return {
    samples, loading, error, partial, lastSampleAt, refreshedAt, paused, selection,
    windowStart: windowBounds.start, windowEnd: windowBounds.end,
    choosePreset, applyCustom, pause, resumeLive, pauseForZoom,
  };
}
