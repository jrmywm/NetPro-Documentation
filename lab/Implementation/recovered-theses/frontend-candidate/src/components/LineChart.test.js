import React from "react";
import { render, screen } from "@testing-library/react";
import LineChart from "./LineChart";

let mockChartProps;
jest.mock("react-apexcharts", () => (props) => {
  mockChartProps = props;
  return <div data-testid="chart" />;
});
jest.mock("./SkeletonLineChart", () => () => <div>Loading</div>);

const chartProps = () => {
  screen.getByTestId("chart");
  return mockChartProps;
};

test("sorts API timestamps, displays local time labels, and preserves zero counts", () => {
  const time = "2026-09-26T06:24:00.000Z";
  render(<LineChart title="HTTP" loading={false} packetData={[
    { time: "2026-09-26T06:24:01.000Z", value: 17 },
    { time, value: 0 },
  ]} windowStart={new Date("2026-09-26T06:23:00.000Z").getTime()} windowEnd={new Date("2026-09-26T06:25:00.000Z").getTime()} />);
  const props = chartProps();
  expect(props.options.xaxis).toMatchObject({ type: "numeric", tickAmount: 6 });
  expect(props.options.xaxis.labels.rotate).toBe(0);
  expect(props.options.xaxis.labels.formatter(new Date(time).getTime())).toContain(":");
  expect(props.options.tooltip.x.formatter(new Date(time).getTime())).toContain("2026");
  expect(screen.getByText((content) => content.startsWith("Date: ") && content.includes(" · Timezone: "))).toBeTruthy();
  expect(props.series[0].data).toEqual([
    { x: new Date(time).getTime(), y: 0 },
    { x: new Date("2026-09-26T06:24:01.000Z").getTime(), y: 17 },
  ]);
});

test("uses integer-spaced y-axis ticks", () => {
  render(<LineChart title="HTTP" loading={false} packetData={[
    { time: "2026-09-26T06:24:00.000Z", value: 6 },
  ]} windowStart={new Date("2026-09-26T06:23:00.000Z").getTime()} windowEnd={new Date("2026-09-26T06:25:00.000Z").getTime()} />);
  const { yaxis } = chartProps().options;
  const tickStep = yaxis.max / yaxis.tickAmount;
  expect(Number.isInteger(tickStep)).toBe(true);
  expect(yaxis.tickAmount).toBeGreaterThanOrEqual(1);
  expect(yaxis.tickAmount).toBeLessThanOrEqual(4);
});

test("invalid timestamps cannot produce labels or shift counts", () => {
  render(<LineChart title="TLS" loading={false} packetData={[
    { time: "not-a-date", value: 99 },
    { time: null, value: 88 },
    { time: "", value: 77 },
    null,
    { time: "2026-09-26T06:24:00.000Z", value: 5 },
  ]} windowStart={new Date("2026-09-26T06:23:00.000Z").getTime()} windowEnd={new Date("2026-09-26T06:25:00.000Z").getTime()} />);
  const props = chartProps();
  expect(props.series[0].data).toEqual([
    { x: new Date("2026-09-26T06:24:00.000Z").getTime(), y: 5 },
  ]);
});

test("empty or missing responses clear the previous chart", () => {
  const { rerender } = render(<LineChart title="HTTP" loading={false}
    packetData={[{ time: "2026-09-26T06:24:00.000Z", value: 12 }]} windowStart={new Date("2026-09-26T06:23:00Z").getTime()} windowEnd={new Date("2026-09-26T06:25:00Z").getTime()} />);
  for (const packetData of [[], null, undefined]) {
    rerender(<LineChart title="HTTP" loading={false} packetData={packetData} windowStart={new Date("2026-09-26T06:23:00Z").getTime()} windowEnd={new Date("2026-09-26T06:25:00Z").getTime()} />);
    const props = chartProps();
    expect(props.series[0].data).toEqual([]);
    expect(props.options.noData.text).toBe("No data");
  }
});
