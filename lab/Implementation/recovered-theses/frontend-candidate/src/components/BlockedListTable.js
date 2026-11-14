import React, { useState, useEffect, useRef } from "react";
import { DataTable } from "primereact/datatable";
import { Column } from "primereact/column";
import { Toast } from "primereact/toast";
import { Button } from "primereact/button";
import { Toolbar } from "primereact/toolbar";
import { Dialog } from "primereact/dialog";
import { InputText } from "primereact/inputtext";
import axios from "axios";

export const isValidIPv4 = (value) => {
  const parts = String(value || "").trim().split(".");
  return (
    parts.length === 4 &&
    parts.every(
      (part) =>
        /^(0|[1-9]\d{0,2})$/.test(part) && Number(part) >= 0 && Number(part) <= 255
    )
  );
};

export const isValidBareDomain = (value) => {
  const domain = String(value || "").trim();
  if (!domain || domain.length > 253 || domain.includes(":") || domain.includes("/")) {
    return false;
  }
  const labels = domain.split(".");
  return (
    labels.length >= 2 &&
    labels.every(
      (label) =>
        label.length > 0 &&
        label.length <= 63 &&
        /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label)
    )
  );
};

export const validateBlockedItem = (item) => {
  if (
    !String(item?.name || "").trim() ||
    !String(item?.domain || "").trim() ||
    !String(item?.ip_add || "").trim() ||
    !item?.category
  ) {
    return "Name, domain, IPv4 address, and category are required.";
  }
  if (!isValidBareDomain(item.domain)) {
    return "Enter a bare domain name, without a URL, path, or port.";
  }
  if (!isValidIPv4(item.ip_add)) {
    return "Enter a valid IPv4 address in standard dotted-decimal form.";
  }
  return "";
};

const toBlockedItemPayload = (item) => ({
  name: item.name.trim(),
  domain: item.domain.trim().toLowerCase(),
  ip_add: item.ip_add.trim(),
  category: item.category,
});

