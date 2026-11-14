import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import NPBCard from "../components/NPBCard";
import AddNewDevice from "../components/AddNewDevice";
import ProgressSpinner from "../components/ProgressSpinner"; // Import ProgressSpinner component
import { Dropdown } from "primereact/dropdown";

let cachedNpbCards = null;

const NpbList = () => {
  const navigateTo = useNavigate();
  const location = useLocation();
  const [npbCards, setNpbCards] = useState([]);
  const [isAddNewDeviceOpen, setIsAddNewDeviceOpen] = useState(false);
  const [sortNpb, setSortNpb] = useState(null);
  const [loading, setLoading] = useState(true); // Loading state for initial data fetch
  const token = localStorage.getItem("token");
  if (!token) {
    navigateTo("/");
  }
  const items = [
    { name: "Name", value: "name" },
    { name: "Status", value: "status" },
    { name: "Creation Data", value: "createdAt" },
    // Add more items as needed
  ];

  useEffect(() => {
    // Restore state when coming back from another page
    const state = location.state;
    if (state) {
      setNpbCards(state.npbCards);
      setLoading(false); // Set loading to false after restoring state
    } else {
      fetchData(); // Fetch data only if no state found (initial page load)
    }
  }, [location.state]);

  useEffect(() => {
    const intervalId = setInterval(updateData, 10000); // Fetch data every 10 seconds
    return () => clearInterval(intervalId); // Cleanup interval on unmount
  }, []); // Empty dependency array ensures useEffect runs only once on component mount

  useEffect(() => {
    updateData();
  }, [sortNpb]);

  const fetchData = () => {
    if (cachedNpbCards) {
      setNpbCards(cachedNpbCards);

      setLoading(false);
    } else {
      axios
        .get(`${process.env.REACT_APP_BASE_URL}/npb/npbs`, {
          params: {
            sortParam: sortNpb ? sortNpb : "name",
          },
        })
        .then((response) => {
          const data = response.data;
          setNpbCards(data);
          cachedNpbCards = data;
          setLoading(false);
        })
        .catch((error) => {
          console.error("Error fetching NPB data: ", error);
        });
    }
  };

  const updateData = () => {
    axios
      .get(`${process.env.REACT_APP_BASE_URL}/npb/npbs`, {
        params: {
          sortParam: sortNpb ? sortNpb : "name",
        },
      })
      .then((response) => {
        const data = response.data;
        setNpbCards(data);
        cachedNpbCards = data;
      })
      .catch((error) => {
        console.error("Error fetching NPB data: ", error);
      });
  };

  const openPopup = () => {
    setIsAddNewDeviceOpen(true);
  };

  const closePopup = () => {
    setIsAddNewDeviceOpen(false);
  };

  const handleNpbCardClick = (id) => {
    console.log("id", id);
    navigateTo(`/dashboard/npb?id=${encodeURIComponent(id)}`, {
      state: { npbCards },
    });
  };

  const handleDeviceAdded = () => {
    updateData();
  };

  return (
    <div className="relative">
      {/* Loading spinner only for initial data fetch */}
      {loading && (
        <div className="fixed inset-0 flex items-center justify-center">
          <ProgressSpinner />
        </div>
      )}

      <header>
        <div className="flex items-center space-x-1 mt-3">
          <p className="text-gray-400 font-['Helvetica'] text-lg font-normal">
            Pages
          </p>
          <p className="text-gray-600 font-['Helvetica'] text-lg font-bold">
            / Home
          </p>
        </div>
      </header>
      <p className="text-gray-700 font-['Helvetica'] text-lg font-bold pb-3">
        Dashboard
      </p>
      <button
        onClick={openPopup}
        className=" hover:bg-red-500 bg-red-primary rounded-lg shadow-lg text-white font-bold py-2 px-4"
      >
        Add new Devices +
      </button>

      <AddNewDevice
        isOpen={isAddNewDeviceOpen}
        onClose={closePopup}
        onDeviceAdded={handleDeviceAdded}
      />

      {/* Packet Broker section */}
      <div className="w-full h-full text-gray-700 text-2xl font-bold font-['Helvetica'] pt-3 flex items-center">
        <div className="flex w-3/4 items-center">
          <h1>Packet Broker</h1>
        </div>
        <div className="card flex w-1/4 justify-end">
          <Dropdown
            value={sortNpb}
            onChange={(e) => setSortNpb(e.value)}
            options={items}
            optionLabel="name"
            placeholder="Select a sort"
            className="w-full md:w-14rem"
          />
        </div>
      </div>
      <div className="ml-auto"></div>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 justify-start w-full gap-4 gap-y-4 pt-4">
        {npbCards.map((card) => (
          <div
            key={card.id}
            className="card-container hover:cursor-pointer"
            onClick={() => handleNpbCardClick(card.id)}
          >
            <NPBCard {...card} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default NpbList;
