import { act, renderHook, waitFor } from "@testing-library/react";
import axios from "axios";
import usePacketTimeline, { formatAgo, normalizePackets, timestampOf, windowFor } from "./usePacketTimeline";

jest.mock("axios", () => ({ get: jest.fn() }));

beforeEach(() => jest.resetAllMocks());
afterEach(() => jest.useRealTimers());

test("normalizes only valid rows, sorts ascending, and deduplicates packet ids", () => {
  const rows = [
    { packet_id: 2, time: "2026-01-01T00:00:02Z" },
    { packet_id: 1, time: "2026-01-01T00:00:01Z" },
    { packet_id: 1, time: "2026-01-01T00:00:01Z", value: 99 },
    { packet_id: 3, time: "bad" }, null,
  ];
  const result = normalizePackets(rows, Date.parse("2026-01-01T00:00:00Z"), Date.parse("2026-01-01T00:01:00Z"));
  expect(result.map((row) => row.packet_id)).toEqual([1, 2]);
  expect(timestampOf({ time: "" })).toBeNull();
});

test("computes preset/custom bounds and sample age", () => {
  expect(windowFor({ kind: "preset", preset: "15m" }, 900000)).toEqual({ start: 0, end: 900000 });
  expect(windowFor({ kind: "custom", start: 10, end: 20 }, 100)).toEqual({ start: 10, end: 20 });
  expect(formatAgo(1000, 7000)).toBe("6s ago");
});

test("loads a bounded page and preserves current data when a live refresh fails", async () => {
  jest.useFakeTimers();
  const timestamp = Date.now() - 1000;
  axios.get.mockResolvedValueOnce({ data: { count: 1, npbPackets: [{ packet_id: 1, time: timestamp, http_count: 2 }] } });
  const { result } = renderHook(() => usePacketTimeline({ id: "device-a", kind: "npb" }));
  await waitFor(() => expect(result.current.samples).toHaveLength(1));
  expect(axios.get.mock.calls[0][0]).toContain("page=1&pageSize=1000");
  axios.get.mockRejectedValueOnce(new Error("offline"));
  await act(async () => { jest.advanceTimersByTime(5000); await Promise.resolve(); await Promise.resolve(); });
  await waitFor(() => expect(result.current.error).toBe("offline"));
  expect(result.current.samples).toHaveLength(1);
});

test("aborts and discards an older device response", async () => {
  let resolveOld;
  axios.get.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
  axios.get.mockResolvedValueOnce({ data: { count: 1, psPackets: [{ packet_id: 20, time: Date.now(), rstClient: 1 }] } });
  const { result, rerender } = renderHook(({ id }) => usePacketTimeline({ id, kind: "ps" }), { initialProps: { id: "old" } });
  rerender({ id: "new" });
  await waitFor(() => expect(result.current.samples[0]?.packet_id).toBe(20));
  await act(async () => resolveOld({ data: { count: 1, psPackets: [{ packet_id: 10, time: Date.now(), rstClient: 1 }] } }));
  expect(result.current.samples.map((row) => row.packet_id)).toEqual([20]);
});

test("keeps the capped-history warning after an overlapping live refresh", async () => {
  jest.useFakeTimers();
  const now = Date.now();
  const page = Array.from({ length: 1000 }, (_, packet_id) => ({ packet_id, time: now - 1000, http_count: 1 }));
  axios.get.mockResolvedValue({ data: { count: 50000, npbPackets: page } });
  const { result, unmount } = renderHook(() => usePacketTimeline({ id: "wide", kind: "npb" }));
  await act(async () => { for (let i = 0; i < 20; i += 1) await Promise.resolve(); });
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(20));
  expect(result.current.partial).toBe(true);
  await act(async () => { jest.advanceTimersByTime(5000); for (let i = 0; i < 4; i += 1) await Promise.resolve(); });
  expect(axios.get).toHaveBeenCalledTimes(21);
  expect(result.current.partial).toBe(true);
  unmount();
  jest.useRealTimers();
});