const BlockedListTable = ({ id }) => {
  const emptyBlockedItem = {
    id: null,
    ps_id: null,
    name: "",
    domain: "",
    ip_add: "",
    hit_count: 0,
    category: "",
  };

  const [blockedItems, setBlockedItems] = useState(null);
  const [listError, setListError] = useState("");
  const [blockedItemDialog, setBlockedItemDialog] = useState(false);
  const [blockedItem, setBlockedItem] = useState(emptyBlockedItem);
  const [selectedBlockedItem, setSelectedBlockedItem] = useState(null);
  const [globalFilter, setGlobalFilter] = useState(null);
  const toast = useRef(null);
  const dt = useRef(null);
  const [deleteBlockedItemDialog, setDeleteBlockedItemDialog] = useState(false);
  const [updateBlockedItemDialog, setUpdateBlockedItemDialog] = useState(false);
  const [deleteBatchItemDialog, setDeleteBatchItemDialog] = useState(false);
  const [updateBlockedItem, setUpdateBlockedItem] = useState(emptyBlockedItem);
  const [deleteBlockedItem, setDeleteBlockedItem] = useState(emptyBlockedItem);
  const [formError, setFormError] = useState("");
  const [updateError, setUpdateError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const mutationInProgress = useRef(false);

  useEffect(() => {
    fetchData();
    const intervalId = setInterval(fetchData, 5000); // Fetch data every 5 seconds
    return () => clearInterval(intervalId); // Cleanup interval on unmount
  }, [id]);

  const fetchData = async () => {
    try {
      const response = await axios.get(
        `${process.env.REACT_APP_BASE_URL}/ps/blocked-list`
      );

      if (
        response.data.message &&
        response.data.message === "No PS blocked list found"
      ) {
        setBlockedItems([]); // Set an empty array if no data is found
      } else {
        if (!Array.isArray(response.data)) {
          throw new Error("The blocked-list response was not a list.");
        }
        setBlockedItems(response.data);
      }
      setListError("");
    } catch (error) {
      setListError(error.response?.data?.message || "Could not load the blocked list. Existing rows are left visible.");
    }
  };

  const openNew = () => {
    setBlockedItem(emptyBlockedItem);
    setFormError("");
    setBlockedItemDialog(true);
  };

  const hideDialog = () => {
    if (mutationInProgress.current) return;
    setFormError("");
    setUpdateError("");
    setDeleteError("");
    setBlockedItemDialog(false);
    setUpdateBlockedItemDialog(false);
    setDeleteBlockedItemDialog(false);
    setDeleteBatchItemDialog(false);
  };

  const saveBlockedItem = async () => {
    if (mutationInProgress.current) return;
    const validationError = validateBlockedItem(blockedItem);
    if (validationError) {
      setFormError(validationError);
      return;
    }

    mutationInProgress.current = true;
    setIsSaving(true);
    setFormError("");
    try {
      const response = await axios.post(
        `${process.env.REACT_APP_BASE_URL}/ps/blocked-list`,
        toBlockedItemPayload(blockedItem)
      );
      if (response.status !== 200 || !response.data?.createdBlockedList?.id) {
        throw new Error("The server did not confirm that the rule was saved.");
      }
      await fetchData();
      toast.current?.show({
        severity: "success",
        summary: "Saved",
        detail: "Rule saved; Policy synchronization may take a moment.",
        life: 4000,
      });
      setBlockedItemDialog(false);
      setBlockedItem(emptyBlockedItem);
    } catch (error) {
      setFormError(error.response?.data?.message || error.message || "Failed to save the rule.");
      toast.current?.show({ severity: "error", summary: "Save failed", detail: "The rule was not confirmed as saved.", life: 4000 });
    } finally {
      mutationInProgress.current = false;
      setIsSaving(false);
    }
  };

  const openUpdateDialog = (item) => {
    setUpdateBlockedItem({
      ...emptyBlockedItem,
      ...item,
      name: String(item?.name || ""),
      domain: String(item?.domain || ""),
      ip_add: String(item?.ip_add || ""),
      category: String(item?.category || ""),
    });
    setUpdateError("");
    setUpdateBlockedItemDialog(true);
  };

  const openDeleteDialog = (rowData) => {
    setDeleteBlockedItem(rowData);
    setDeleteError("");
    setDeleteBlockedItemDialog(true);
  };

  const openBatchDeleteDialog = () => {
    setDeleteError("");
    setDeleteBatchItemDialog(true);
  };

  const handleUpdateBlockedItem = async () => {
    if (mutationInProgress.current) return;
    const validationError = validateBlockedItem(updateBlockedItem);
    if (validationError) {
      setUpdateError(validationError);
      return;
    }
    mutationInProgress.current = true;
    setIsUpdating(true);
    setUpdateError("");
    try {
      const response = await axios.put(
        `${process.env.REACT_APP_BASE_URL}/ps/blocked-list/${updateBlockedItem.id}`,
        toBlockedItemPayload(updateBlockedItem)
      );
      if (
        response.status !== 200 ||
        String(response.data?.updatedBlockedList?.id) !== String(updateBlockedItem.id)
      ) {
        throw new Error("The server did not confirm that the rule was updated.");
      }
      await fetchData();
      toast.current?.show({
          severity: "success",
          summary: "Saved",
          detail: "Rule updated; Policy synchronization may take a moment.",
          life: 4000,
      });
      setUpdateBlockedItemDialog(false);
      setUpdateBlockedItem(emptyBlockedItem);
    } catch (error) {
      setUpdateError(error.response?.data?.message || error.message || "Failed to update the rule.");
      toast.current?.show({ severity: "error", summary: "Update failed", detail: "The rule was not confirmed as updated.", life: 4000 });
    } finally {
      mutationInProgress.current = false;
      setIsUpdating(false);
    }
  };

  const deleteBlockedItemConfirm = async () => {
    if (mutationInProgress.current) return;
    if (!deleteBlockedItem.id) {
      setDeleteError("No rule ID is selected; nothing was deleted.");
      return;
    }
    mutationInProgress.current = true;
    setIsDeleting(true);
    setDeleteError("");
    try {
      const response = await axios.delete(
        `${process.env.REACT_APP_BASE_URL}/ps/blocked-list/${deleteBlockedItem.id}`
      );
      if (
        response.status !== 200 ||
        String(response.data?.deletedBlockedList?.id) !== String(deleteBlockedItem.id)
      ) {
        throw new Error(
          `Failed to delete blocked item with ID ${deleteBlockedItem.id}`
        );
      }

      await fetchData();
      toast.current?.show({
        severity: "success",
        summary: "Successful",
        detail: "Blocked Item Deleted",
        life: 3000,
      });
      setDeleteBlockedItemDialog(false);
      setDeleteBlockedItem(emptyBlockedItem);
    } catch (error) {
      setDeleteError(error.response?.data?.message || error.message || "Failed to delete the rule.");
      toast.current?.show({
        severity: "error",
        summary: "Error",
        detail: "Failed to delete blocked item",
        life: 3000,
      });
    } finally {
      mutationInProgress.current = false;
      setIsDeleting(false);
    }
  };

  const confirmDeleteBatchBlockedItem = async () => {
    if (mutationInProgress.current || !selectedBlockedItem?.length) return;
    mutationInProgress.current = true;
    setIsDeleting(true);
    setDeleteError("");
    let didDelete = false;
    try {
      const results = await Promise.allSettled(
        selectedBlockedItem.map(async (blockedItem) => {
          const response = await axios.delete(
            `${process.env.REACT_APP_BASE_URL}/ps/blocked-list/${blockedItem.id}`
          );
          if (
            response.status !== 200 ||
            String(response.data?.deletedBlockedList?.id) !== String(blockedItem.id)
          ) {
            throw new Error(
              `Failed to delete blocked item with ID ${blockedItem.id}`
            );
          }
        })
      );

      const failedIds = results
        .map((result, index) => (result.status === "rejected" ? selectedBlockedItem[index].id : null))
        .filter(Boolean);
      await fetchData();
      if (failedIds.length) {
        setSelectedBlockedItem(selectedBlockedItem.filter((item) => failedIds.includes(item.id)));
        setDeleteError(`Deletion was not confirmed for IDs: ${failedIds.join(", ")}.`);
        toast.current?.show({ severity: "error", summary: "Partial delete", detail: "Some selected rule deletions were not confirmed.", life: 4000 });
        return;
      }
      didDelete = true;
      toast.current?.show({
        severity: "success",
        summary: "Successful",
        detail: "Blocked Item(s) Deleted",
        life: 3000,
      });
      setDeleteBatchItemDialog(false);
    } catch (error) {
      setDeleteError(error.response?.data?.message || error.message || "Failed to delete selected rules.");
      toast.current?.show({
        severity: "error",
        summary: "Error",
        detail: "Failed to delete blocked item(s)",
        life: 3000,
      });
    } finally {
      mutationInProgress.current = false;
      setIsDeleting(false);
      if (didDelete) {
        setDeleteBatchItemDialog(false);
        setSelectedBlockedItem(null);
      }
    }
  };

  const onInputChangeUpdate = (e, name) => {
    const val = e.target.value || "";
    setUpdateError("");
    setUpdateBlockedItem((prevState) => ({ ...prevState, [name]: val }));
  };

  const onInputChange = (e, name) => {
    const val = e.target.value || "";
    setFormError("");
    setBlockedItem((prevState) => ({ ...prevState, [name]: val }));
  };

  const handleCategoryChange = (event) => {
    // Update the blockedItem state with the new category
    setBlockedItem((prevState) => ({ ...prevState, category: event.target.value }));
  };

  const handleCategoryChangeUpdate = (event) => {
    // Update the updateBlockedItem state with the new category
    setUpdateBlockedItem((prevState) => ({ ...prevState, category: event.target.value }));
  };

  const leftToolbarTemplate = () => {
    return (
      <div className="flex flex-wrap gap-2 font-['Helvetica']">
        <Button
          label="New"
          icon="pi pi-plus"
          severity="success"
          onClick={openNew}
        />
        <a href="/dashboard/imports" className="p-button p-button-outlined font-['Helvetica']" style={{ display: 'inline-flex', alignItems: 'center', padding: '0.75rem 1rem' }}>Import CSV</a>
        <Button
          label="Delete"
          icon="pi pi-trash"
          severity="danger"
          onClick={openBatchDeleteDialog}
          disabled={!selectedBlockedItem || !selectedBlockedItem.length}
        />
      </div>
    );
  };

  const rightToolbarTemplate = () => {
    return (
      <Button
        label="Export"
        icon="pi pi-upload"
        className="p-button-help font-['Helvetica']"
        // onClick={exportCSV}
      />
    );
  };

  const header = (
    <div className="flex flex-wrap gap-2 align-items-center justify-content-between ">
      <h4 className="m-0">Blocked List</h4>
      <span className="p-input-icon-end">
        <i className="pi pi-search" />
        <InputText
          className="p-2 mr-1 ml-2 rounded-xl font-['Helvetica'] font-normal"
          type="search"
          onInput={(e) => setGlobalFilter(e.target.value)}
          placeholder="Search..."
        />
      </span>
    </div>
  );

  const blockedItemDialogFooter = (
    <React.Fragment>
      <Button
        label="Cancel"
        icon="pi pi-times"
        className="p-button-text bg-gray-300 text-gray-700 hover:bg-gray-400 hover:text-gray-800 rounded-lg px-4 py-2 mr-2  font-['Helvetica']"
        onClick={hideDialog}
      />
      <Button
        label="Save"
        icon="pi pi-check"
        className="p-button-text bg-red-primary hover:bg-red-500 rounded-lg px-4 py-2 text-white font-['Helvetica']"
        onClick={saveBlockedItem}
        disabled={isSaving}
      />
    </React.Fragment>
  );

  const deleteBlockedItemFooterDialog = (
    <React.Fragment>
      <Button
        label="Cancel"
        icon="pi pi-times"
        className="p-button-text bg-gray-300 text-gray-700 hover:bg-gray-400 hover:text-gray-800 rounded-lg px-4 py-2 mr-2  font-['Helvetica']"
        onClick={hideDialog}
      />
      <Button
        label="Yes"
        icon="pi pi-check"
        className="p-button-text bg-red-primary hover:bg-red-500 rounded-lg px-4 py-2 text-white font-['Helvetica']"
        onClick={deleteBlockedItemConfirm}
        disabled={isDeleting}
      />
    </React.Fragment>
  );

  const deleteBatchBlockedItemFooterDialog = (
    <React.Fragment>
      <Button
        label="Cancel"
        icon="pi pi-times"
        className="p-button-text bg-gray-300 text-gray-700 hover:bg-gray-400 hover:text-gray-800 rounded-lg px-4 py-2 mr-2  font-['Helvetica']"
        onClick={hideDialog}
      />
      <Button
        label="Yes"
        icon="pi pi-check"
        className="p-button-text bg-red-primary hover:bg-red-500 rounded-lg px-4 py-2 text-white font-['Helvetica']"
        onClick={confirmDeleteBatchBlockedItem}
        disabled={isDeleting}
      />
    </React.Fragment>
  );

  const blockedItemDialogFooterUpdate = (
    <React.Fragment>
      <Button
        label="Cancel"
        icon="pi pi-times"
        className="p-button-text bg-gray-300 text-gray-700 hover:bg-gray-400 hover:text-gray-800 rounded-lg px-4 py-2 mr-2  font-['Helvetica']"
        onClick={hideDialog}
      />
      <Button
        label="Save"
        icon="pi pi-check"
        className="p-button-text bg-red-primary hover:bg-red-500 rounded-lg px-4 py-2 text-white font-['Helvetica']"
        onClick={handleUpdateBlockedItem}
        disabled={isUpdating}
      />
    </React.Fragment>
  );

  const actionBodyTemplate = (rowData) => {
    return (
      <React.Fragment>
        <Button
          icon="pi pi-pencil"
          aria-label={`Edit ${rowData.name}`}
          rounded
          outlined
          style={{ color: "blue" }}
          onClick={() => openUpdateDialog(rowData)}
        />
        <Button
          icon="pi pi-trash"
          aria-label={`Delete ${rowData.name}`}
          rounded
          outlined
          severity="danger"
          style={{ color: "red" }}
          onClick={() => openDeleteDialog(rowData)}
        />
      </React.Fragment>
    );
  };

  const hideDeleteBlockedItemDialog = () => {
    if (mutationInProgress.current) return;
    setDeleteBlockedItemDialog(false);
    setDeleteError("");
  };

  return (
    <div className="body ">
      <Toast ref={toast} />
      <div className="card">
        <div className="flex justify-end mb-2">
          <Toolbar
            className="mb-4"
            start={leftToolbarTemplate}
            end={rightToolbarTemplate}
          ></Toolbar>
        </div>
        {listError && <p role="alert" className="text-red-600 mb-3">{listError}</p>}
        <DataTable
          ref={dt}
          value={blockedItems}
          selection={selectedBlockedItem}
          onSelectionChange={(e) => setSelectedBlockedItem(e.value)}
          dataKey="id"
          paginator
          rows={20}
          rowsPerPageOptions={[10, 15, 20]}
          paginatorTemplate="RowsPerPageDropdown CurrentPageReport PrevPageLink NextPageLink"
          currentPageReportTemplate="{first}-{last} of {totalRecords}"
          scrollable
          scrollHeight="calc(100vh - 300px)"
          globalFilter={globalFilter}
          header={header}
        >
          <Column selectionMode="multiple" exportable={false}></Column>
          <Column field="name" header="Name" sortable></Column>
          <Column field="domain" header="Domain" sortable></Column>
          <Column field="ip_add" header="IPv4" sortable></Column>
          <Column field="hit_count" header="Hit Count" sortable></Column>
          <Column field="category" header="Category" sortable></Column>
          <Column
            body={actionBodyTemplate}
            style={{ textAlign: "center", overflow: "visible" }}
          ></Column>
        </DataTable>
      </div>

      <Dialog
        visible={blockedItemDialog}
        style={{ width: "30rem" }}
        header="Add/Edit Blocked Item"
        modal
        className="p-fluid font-['Helvetica']"
        footer={blockedItemDialogFooter}
        onHide={hideDialog}
      >
        <div className="p-field">
          <label htmlFor="name" className="font-['Helvetica']">
            Name
          </label>
          <InputText
            id="name"
            value={blockedItem.name}
            onChange={(e) => onInputChange(e, "name")}
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
            // Add Tailwind classes for styling
          />
        </div>
        <div className="p-field">
          <label htmlFor="domain" className="font-['Helvetica']">
            Domain
          </label>
          <InputText
            id="domain"
            value={blockedItem.domain}
            onChange={(e) => onInputChange(e, "domain")}
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
            // Add Tailwind classes for styling
          />
        </div>
        <div className="p-field">
          <label htmlFor="ip_add" className="font-['Helvetica']">
            IPv4 address
          </label>
          <InputText
            id="ip_add"
            value={blockedItem.ip_add}
            onChange={(e) => onInputChange(e, "ip_add")}
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
            autoComplete="off"
            placeholder="31.13.87.36"
          />
        </div>
        <div className="p-field">
          <label htmlFor="category" className="font-['Helvetica']">
            Category
          </label>
          <select
            id="category"
            name="category"
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
            value={blockedItem.category}
            onChange={handleCategoryChange} // Attach the onChange handler here
          >
            <option value=""></option>
            <option value="Social Media">Social Media</option>
            <option value="News">News</option>
            <option value="Education">Education</option>
            <option value="Entertainment">Entertainment</option>
            <option value="Shopping">Shopping</option>
            <option value="Finance">Finance</option>
            <option value="Health">Health</option>
            <option value="Sports">Sports</option>
            <option value="Technology">Technology</option>
            <option value="Other">Other</option>
          </select>
        </div>
        {formError && <p role="alert" className="text-red-600 mt-2">{formError}</p>}
        <p className="text-sm text-gray-600 mt-2">Saving a rule does not confirm that Policy has synchronized it or that traffic is blocked.</p>
      </Dialog>

      <Dialog
        visible={deleteBlockedItemDialog}
        style={{ width: "30rem" }}
        header="Confirm"
        modal
        footer={deleteBlockedItemFooterDialog}
        onHide={hideDeleteBlockedItemDialog}
        className="font-['Helvetica']"
      >
        <div>
          <p>
            Are you sure you want to delete the blocked item{" "}
            <strong>{deleteBlockedItem.name}</strong> (ID: <code>{deleteBlockedItem.id}</code>)?
          </p>
          {deleteError && <p role="alert" className="text-red-600">{deleteError}</p>}
        </div>
      </Dialog>

      <Dialog
        visible={deleteBatchItemDialog}
        style={{ width: "30rem" }}
        header="Confirm"
        modal
        footer={deleteBatchBlockedItemFooterDialog}
        onHide={hideDialog}
        className="font-['Helvetica']"
      >
        <div>
          <p>
            Delete {selectedBlockedItem?.length || 0} selected rule(s):{" "}
            <strong>{(selectedBlockedItem || []).map((item) => `${item.name} (${item.id})`).join(", ")}</strong>?
          </p>
          {deleteError && <p role="alert" className="text-red-600">{deleteError}</p>}
        </div>
      </Dialog>

      <Dialog
        visible={updateBlockedItemDialog}
        style={{ width: "30rem" }}
        header="Update Blocked Item"
        modal
        className="p-fluid font-['Helvetica']"
        footer={blockedItemDialogFooterUpdate}
        onHide={hideDialog}
      >
        <div className="p-field">
          <label htmlFor="update_name" className="font-['Helvetica']">
            Name
          </label>
          <InputText
            id="update_name"
            value={updateBlockedItem.name}
            onChange={(e) => onInputChangeUpdate(e, "name")}
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
          />
        </div>
        <div className="p-field">
          <label htmlFor="update_domain" className="font-['Helvetica']">
            Domain
          </label>
          <InputText
            id="update_domain"
            value={updateBlockedItem.domain}
            onChange={(e) => onInputChangeUpdate(e, "domain")}
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
          />
        </div>
        <div className="p-field">
          <label htmlFor="update_ip_add" className="font-['Helvetica']">
            IPv4 address
          </label>
          <InputText
            id="update_ip_add"
            value={updateBlockedItem.ip_add}
            onChange={(e) => onInputChangeUpdate(e, "ip_add")}
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
            autoComplete="off"
          />
        </div>
        <div className="p-field">
          <label htmlFor="update_category" className="font-['Helvetica']">
            Category
          </label>
          <select
            id="update_category"
            name="category"
            className="p-inputtext-custom w-full p-2 border border-gray-300 rounded-xl mt-1"
            value={updateBlockedItem.category}
            onChange={handleCategoryChangeUpdate} // Attach the onChange handler here
          >
            <option value="Social Media">Social Media</option>
            <option value="News">News</option>
            <option value="Education">Education</option>
            <option value="Entertainment">Entertainment</option>
            <option value="Shopping">Shopping</option>
            <option value="Finance">Finance</option>
            <option value="Health">Health</option>
            <option value="Sports">Sports</option>
            <option value="Technology">Technology</option>
            <option value="Other">Other</option>
          </select>
        </div>
        {updateError && <p role="alert" className="text-red-600 mt-2">{updateError}</p>}
      </Dialog>
    </div>
  );
};

export default BlockedListTable;
