import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios"; // Import Axios library
import { Toast } from "primereact/toast"; // Import Toast component

export default function Register() {
  const navigateTo = useNavigate();

  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [name, setName] = useState(""); // Add name state
  const [password, setPassword] = useState("");
  const toast = useRef(null);

  const token = localStorage.getItem("token");
  useEffect(() => {
    if (token) {
      navigateTo("/dashboard");
    }
  }, [token]);

  const validateEmail = (email) => {
    // Regular expression for email validation
    const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    return regex.test(email);
  };

  const handleEmailChange = (e) => {
    const newEmail = e.target.value;
    setEmail(newEmail);

    if (!validateEmail(newEmail)) {
      setEmailError("Invalid email format");
    } else {
      setEmailError("");
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();

    if (!email || !password || !name) {
      toast.current.show({
        severity: "error",
        summary: "Error",
        detail: "Please fill in all fields",
        life: 3000,
      });
      return;
    }

    const body = {
      email,
      password,
      name,
    };

    axios
      .post(`${process.env.REACT_APP_BASE_URL}/user/register`, body)
      .then((response) => {
        if (response.data.message === "User added successfully") {
          toast.current.show({
            severity: "success",
            summary: "Success",
            detail: response.data.message,
            life: 2000,
          });

          // Delay the navigation
          setTimeout(() => {
            navigateTo("/");
          }, 1000); // Delay should be slightly more than the life of the toast
        } else if (response.data.message === "email already in use") {
          toast.current.show({
            severity: "error",
            summary: "Error",
            detail: response.data.message,
            life: 3000,
          });
        }
      })
      .catch((error) => {
        toast.current.show({
          severity: "error",
          summary: "Error",
          detail: error.response.data.message,
          life: 3000,
        });
        console.error(error);
      });
  };
  return (
    <>
      {/*
        This example requires updating your template:

        ```
        <html class="h-full bg-white">
        <body class="h-full">
        ```
      */}
      <div
        style={{ marginTop: "20vh" }}
        className="flex min-h-full flex-1 flex-col justify-center px-6 py-12 lg:px-8"
      >
        <Toast ref={toast} />
        <div className="sm:mx-auto sm:w-full sm:max-w-sm">
          {/* <img
            className="mx-auto h-10 w-auto"
            src="https://tailwindui.com/img/logos/mark.svg?color=indigo&shade=600"
            alt="Your Company"
          /> */}
          <h2 className="mt-10 text-center text-2xl font-bold leading-9 tracking-tight text-gray-900">
            Register your account
          </h2>
        </div>

        <div className="mt-10 sm:mx-auto sm:w-full sm:max-w-sm">
          <form className="space-y-6">
            <div>
              <label
                htmlFor="email"
                className="block text-base font-medium leading-6 text-gray-900"
              >
                Email address
              </label>
              <div className="mt-2">
                <input
                  id="email"
                  name="email"
                  type="text"
                  onChange={handleEmailChange}
                  autoComplete="email"
                  required
                  className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-red-primary text-sm sm:leading-6"
                />
                {emailError && (
                  <div className="error text-red-600 text-sm">{emailError}</div>
                )}
              </div>
            </div>

            <div>
              <label
                htmlFor="name"
                className="block text-base font-medium leading-6 text-gray-900"
              >
                Name
              </label>
              <div className="mt-2">
                <input
                  id="name"
                  name="name"
                  type="text"
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="name"
                  required
                  className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-red-primary sm:text-sm sm:leading-6"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label
                  htmlFor="password"
                  className="block text-base font-medium leading-6 text-gray-900"
                >
                  Password
                </label>
                {/* <div className="text-sm">
                  <a
                    href="#"
                    className="font-semibold text-indigo-600 hover:text-indigo-500"
                  >
                    Forgot password?
                  </a>
                </div> */}
              </div>
              <div className="mt-2">
                <input
                  id="password"
                  name="password"
                  onChange={(e) => setPassword(e.target.value)}
                  type="password"
                  autoComplete="current-password"
                  required
                  className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-red-primary sm:text-sm sm:leading-6"
                />
              </div>
            </div>

            <div>
              <button
                type="submit"
                onClick={handleSubmit}
                className="flex w-full justify-center rounded-md bg-red-primary px-3 py-1.5 text-sm font-semibold leading-6 text-white shadow-sm hover:bg-red-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-primary"
              >
                Register
              </button>
            </div>
          </form>

          <p className="mt-10 text-center text-sm text-gray-500">
            Already have an Account?{" "}
            <a
              href=""
              className="font-semibold leading-6 text-red-primary hover:text-red-500"
              onClick={() => {
                navigateTo("/");
              }}
            >
              Login here
            </a>
          </p>
        </div>
      </div>
    </>
  );
}
