import React from "react";

const Cards = ({ hitType, number, packet }) => {
  return (
    <div
      style={{ borderRadius: "10px" }}
      className="shadow-lg container p-4 w-56 h-32 bg-white-primary"
    >
      <div className="row">
        <h1 className="text-black text-lg font-['Helvetica']">{hitType}</h1>
        <h2 className="text-2xl font-['Helvetica'] font-bold text-red-primary">
          {number}
        </h2>
        <h1 className="text-gray-700 text-base font-['Helvetica']">{packet}</h1>
      </div>
    </div>
  );
};

export default Cards;
