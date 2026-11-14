import React, { useEffect, useState } from "react";
import "./ChartLayout.css";

const DEFAULT_COLUMNS = 2;

export function defaultLayout(ids) {
  return { columns: DEFAULT_COLUMNS, visibleIds: [...ids] };
}

export function readLayout(storage, key, ids) {
  const fallback = defaultLayout(ids);
  try {
    const saved = JSON.parse(storage.getItem(key));
    if (!saved || saved.version !== 1 || ![1, 2].includes(saved.columns) || !Array.isArray(saved.visibleIds)) return fallback;
    const allowed = new Set(ids);
    return { columns: saved.columns, visibleIds: [...new Set(saved.visibleIds.filter((id) => allowed.has(id)))] };
  } catch (_error) {
    return fallback;
  }
}

function initialLayout(key, ids) {
  try { return readLayout(window.localStorage, key, ids); }
  catch (_error) { return defaultLayout(ids); }
}

export default function ChartLayout({ storageKey, charts }) {
  const ids = charts.map((chart) => chart.id);
  const [layout, setLayout] = useState(() => initialLayout(storageKey, ids));
  const [expandedId, setExpandedId] = useState(null);
  const visible = new Set(layout.visibleIds);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ version: 1, ...layout }));
    } catch (_error) {
      // Storage can be disabled or full; the current in-memory layout still works.
    }
  }, [layout, storageKey]);

  const setColumns = (columns) => setLayout((current) => ({ ...current, columns }));
  const toggleVisible = (id, checked) => {
    if (!checked) setExpandedId((current) => current === id ? null : current);
    setLayout((current) => ({
      ...current,
      visibleIds: checked ? [...current.visibleIds, id] : current.visibleIds.filter((item) => item !== id),
    }));
  };
  const reset = () => {
    setExpandedId(null);
    setLayout(defaultLayout(ids));
  };
  const expanded = charts.find((chart) => chart.id === expandedId && visible.has(chart.id));
  const gridCharts = charts.filter((chart) => visible.has(chart.id) && chart.id !== expanded?.id);

  return <section aria-label="Chart layout" className="chart-layout my-4">
    <div className="chart-layout-controls">
      <fieldset>
        <legend>Columns</legend>
        {[1, 2].map((columns) => <label key={columns}>
          <input type="radio" name={`${storageKey}-columns`} value={columns} checked={layout.columns === columns} onChange={() => setColumns(columns)} />
          {columns} column{columns === 1 ? "" : "s"}
        </label>)}
      </fieldset>
      <fieldset>
        <legend>Visible charts</legend>
        {charts.map((chart) => <label key={chart.id}>
          <input type="checkbox" checked={visible.has(chart.id)} onChange={(event) => toggleVisible(chart.id, event.target.checked)} />
          {chart.title}
        </label>)}
      </fieldset>
      <button type="button" onClick={reset}>Reset layout</button>
    </div>
    {expanded && <div className="chart-layout-expanded">
      <button type="button" aria-expanded="true" aria-label={`Collapse ${expanded.title}`} onClick={() => setExpandedId(null)}>Collapse {expanded.title}</button>
      {expanded.content}
    </div>}
    {gridCharts.length === 0 && !expanded
      ? <p role="status" className="chart-layout-empty">No charts are visible. Select a chart or reset the layout.</p>
      : <div className="chart-layout-grid" style={{ "--chart-columns": layout.columns }}>
        {gridCharts.map((chart) => <div key={chart.id} className="chart-layout-item">
          <button type="button" aria-expanded="false" aria-label={`Expand ${chart.title}`} onClick={() => setExpandedId(chart.id)}>Expand {chart.title}</button>
          {chart.content}
        </div>)}
      </div>}
  </section>;
}
