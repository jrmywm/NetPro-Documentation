import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import ChartLayout, { defaultLayout, readLayout } from "./ChartLayout";

const charts = [
  { id: "http", title: "HTTP", content: <div>HTTP chart body</div> },
  { id: "tls", title: "TLS", content: <div>TLS chart body</div> },
];

beforeEach(() => window.localStorage.clear());

test("defaults to two columns and persists one-column and visibility choices", () => {
  const { unmount } = render(<ChartLayout storageKey="layout-test" charts={charts} />);
  fireEvent.click(screen.getByLabelText("1 column"));
  fireEvent.click(screen.getByLabelText("HTTP"));
  expect(screen.queryByText("HTTP chart body")).toBeNull();
  expect(JSON.parse(window.localStorage.getItem("layout-test"))).toEqual({ version: 1, columns: 1, visibleIds: ["tls"] });
  unmount();
  render(<ChartLayout storageKey="layout-test" charts={charts} />);
  expect(screen.getByLabelText("1 column").checked).toBe(true);
  expect(screen.getByLabelText("HTTP").checked).toBe(false);
});

test("expands inline, collapses, shows empty state, and resets defaults", () => {
  render(<ChartLayout storageKey="layout-expand" charts={charts} />);
  fireEvent.click(screen.getByRole("button", { name: "Expand HTTP" }));
  expect(screen.getByText("HTTP chart body")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Collapse HTTP" }));
  fireEvent.click(screen.getByLabelText("HTTP"));
  fireEvent.click(screen.getByLabelText("TLS"));
  expect(screen.getByRole("status").textContent).toContain("No charts are visible");
  fireEvent.click(screen.getByRole("button", { name: "Reset layout" }));
  expect(screen.getByLabelText("HTTP").checked).toBe(true);
  expect(screen.getByLabelText("TLS").checked).toBe(true);
  expect(screen.getByLabelText("2 columns").checked).toBe(true);
});

test("uses defaults for malformed, version-mismatched, or inaccessible storage", () => {
  const storage = { getItem: jest.fn(() => "not-json") };
  expect(readLayout(storage, "bad", ["http", "tls"])).toEqual(defaultLayout(["http", "tls"]));
  expect(readLayout({ getItem: () => JSON.stringify({ version: 9, columns: 1, visibleIds: [] }) }, "old", ["http"])).toEqual(defaultLayout(["http"]));
  expect(readLayout({ getItem: () => { throw new Error("blocked"); } }, "blocked", ["http"])).toEqual(defaultLayout(["http"]));
  expect(readLayout({ getItem: () => JSON.stringify({ version: 1, columns: 1, visibleIds: ["http", "unknown", "http"] }) }, "filter", ["http", "tls"]))
    .toEqual({ columns: 1, visibleIds: ["http"] });
});

test("persists layout independently for each page key", () => {
  render(<>
    <ChartLayout storageKey="npb-layout" charts={charts} />
    <ChartLayout storageKey="ps-layout" charts={charts} />
  </>);
  fireEvent.click(screen.getAllByLabelText("1 column")[0]);
  expect(JSON.parse(window.localStorage.getItem("npb-layout")).columns).toBe(1);
  expect(JSON.parse(window.localStorage.getItem("ps-layout")).columns).toBe(2);
});

test("hiding an expanded chart clears its expansion", () => {
  render(<ChartLayout storageKey="layout-hide-expanded" charts={charts} />);
  fireEvent.click(screen.getByRole("button", { name: "Expand HTTP" }));
  fireEvent.click(screen.getByLabelText("HTTP"));
  expect(screen.queryByRole("button", { name: "Collapse HTTP" })).toBeNull();
  expect(screen.queryByText("HTTP chart body")).toBeNull();
});

test("remains interactive when localStorage writes fail", () => {
  const setItem = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  render(<ChartLayout storageKey="layout-blocked" charts={charts} />);
  fireEvent.click(screen.getByLabelText("1 column"));
  expect(screen.getByLabelText("1 column").checked).toBe(true);
  setItem.mockRestore();
});
