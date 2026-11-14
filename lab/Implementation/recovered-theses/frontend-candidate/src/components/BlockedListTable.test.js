import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import BlockedListTable from "./BlockedListTable";

jest.mock("axios", () => ({
  get: jest.fn(),
  post: jest.fn(),
  put: jest.fn(),
  delete: jest.fn(),
}));

jest.mock("primereact/datatable", () => {
  const ReactLib = require("react");
  return {
    DataTable: ({ value, children }) => {
      const columns = ReactLib.Children.toArray(children);
      return (
        <div role="table">
          {(value || []).map((row) => (
            <div role="row" key={row.id}>
              {columns.map((column, index) => (
                <span key={`${row.id}-${index}`}>
                  {column.props.field ? row[column.props.field] : column.props.body?.(row)}
                </span>
              ))}
            </div>
          ))}
        </div>
      );
    },
  };
});
jest.mock("primereact/column", () => ({ Column: () => null }));
jest.mock("primereact/toast", () => {
  const ReactLib = require("react");
  return {
    Toast: ReactLib.forwardRef((_props, ref) => {
      ReactLib.useImperativeHandle(ref, () => ({ show: jest.fn() }));
      return null;
    }),
  };
});
jest.mock("primereact/button", () => ({
  Button: ({ label, icon, onClick, disabled, "aria-label": accessibleName }) => (
    <button type="button" aria-label={accessibleName || label || icon} onClick={onClick} disabled={disabled}>
      {label || icon}
    </button>
  ),
}));
jest.mock("primereact/toolbar", () => ({
  Toolbar: ({ start, end }) => (
    <div>{typeof start === "function" ? start() : start}{typeof end === "function" ? end() : end}</div>
  ),
}));
jest.mock("primereact/dialog", () => ({
  Dialog: ({ visible, header, footer, children }) =>
    visible ? <section role="dialog" aria-label={header}>{children}{footer}</section> : null,
}));
jest.mock("primereact/inputtext", () => ({
  InputText: (props) => <input {...props} />,
}));

const row = {
  id: "row-a",
  name: "Rule A",
  domain: "example.test",
  ip_add: "31.13.87.40",
  category: "Other",
  hit_count: 0,
};

const fillNewForm = () => {
  fireEvent.click(screen.getByRole("button", { name: "New" }));
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Facebook browser demo" } });
  fireEvent.change(screen.getByLabelText("Domain"), { target: { value: "www.facebook.com" } });
  fireEvent.change(screen.getByLabelText("IPv4 address"), { target: { value: "31.13.87.36" } });
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "Other" } });
};

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue({ data: [row] });
});

test("creates a rule with the flat IPv4 payload and shows its IP in the table", async () => {
  axios.post.mockResolvedValue({ status: 200, data: { createdBlockedList: { id: "new-id" } } });
  render(<BlockedListTable id="policy-id" />);
  expect(await screen.findByText("31.13.87.40")).toBeInTheDocument();
  fillNewForm();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/ps/blocked-list"),
    { name: "Facebook browser demo", domain: "www.facebook.com", ip_add: "31.13.87.36", category: "Other" }
  ));
});

test("rejects invalid IPv4 input without making a request", async () => {
  render(<BlockedListTable id="policy-id" />);
  await screen.findByText("31.13.87.40");
  fillNewForm();
  fireEvent.change(screen.getByLabelText("IPv4 address"), { target: { value: "999.13.87.36" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("valid IPv4");
  expect(axios.post).not.toHaveBeenCalled();
});

test("updates the selected rule IPv4 using its row ID", async () => {
  axios.put.mockResolvedValue({ status: 200, data: { updatedBlockedList: { id: row.id } } });
  render(<BlockedListTable id="policy-id" />);
  await screen.findByText("31.13.87.40");
  fireEvent.click(screen.getByRole("button", { name: "Edit Rule A" }));
  fireEvent.change(screen.getByLabelText("IPv4 address"), { target: { value: "31.13.87.41" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
    expect.stringContaining(`/ps/blocked-list/${row.id}`),
    { name: row.name, domain: row.domain, ip_add: "31.13.87.41", category: row.category }
  ));
});

test("confirms and deletes exactly the selected row", async () => {
  axios.get.mockResolvedValue({ data: [row, { ...row, id: "row-b", name: "Rule B", ip_add: "31.13.87.42" }] });
  axios.delete.mockResolvedValue({ status: 200, data: { deletedBlockedList: { id: "row-b" } } });
  render(<BlockedListTable id="policy-id" />);
  await screen.findByText("31.13.87.42");
  fireEvent.click(screen.getByRole("button", { name: "Delete Rule B" }));
  expect(screen.getByRole("dialog", { name: "Confirm" })).toHaveTextContent("ID: row-b");
  fireEvent.click(screen.getByRole("button", { name: "Yes" }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith(expect.stringContaining("/ps/blocked-list/row-b")));
});

test("keeps entered form values and reports the server error", async () => {
  axios.post.mockRejectedValue(new Error("offline"));
  render(<BlockedListTable id="policy-id" />);
  await screen.findByText("31.13.87.40");
  fillNewForm();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  expect(screen.getByLabelText("IPv4 address")).toHaveValue("31.13.87.36");
  expect(screen.getByLabelText("Domain")).toHaveValue("www.facebook.com");
});
