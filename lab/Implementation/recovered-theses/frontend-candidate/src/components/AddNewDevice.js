import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import generateConfigFileContent from "./GenerateConfigFileContent"; // Import the function
import { Toast } from "primereact/toast";

const AddNewDevice = ({ isOpen, onClose, onDeviceAdded }) => {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  // const [ipAdd, setIpAdd] = useState("");
  const [periodStats, setPeriodStats] = useState("");
  const [periodSend, setPeriodSend] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const toast = useRef(null);

  const handleNextPage = () => {
    setCurrentPage(2);
  };

  const handlePrevPage = () => {
    setCurrentPage(1);
  };

  useEffect(() => {
    if (isOpen) {
      setName("");
      setLocation("");
      setPeriodStats("");
      setPeriodSend("");
      setCurrentPage(1);
    }
  }, [isOpen]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      if (currentPage === 1) {
        // If it's the first page, move to the second page
        handleNextPage();
        return;
      }

      // Create NPB
      const npbResponse = await axios.post(
        `${process.env.REACT_APP_BASE_URL}/npb/createnpb`,
        { name, location }
      );
      const npbId = npbResponse.data.id; // Extract NPB ID from the response

      // Create PS
      const psResponse = await axios.post(
        `${process.env.REACT_APP_BASE_URL}/ps/createps`,
        { name, location }
      );
      const psId = psResponse.data.id; // Extract PS ID from the response

      // Generate configuration file content
      const configFileContent = generateConfigFileContent(
        npbId,
        psId, // Ensure psId is declared before using it
        process.env.REACT_APP_BASE_URL,
        periodStats,
        periodSend
      );

      // Create a Blob from the configuration content
      const blob = new Blob([configFileContent], { type: "text/plain" });

      // Create a URL for the Blob
      const url = URL.createObjectURL(blob);

      // Create a temporary link element
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "config.cfg"); // Set the filename for download
      document.body.appendChild(link);

      // Click the link to trigger the download
      link.click();

      // Cleanup: Remove the temporary link and revoke the URL
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      // Static configuration values
      const staticConfigValues = {
        maxPacketLen: 1500,
        rxRingSize: 1024,
        txRingSize: 1024,
        numMbufs: 8191,
        mbufCacheSize: 250,
        burstSize: 32,
        maxTcpPayloadLen: 1024,
        statFile: "stats/stats",
        statFileExt: ".csv",
      };

      // Combine static and dynamic values
      const configData = {
        npbId: npbId,
        psId: psId,
        hostname: process.env.REACT_APP_BASE_URL,
        ...staticConfigValues,
        timerPeriodStats: periodStats,
        timerPeriodSend: periodSend,
      };

      // Post the combined config data
      await axios.post(
        `${process.env.REACT_APP_BASE_URL}/config/create`,
        configData
      );

      // Reload data after adding a new device
      onDeviceAdded();

      // Close the popup after successful submission
      onClose(); // <-- Close the popup here

      toast.current.show({
        severity: "success",
        summary: "Success",
        detail: "Device added successfully.",
      });
    } catch (error) {
      console.error("Error adding new device: ", error);
      toast.current.show({
        severity: "error",
        summary: "Error",
        detail: "Error adding new device.",
      });
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 flex justify-center items-center bg-black bg-opacity-50 z-50">
      <Toast ref={toast} />
      <div className="bg-white p-8 rounded-lg w-screen max-w-screen-sm">
        {currentPage === 1 && (
          <>
            <h2 className="text-2xl font-bold mb-4">Add New Device</h2>
            <form onSubmit={handleSubmit}>
              {/* Form fields with adjusted width and height */}
              <div className="mb-4">
                <label
                  htmlFor="name"
                  className="block font-normal mb-1 font-['Helvetica']"
                >
                  Name:
                </label>
                <input
                  type="text"
                  id="name"
                  className="border p-2 w-full rounded-md font-['Helvetica']"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. University Campus"
                  maxLength={30} // Limit input to 30 characters
                />
              </div>
              <div className="mb-4">
                <label
                  htmlFor="location"
                  className="block font-normal mb-1 font-['Helvetica']"
                >
                  Location:
                </label>
                <input
                  type="text"
                  id="location"
                  className="border p-2 w-full rounded-md font-['Helvetica']"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="e.g. Building A, Floor 1, Room 101"
                  maxLength={60} // Limit input to 30 characters
                />
              </div>
              <div className="mb-4">
                <label
                  htmlFor="periodStats"
                  className="block font-normal mb- font-['Helvetica']"
                >
                  Period Stats (1-60):
                </label>
                <input
                  type="number"
                  id="periodStats"
                  className="border p-2 w-full rounded-md font-['Helvetica']" // Adjusted height
                  value={periodStats}
                  onChange={(e) => {
                    const value =
                      e.target.value === ""
                        ? ""
                        : Math.min(Math.max(e.target.value, 1), 60);
                    setPeriodStats(value);
                  }}
                  placeholder="Seconds in which data will be recorded (e.g data/2 seconds)"
                  min="1"
                  max="60"
                />
              </div>
              <div className="mb-4">
                <label
                  htmlFor="periodSend"
                  className="block font-normal mb-1 font-['Helvetica']"
                >
                  Period Send (1-60):
                </label>
                <input
                  type="number"
                  id="periodSend"
                  className="border p-2 w-full rounded-md font-['Helvetica']" // Adjusted height
                  value={periodSend}
                  onChange={(e) => {
                    const value =
                      e.target.value === ""
                        ? ""
                        : Math.min(Math.max(e.target.value, 1), 60);
                    setPeriodSend(value);
                  }}
                  placeholder="Minute in which data will be sent (e.g every 2 minutes)"
                  min="1"
                  max="60"
                />
              </div>
              <div className="flex justify-between">
                <button
                  type="button"
                  className="text-gray-600 hover:text-gray-800"
                  onClick={onClose}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="bg-red-primary hover:bg-red-500 text-white px-4 py-2 rounded-md ml-2" // Rounded button
                  onClick={handleNextPage}
                >
                  Next
                </button>
              </div>
            </form>
          </>
        )}
        {currentPage === 2 && (
          <>
            <h2 className="text-2xl font-bold mb-4">Confirm and Download</h2>
            <p>Are you sure you want to add this device?</p>
            <div className="flex justify-between mt-4">
              <button
                type="button"
                className="text-gray-600 hover:text-gray-800"
                onClick={handlePrevPage}
              >
                Back
              </button>
              <button
                type="submit"
                className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-md ml-2" // Rounded button
                onClick={handleSubmit}
              >
                Confirm & Download
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default AddNewDevice;
