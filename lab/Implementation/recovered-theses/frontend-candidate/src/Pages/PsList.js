import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import PolicyServerCard from "../components/PSCard";
import AddNewDevice from "../components/AddNewDevice";
import ProgressSpinner from "../components/ProgressSpinner"; // Import ProgressSpinner component
import { Dropdown } from "primereact/dropdown";

let cachedNpbCards = null;
let cachedPolicyServerCards = null;

const PsList = () => {
  const navigateTo = useNavigate();
  const location = useLocation();
  const [policyServerCards, setPolicyServerCards] = useState([]);
  const [isAddNewDeviceOpen, setIsAddNewDeviceOpen] = useState(false);
  const [sortPs, setSortPs] = useState(null);
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
      setPolicyServerCards(state.policyServerCards);
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
  }, [ sortPs]);

  const fetchData = () => {
    if (cachedNpbCards && cachedPolicyServerCards) {
      setPolicyServerCards(cachedPolicyServerCards);
      setLoading(false);
    } else {
     

      axios
        .get(`${process.env.REACT_APP_BASE_URL}/ps/pss`, {
          params: {
            sortParam: sortPs ? sortPs : "name",
          },
        })
        .then((response) => {
          const data = response.data;
          setPolicyServerCards(data);
          cachedPolicyServerCards = data;
        })
        .catch((error) => {
          console.error("Error fetching Policy Server data: ", error);
        })
        .finally(() => {
          setLoading(false); // Set loading to false after data fetch completes
        });
    }
  };

  const updateData = () => {
    

    axios
      .get(`${process.env.REACT_APP_BASE_URL}/ps/pss`, {
        params: {
          sortParam: sortPs ? sortPs : "name",
        },
      })
      .then((response) => {
        const data = response.data;
        setPolicyServerCards(data);
      })
      .catch((error) => {
        console.error("Error fetching Policy Server data: ", error);
      });
  };

  const openPopup = () => {
    setIsAddNewDeviceOpen(true);
  };

  const closePopup = () => {
    setIsAddNewDeviceOpen(false);
  };

  

  const handlePolicyServerCardClick = (id) => {
    navigateTo(`/dashboard/ps?id=${encodeURIComponent(id)}`, {
      state: { policyServerCards },
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

     
      {/* Policy Server section */}
      <div className="w-full h-full text-gray-700 text-2xl font-bold font-['Helvetica'] pt-3 flex items-center">
        <div className="flex w-3/4 items-center">
          Policy Server
         
        </div>
        <div className="card flex w-1/4 justify-end">
          <Dropdown
            value={sortPs}
            onChange={(e) => setSortPs(e.value)}
            options={items}
            optionLabel="name"
            placeholder="Select a sort"
            className="w-full md:w-14rem"
          />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 justify-start w-full gap-4 gap-y-4 pt-4">
        {policyServerCards.map((card) => (
          <div
            key={card.id}
            className="card-container hover:cursor-pointer "
            onClick={() => handlePolicyServerCardClick(card.id)}
          >
            <PolicyServerCard {...card} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default PsList;
