import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import TimeRangeControls from "./TimeRangeControls";

jest.mock("axios", () => ({ get: jest.fn() }));

test("shows the active window, sample age, and pause/live controls", () => {
  const timeline = {
    selection: { kind: "preset", preset: "5m" }, paused: false,
    choosePreset: jest.fn(), applyCustom: jest.fn(), pause: jest.fn(), resumeLive: jest.fn(),
    lastSampleAt: Date.now() - 6000, refreshedAt: Date.now(), loading: false, error: "", partial: false, samples: [{}],
  };
  render(<TimeRangeControls timeline={timeline} />);
  expect(screen.getByRole("button", { name: "Last 5 minutes" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText(/Last sample: 6s ago/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Pause" }));
  expect(timeline.pause).toHaveBeenCalled();
});

test("validates custom range and applies a valid local range", () => {
  const timeline = {
    selection: { kind: "preset", preset: "5m" }, paused: false,
    choosePreset: jest.fn(), applyCustom: jest.fn(), pause: jest.fn(), resumeLive: jest.fn(),
    lastSampleAt: null, refreshedAt: null, loading: false, error: "", partial: false, samples: [],
  };
  render(<TimeRangeControls timeline={timeline} />);
  fireEvent.change(screen.getByLabelText("Custom start"), { target: { value: "2026-09-01T10:00" } });
  fireEvent.change(screen.getByLabelText("Custom end"), { target: { value: "2026-09-01T09:00" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply custom range" }));
  expect(screen.getByRole("alert").textContent).toContain("start before the end");
  fireEvent.change(screen.getByLabelText("Custom end"), { target: { value: "2026-09-01T10:30" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply custom range" }));
  expect(timeline.applyCustom).toHaveBeenCalledWith(expect.any(Number), expect.any(Number));
});
