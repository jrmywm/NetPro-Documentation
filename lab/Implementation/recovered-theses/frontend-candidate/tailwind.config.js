/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "white-primary": "#F8F9FA",
        "red-primary": "#FF5959",
        "red-secondary": "#FBD7D7",
        "blue-primary": "#2D3748",
        "blue-secondary": "#CDDEFF",
        "green-secondary": "#E2FBD7",
        "green-primary": "#34B53A",
      },
      fontFamily: {
        helvetica: ["Helvetica", "sans"],
        "dm-sans": ["DM Sans", "sans"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
