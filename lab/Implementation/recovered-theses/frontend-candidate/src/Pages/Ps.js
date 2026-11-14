import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Cards from "../components/Card";
import LineChart from "../components/LineChart";
import TimeRangeControls from "../components/TimeRangeControls";
import ChartLayout from "../components/ChartLayout";
import usePacketTimeline from "../hooks/usePacketTimeline";
import axios from "axios";
import generateConfigFileContent from "../components/GenerateConfigFileContent";
import ProgressSpinner from "../components/ProgressSpinner";
import BlockedListTable from "../components/BlockedListTable";

function Ps() {
  const location = useLocation();
  const navigateTo = useNavigate();
  const id = decodeURIComponent(new URLSearchParams(location.search).get("id"));
  const [initialLoading, setInitialLoading] = useState(true);
  const [metadataError, setMetadataError] = useState("");
  const [totalsError, setTotalsError] = useState("");
  const [policyServer, setPolicyServer] = useState({ id: "", name: "", location: "" });
  const [totalPacket, setTotalPacket] = useState(null);
  const timeline = usePacketTimeline({ id, kind: "ps" });
  const token = localStorage.getItem("token");
  useEffect(() => { if (!token) navigateTo("/"); }, [navigateTo, token]);

  useEffect(() => {
    let active = true;
    let busy = false;
    let metaController;
    let totalController;
    setInitialLoading(true);
    setPolicyServer({ id: "", name: "", location: "" });
    setTotalPacket(null);
    setMetadataError("");
    setTotalsError("");
    const loadIdentity = async () => {
      metaController = new AbortController();
      try {
        const response = await axios.get(`${process.env.REACT_APP_BASE_URL}/ps/psid/${id}`, { signal: metaController.signal, timeout: 10000 });
        if (active) setPolicyServer({ id: response.data.id, name: response.data.name, location: response.data.location });
      } catch (error) {
        if (active && !metaController.signal.aborted) setMetadataError(error.message || "Unable to load policy server details");
      } finally { if (active) setInitialLoading(false); }
    };
    const loadTotals = async () => {
      if (busy) return;
      busy = true;
      totalController = new AbortController();
      try {
        const response = await axios.get(`${process.env.REACT_APP_BASE_URL}/ps/ps-packet-total/${id}`, { signal: totalController.signal, timeout: 10000 });
        if (!active) return;
        const data = response.data.psPackets;
        const safe = (value) => value != null && value !== "" && Number.isFinite(Number(value)) ? formatNumber(Number(value)) : "—";
        setTotalPacket({ rstClient: safe(data.rstClient), rstServer: safe(data.rstServer), rxHTTPCount: safe(data.rx_i_http_count), rxTLSCount: safe(data.rx_i_tls_count) });
        setTotalsError("");
      } catch (error) {
        if (active && !totalController.signal.aborted) setTotalsError(error.message || "Unable to load lifetime totals");
      } finally { busy = false; }
    };
    loadIdentity(); loadTotals();
    const interval = setInterval(loadTotals, 5000);
    return () => { active = false; clearInterval(interval); metaController?.abort(); totalController?.abort(); };
  }, [id]);

  const formatNumber = (num) => {
    if (num >= 1e18) return (num / 1e18).toFixed(2).replace(/\.0$/, "") + " Qi";
    if (num >= 1e15) return (num / 1e15).toFixed(2).replace(/\.0$/, "") + " Qa";
    if (num >= 1e12) return (num / 1e12).toFixed(2).replace(/\.0$/, "") + " T";
    if (num >= 1e9) return (num / 1e9).toFixed(2).replace(/\.0$/, "") + " B";
    if (num >= 1e6) return (num / 1e6).toFixed(2).replace(/\.0$/, "") + " M";
    if (num >= 1e3) return (num / 1e3).toFixed(2).replace(/\.0$/, "") + " K";
    return num;
  };

  const handleDownloadConfig = async () => {
    try {
      const response = await axios.get(`${process.env.REACT_APP_BASE_URL}/config/${id}`);
      const { npbId, psId, hostname, timerPeriodStats, timerPeriodSend } = response.data;
      const content = generateConfigFileContent(npbId, psId, hostname, timerPeriodStats, timerPeriodSend);
      const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
      const link = document.createElement("a"); link.href = url; link.download = "config.cfg";
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    } catch (error) { console.error("Error downloading config: ", error); }
  };

  const cards = [["HTTP Count", "rxHTTPCount"], ["TLS Count", "rxTLSCount"], ["Reset Client TLS", "rstClient"], ["Reset Server TLS", "rstServer"]];
  const charts = [
    { id: "rst-client", title: "TCP Reset Client", field: "rstClient" },
    { id: "rst-server", title: "TCP Reset Server", field: "rstServer" },
    { id: "rx-http", title: "RX HTTP Count", field: "rx_i_http_count" },
    { id: "rx-tls", title: "RX TLS Count", field: "rx_i_tls_count" },
  ];
  return <div className="relative">
    {initialLoading && <div className="fixed inset-0 flex items-center justify-center"><ProgressSpinner /></div>}
    {!initialLoading && <>
      <header>
        <div className="flex items-center space-x-1 mt-3"><p className="text-gray-400 text-lg">Pages</p><p className="text-gray-600 text-lg font-bold">/ Home</p></div>
        <p className="text-gray-700 text-lg font-bold">Status</p>
        <div className="flex"><div className="w-5/6 text-gray-600 text-2xl">Policy Server</div><div className="w-1/6 flex justify-end"><button onClick={handleDownloadConfig} className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded font-bold">Download Config</button></div></div>
        <div className="text-black-700 text-5xl font-bold">{policyServer.name}</div>
        <p className="text-gray-400 text-sm font-bold pt-1">ID: {policyServer.id}</p>
        <div className="text-gray-700 italic">Location: {policyServer.location}</div>
      </header>
      <h2 className="mt-5 text-xl font-semibold">Lifetime totals</h2>
      {metadataError && <p role="alert">Policy server details request failed: {metadataError}</p>}
      {totalsError && <p role="alert">Lifetime totals request failed: {totalsError}</p>}
      <div className="flex flex-wrap gap-5 py-4">{cards.map(([label, key]) => <Cards key={key} hitType={label} number={totalPacket?.[key] ?? "—"} packet="Packet" />)}</div>
      <h2 className="mt-6 text-xl font-semibold">Packets per sample · selected time window</h2>
      <TimeRangeControls timeline={timeline} />
      <ChartLayout storageKey="ps-chart-layout-v1" charts={charts.map(({ id: chartId, title, field }) => ({ id: chartId, title, content: <LineChart title={title} packetData={timeline.samples.map((row) => ({ time: row._time, value: row[field] }))} loading={timeline.loading} windowStart={timeline.windowStart} windowEnd={timeline.windowEnd} onZoom={timeline.pauseForZoom} /> }))} />
      <div className="w-full pt-10 pr-10 shadow-sm"><BlockedListTable id={id} /></div>
    </>}
  </div>;
}

export default Ps;
