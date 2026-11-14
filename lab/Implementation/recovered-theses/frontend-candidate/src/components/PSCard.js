import React from "react";

const HomeCard = ({ id, name, status, location }) => {
  // Set a threshold for word length before truncating
  const maxWordLength = 31;

  // Truncate long words and add "..." if necessary, considering one newline character
  const truncateString = (str, max) => {
    if (str.length > max) {
      const truncated = str.slice(0, max);
      const lastSpaceIndex = truncated.lastIndexOf(" ");
      const lastNewlineIndex = truncated.lastIndexOf("\n");
      const indexToUse = Math.max(lastSpaceIndex, lastNewlineIndex, 0);
      return truncated.slice(0, indexToUse) + "...";
    }
    return str;
  };

    const maxWordTitleLength = 15;

    const truncateTitleString = (str, max) => {
      if (str.length > max) {
        return str.slice(0, max) + "...";
      }
      return str;
    };

  return (
    <div
      style={{ borderRadius: "10px" }}
      className="shadow-lg container p-4 w-60 xl:w-72 h-40 bg-white-primary"
    >
      <div className="row">
        <h1 className="text-black text-base xl:text-lg font-['Helvetica']">
          Policy Server
        </h1>
        <h2 className="text-lg xl:text-2xl font-['Helvetica'] font-bold">
          {truncateTitleString(name, maxWordTitleLength)}
        </h2>
        <h1 className="text-gray-700 text-base font-['Helvetica']">
          {truncateString(location, maxWordLength)}
        </h1>
        <div
          style={{
            backgroundColor: status === "Active" ? "#E2FBD7" : "#FBD7D7",
            borderRadius: "3px",
          }}
          className=" w-16 mt-2 text-center text-sm font-['Helvetica'] font-normal"
        >
          {" "}
          {status}
        </div>
      </div>
    </div>
  );
};

export default HomeCard;
