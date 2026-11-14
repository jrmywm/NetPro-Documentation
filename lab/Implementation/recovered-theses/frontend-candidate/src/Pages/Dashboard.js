import React from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "../components/Sidebar";

const Dashboard = () => {
  return (
    <div className="flex">
      <div className="fixed group hover:w-1/6 top-0 w-[5%] z-50 transition-all duration-100">
        <Sidebar />
      </div>
      <div className="static top-0 w-[5%]">
      </div>
      <div className="w-[95%] px-5">
        <Outlet />
      </div>
    </div>
  );
};

export default Dashboard;
