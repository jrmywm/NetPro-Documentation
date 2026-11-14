import Home from "./Pages/Home";
import Npb from "./Pages/Npb";
import Ps from "./Pages/Ps";

import { createBrowserRouter, RouterProvider } from "react-router-dom";
import Dashboard from "./Pages/Dashboard";
import SignIn from "./Pages/SignIn";
import Register from "./Pages/Register";
import NpbList from "./Pages/NpbList";
import PsList from "./Pages/PsList";
import CsvImports from "./Pages/CsvImports";

const router = createBrowserRouter([
  {
    path: "/",
    element: <SignIn />,
  },
  {
    path: "register",
    element: <Register />,
  },
  {
    path: "dashboard",
    element: <Dashboard />,
    children: [
      { path: "imports", element: <CsvImports /> },
      {
        index: true,
        element: <Home />,
      },
      {
        path: "npb",
        element: <Npb />,
      },
      {
        path: "ps",
        element: <Ps />,
      },
      {
        path: "npbView",
        element: <NpbList />,
      },
      {
        path: "psView",
        element: <PsList />,
      },
    ],
  },
]);

const App = () => {
  return <RouterProvider router={router} />;
};

export default App;
