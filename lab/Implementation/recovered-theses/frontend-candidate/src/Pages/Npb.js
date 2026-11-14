import React, { useEffect, useState } from "react";
import Cards from "../components/Card";
import LineChart from "../components/LineChart";
import TimeRangeControls from "../components/TimeRangeControls";
import ChartLayout from "../components/ChartLayout";
import usePacketTimeline from "../hooks/usePacketTimeline";
import axios from "axios";
import { useLocation, useNavigate } from "react-router-dom";
import generateConfigFileContent from "../components/GenerateConfigFileContent";
import ProgressSpinner from "../components/ProgressSpinner";

function Npb() {
  const location = useLocation();
  const navigateTo = useNavigate();
  const searchParams = new URLSearchParams(location.search);
  const id = decodeURIComponent(searchParams.get("id"));
  const [initialLoading, setInitialLoading] = useState(true); // State for initial loading
  const [metadataError, setMetadataError] = useState("");
  const [totalsError, setTotalsError] = useState("");
  const [packetBroker, setPacketBroker] = useState({
    id: "",
    name: "",
    location: "",
  });
  const [totalPacket, setTotalPacket] = useState(null);
  const timeline = usePacketTimeline({ id, kind: "npb" });
  const token = localStorage.getItem("token");
  useEffect(() => { if (!token) navigateTo("/"); }, [navigateTo, token]);

  useEffect(() => {
    let active = true;
    let totalsBusy = false;
    let metaController;
    let totalsController;
    setInitialLoading(true);
    setPacketBroker({ id: "", name: "", location: "" });
    setTotalPacket(null);
    setMetadataError("");
    setTotalsError("");
    const loadIdentity = async () => {
      metaController = new AbortController();
      try {
        const response = await axios.get(`${process.env.REACT_APP_BASE_URL}/npb/npbid/${id}`, { signal: metaController.signal, timeout: 10000 });
        if (active) setPacketBroker({ id: response.data.id, name: response.data.name, location: response.data.location });
      } catch (error) {
        if (active && !metaController.signal.aborted) setMetadataError(error.message || "Unable to load packet broker details");
      } finally {
        if (active) setInitialLoading(false);
      }
    };
    const loadTotals = async () => {
      if (totalsBusy) return;
      totalsBusy = true;
      totalsController = new AbortController();
      try {
        const response = await axios.get(`${process.env.REACT_APP_BASE_URL}/npb/npb-packet-total/${id}`, { signal: totalsController.signal, timeout: 10000 });
        if (!active) return;
        const data = response.data.npbPackets;
        const safe = (value) => value != null && value !== "" && Number.isFinite(Number(value)) ? formatNumber(Number(value)) : "—";
        setTotalPacket({ httpCount: safe(data.http_count), httpsCount: safe(data.https_count), txHttpCount: safe(data.tx_o_http_count), txTlsCount: safe(data.tx_o_tls_count), rxCount: safe(data.rx_i_count) });
        setTotalsError("");
      } catch (error) {
        if (active && !totalsController.signal.aborted) setTotalsError(error.message || "Unable to load lifetime totals");
      } finally { totalsBusy = false; }
    };
    loadIdentity();
    loadTotals();
    const interval = setInterval(loadTotals, 5000);
    return () => { active = false; clearInterval(interval); metaController?.abort(); totalsController?.abort(); };
  }, [id]);

  // Function to format numbers
  const formatNumber = (num) => {
    if (num >= 1e18) {
      return (num / 1e18).toFixed(2).replace(/\.0$/, "") + " Qi";
    }
    if (num >= 1e15) {
      return (num / 1e15).toFixed(2).replace(/\.0$/, "") + " Qa";
    }
    if (num >= 1e12) {
      return (num / 1e12).toFixed(2).replace(/\.0$/, "") + " T";
    }
    if (num >= 1e9) {
      return (num / 1e9).toFixed(2).replace(/\.0$/, "") + " B";
    }
    if (num >= 1e6) {
      return (num / 1e6).toFixed(2).replace(/\.0$/, "") + " M";
    }
    if (num >= 1e3) {
      return (num / 1e3).toFixed(2).replace(/\.0$/, "") + " K";
    }
    return num;
  };

  const handleDownloadConfig = () => {
    axios
      .get(`${process.env.REACT_APP_BASE_URL}/config/${id}`)
      .then((response) => {
        const { npbId, psId, hostname, timerPeriodStats, timerPeriodSend } =
          response.data;
        const configFileContent = generateConfigFileContent(
          npbId,
          psId,
          hostname,
          timerPeriodStats,
          timerPeriodSend
        );
        const blob = new Blob([configFileContent], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", "config.cfg");
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      })
      .catch((error) => {
        console.error("Error downloading config: ", error);
      });
  };

  return (
    <div className="relative">
      {initialLoading && (
        <div className="fixed inset-0 flex items-center justify-center">
          <ProgressSpinner />
        </div>
      )}
      {!initialLoading && (
        <>
          <header>
            <div className="flex items-center space-x-1 mt-3">
              <p className="text-gray-400 font-['Helvetica'] text-lg font-normal">
                Pages
              </p>
              <p className="text-gray-600 font-['Helvetica'] text-lg font-bold">
                / Home
              </p>
            </div>
            <p className="text-gray-700 font-['Helvetica'] text-lg font-bold ">
              Status
            </p>
            <div className="flex">
              <div className="h-full text-gray-600 text-2xl font-normal font-['Helvetica'] w-5/6">
                Packet Broker
              </div>
              <div className="w-1/6 flex justify-end">
                <button
                  onClick={handleDownloadConfig}
                  className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded flex items-center font-['Helvetica'] font-bold"
                >
                  <span className="mr-2">Download Config</span>
                  <img
                    src="/download_logo.svg"
                    alt="Download Icon"
                    className="h-5"
                    style={{ fill: "white" }}
                  />
                </button>
              </div>
            </div>
            <div className="w-full h-full text-black-700 text-5xl font-bold font-['Helvetica']">
              {packetBroker.name}
            </div>
            <p className="text-gray-400 w-full h-full font-['Helvetica'] text-sm font-bold pt-1">
              ID: {packetBroker.id}
            </p>
            <div className="text-gray-700 text-base font-normal font-['Helvetica'] italic">
              Location: {packetBroker.location}
            </div>
          </header>
          <h2 className="mt-5 text-xl font-semibold">Lifetime totals</h2>
          {metadataError && <p role="alert">Packet broker details request failed: {metadataError}</p>}
          {totalsError && <p role="alert">Lifetime totals request failed: {totalsError}</p>}
          <div className="overflow-x-auto w-screen-lg ">
            <div className="flex justify-between pt-4 pb-4">
              <div className="flex space-x-5 pr-5">
                <Cards
                  hitType="HTTP Count"
                  number={totalPacket?.httpCount ?? "—"}
                  packet="Packet"
                />
                <Cards
                  hitType="HTTPS Count"
                  number={totalPacket?.httpsCount ?? "—"}
                  packet="Packet"
                />
                <Cards
                  hitType="TX HTTP Count"
                  number={totalPacket?.txHttpCount ?? "—"}
                  packet="Packet"
                />
                <Cards
                  hitType="TX TLS Count"
                  number={totalPacket?.txTlsCount ?? "—"}
                  packet="Packet"
                />
                <Cards
                  hitType="RX Count"
                  number={totalPacket?.rxCount ?? "—"}
                  packet="Packet"
                />
              </div>
            </div>
          </div>
          <h2 className="mt-6 text-xl font-semibold">Packets per sample · selected time window</h2>
          <TimeRangeControls timeline={timeline} />
          <ChartLayout storageKey="npb-chart-layout-v1" charts={[
            { id: "http", title: "HTTP Count", content: <LineChart title="HTTP Count" packetData={timeline.samples.map((row) => ({ time: row._time, value: row.http_count }))} loading={timeline.loading} windowStart={timeline.windowStart} windowEnd={timeline.windowEnd} onZoom={timeline.pauseForZoom} /> },
            { id: "https", title: "HTTPS Count", content: <LineChart title="HTTPS Count" packetData={timeline.samples.map((row) => ({ time: row._time, value: row.https_count }))} loading={timeline.loading} windowStart={timeline.windowStart} windowEnd={timeline.windowEnd} onZoom={timeline.pauseForZoom} /> },
            { id: "rx", title: "RX Count", content: <LineChart title="RX Count" packetData={timeline.samples.map((row) => ({ time: row._time, value: row.rx_i_count }))} loading={timeline.loading} windowStart={timeline.windowStart} windowEnd={timeline.windowEnd} onZoom={timeline.pauseForZoom} /> },
          ]} />
        </>
      )}
    </div>
  );
}

export default Npb;
