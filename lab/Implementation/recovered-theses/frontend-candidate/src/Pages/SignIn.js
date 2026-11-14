import axios from "axios";
import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Toast } from "primereact/toast";
import { data } from "autoprefixer";

export default function SignIn() {
  const navigateTo = useNavigate();
  const token = localStorage.getItem("token");
  const toast = useRef(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (token) {
      navigateTo("/dashboard");
    }
  }, [token]); // Add token to the dependency array

  // if (token) {
  //   navigateTo("/dashboard");
  // }

  const handleSubmit = (event) => {
    event.preventDefault();

    if (!email || !password) {
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
    };

    axios
      .post(`${process.env.REACT_APP_BASE_URL}/user/login`, body)
      .then((response) => {
        if (response.data.message === "Success") {
          localStorage.setItem("token", response.data.loginResult.token);
          toast.current.show({
            severity: "success",
            summary: "Success",
            detail: "Logged in successfully",
            life: 3000,
          });
          // Delay the navigation
          setTimeout(() => {
            navigateTo("/dashboard");
          }, 1100); // Delay should be slightly more than the life of the toast
        }
      })
      .catch((error) => {
        toast.current.show({
          severity: "error",
          summary: "Error",
          detail: error.response.data.message, // Changed this line
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
            Sign in to your account
          </h2>
        </div>

        <div className="mt-10 sm:mx-auto sm:w-full sm:max-w-sm">
          <form className="space-y-6" action="#" method="POST">
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
                  type="email"
                  autoComplete="email"
                  required
                  onChange={(event) => setEmail(event.target.value)}
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
                  type="password"
                  autoComplete="current-password"
                  onChange={(event) => setPassword(event.target.value)}
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
                Sign in
              </button>
            </div>
          </form>

          <p className="mt-10 text-center text-sm text-gray-500">
            Not a member?{" "}
            <a
              href=""
              className="font-semibold leading-6 text-red-primary hover:text-red-500"
              onClick={() => {
                navigateTo("register");
              }}
            >
              Register here
            </a>
          </p>
        </div>
      </div>
    </>
  );
}
