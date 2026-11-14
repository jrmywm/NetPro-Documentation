import React, { useMemo } from "react";
import Chart from "react-apexcharts";

function axisLabel(value, span) {
  const date = new Date(Number(value));
  const options = span <= 60 * 60 * 1000
    ? { hour: "2-digit", minute: "2-digit", second: "2-digit" }
    : { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" };
  return date.toLocaleString(undefined, options);
}

const LineChart = ({ title, packetData, loading, windowStart, windowEnd, onZoom }) => {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const validRows = (Array.isArray(packetData) ? packetData : []).filter((row) => row && row.time != null && row.time !== "");
  const times = validRows.map((row) => new Date(row.time).getTime()).filter(Number.isFinite);
  const start = Number.isFinite(windowStart) ? windowStart : (times.length ? Math.min(...times) : Date.now() - 300000);
  const end = Number.isFinite(windowEnd) ? windowEnd : (times.length ? Math.max(...times) : Date.now());
  const span = Math.max(1, end - start);
  const points = useMemo(() => (Array.isArray(packetData) ? packetData : [])
    .filter((row) => row && row.time != null && row.time !== "")
    .map((row) => {
      const x = new Date(row.time).getTime();
      const raw = row.value;
      const y = raw == null || raw === "" || !Number.isFinite(Number(raw)) ? null : Number(raw);
      return { x, y };
    })
    .filter((point) => Number.isFinite(point.x) && point.x >= start && point.x <= end)
    .sort((a, b) => a.x - b.x)
    .flatMap((point, index, all) => index && point.x - all[index - 1].x > 5000
      ? [{ x: (point.x + all[index - 1].x) / 2, y: null }, point] : [point]), [packetData, start, end]);
  const dataMax = Math.max(1, ...points.map((point) => Number.isFinite(point.y) ? Math.ceil(point.y) : 0));
  const yStep = Math.max(1, Math.ceil(dataMax / 4));
  const yMax = Math.ceil(dataMax / yStep) * yStep;
  const options = useMemo(() => ({
    chart: {
      type: "line",
      height: 350,
      toolbar: { tools: { download: false, selection: false, zoom: true, zoomin: false, zoomout: false, pan: false, reset: true } },
      events: { zoomed: (_chart, { xaxis }) => onZoom?.(xaxis.min, xaxis.max) },
    },
    xaxis: {
      type: "numeric",
      min: start,
      max: end,
      tickAmount: 6,
      labels: { formatter: (value) => axisLabel(value, span), rotate: 0, hideOverlappingLabels: true },
    },
    noData: { text: "No data" },
    colors: ["#FF5959"],
    yaxis: { min: 0, max: yMax, tickAmount: yMax / yStep, decimalsInFloat: 0, labels: { formatter: (value) => Math.round(value) } },
    dataLabels: { enabled: false },
    tooltip: {
      intersect: false,
      shared: false,
      x: { formatter: (value) => new Date(Number(value)).toLocaleString(undefined, {
        year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short",
      }) },
    },
    grid: { borderColor: "#f1f1f1" },
    stroke: { curve: "straight", width: 2 },
    markers: { size: 2 },
  }), [onZoom, span, end, start, yMax, yStep]);

  return (
    <section className="min-w-0 rounded bg-white p-3 shadow-sm">
      <h3>{title}</h3>
      <p className="text-xs text-gray-500">Date: {new Date(end).toLocaleDateString()} · Timezone: {timeZone}</p>
      {loading
        ? <p className="py-12 text-center">Loading plot…</p>
        : <div className="chart-container"><Chart options={options} series={[{ name: title, data: points }]} type="line" height={350} /></div>}
    </section>
  );
};

export default LineChart;
