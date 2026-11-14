import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import NPBCard from "../components/NPBCard";
import PolicyServerCard from "../components/PSCard";
import AddNewDevice from "../components/AddNewDevice";
import ProgressSpinner from "../components/ProgressSpinner"; // Import ProgressSpinner component
import { Dropdown } from "primereact/dropdown";

let cachedNpbCards = null;
let cachedPolicyServerCards = null;

const Home = () => {
  const navigateTo = useNavigate();
  const location = useLocation();
  const [npbCards, setNpbCards] = useState([]);
  const [policyServerCards, setPolicyServerCards] = useState([]);
  const [isAddNewDeviceOpen, setIsAddNewDeviceOpen] = useState(false);
  const [sortNpb, setSortNpb] = useState(null);
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
      setNpbCards(state.npbCards);
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
  }, [sortNpb, sortPs]);

  const fetchData = () => {
    if (cachedNpbCards && cachedPolicyServerCards) {
      setNpbCards(cachedNpbCards);
      setPolicyServerCards(cachedPolicyServerCards);
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
        })
        .catch((error) => {
          console.error("Error fetching NPB data: ", error);
        });

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

  const handleNpbCardClick = (id) => {
    console.log("id", id);
    navigateTo(`npb?id=${encodeURIComponent(id)}`, {
      state: { npbCards, policyServerCards },
    });
  };

  const handlePolicyServerCardClick = (id) => {
    navigateTo(`ps?id=${encodeURIComponent(id)}`, {
      state: { npbCards, policyServerCards },
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
          <a
            onClick={() => navigateTo("npbView")}
            className="pl-4 h-full text-red-primary hover:text-red-600 font-['Helvetica'] font-light text-base flex items-center"
          >
            View All
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 20"
              fill="#FF5959"
              className="ml-2 hover-fill-red-600"
            >
              <path d="M23.7075 10.7076L14.7075 19.7076C14.5199 19.8952 14.2654 20.0006 14 20.0006C13.7346 20.0006 13.4801 19.8952 13.2925 19.7076C13.1049 19.5199 12.9994 19.2654 12.9994 19.0001C12.9994 18.7347 13.1049 18.4802 13.2925 18.2926L20.5863 11.0001H1C0.734784 11.0001 0.48043 10.8947 0.292893 10.7072C0.105357 10.5196 0 10.2653 0 10.0001C0 9.73485 0.105357 9.4805 0.292893 9.29296C0.48043 9.10542 0.734784 9.00007 1 9.00007H20.5863L13.2925 1.70757C13.1049 1.51993 12.9994 1.26543 12.9994 1.00007C12.9994 0.734704 13.1049 0.480208 13.2925 0.292568C13.4801 0.104927 13.7346 -0.000488281 14 -0.000488281C14.2654 -0.000488281 14.5199 0.104927 14.7075 0.292568L23.7075 9.29257C23.8005 9.38544 23.8742 9.49573 23.9246 9.61713C23.9749 9.73853 24.0008 9.86865 24.0008 10.0001C24.0008 10.1315 23.9749 10.2616 23.9246 10.383C23.8742 10.5044 23.8005 10.6147 23.7075 10.7076Z" />
            </svg>
          </a>
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
        {npbCards.slice(0, 8).map((card) => (
          <div
            key={card.id}
            className="card-container hover:cursor-pointer"
            onClick={() => handleNpbCardClick(card.id)}
          >
            <NPBCard {...card} />
          </div>
        ))}
      </div>
      {/* Policy Server section */}
      <div className="w-full h-full text-gray-700 text-2xl font-bold font-['Helvetica'] pt-3 flex items-center">
        <div className="flex w-3/4 items-center">
          Policy Server
          <a
            onClick={() => navigateTo("psView")}
            className="pl-4 h-full text-red-primary hover:text-red-600 font-['Helvetica'] font-light text-base flex items-center"
          >
            View All
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 20"
              fill="#FF5959"
              className="ml-2 hover-fill-red-600"
            >
              <path d="M23.7075 10.7076L14.7075 19.7076C14.5199 19.8952 14.2654 20.0006 14 20.0006C13.7346 20.0006 13.4801 19.8952 13.2925 19.7076C13.1049 19.5199 12.9994 19.2654 12.9994 19.0001C12.9994 18.7347 13.1049 18.4802 13.2925 18.2926L20.5863 11.0001H1C0.734784 11.0001 0.48043 10.8947 0.292893 10.7072C0.105357 10.5196 0 10.2653 0 10.0001C0 9.73485 0.105357 9.4805 0.292893 9.29296C0.48043 9.10542 0.734784 9.00007 1 9.00007H20.5863L13.2925 1.70757C13.1049 1.51993 12.9994 1.26543 12.9994 1.00007C12.9994 0.734704 13.1049 0.480208 13.2925 0.292568C13.4801 0.104927 13.7346 -0.000488281 14 -0.000488281C14.2654 -0.000488281 14.5199 0.104927 14.7075 0.292568L23.7075 9.29257C23.8005 9.38544 23.8742 9.49573 23.9246 9.61713C23.9749 9.73853 24.0008 9.86865 24.0008 10.0001C24.0008 10.1315 23.9749 10.2616 23.9246 10.383C23.8742 10.5044 23.8005 10.6147 23.7075 10.7076Z" />
            </svg>
          </a>
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
        {policyServerCards.slice(0, 8).map((card) => (
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

export default Home;
