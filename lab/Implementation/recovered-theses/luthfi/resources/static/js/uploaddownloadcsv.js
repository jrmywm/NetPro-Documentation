import { response } from "express";

$(document).ready(function () {
  $("#uploadSingleFileForm").submit(function (event) {
    event.preventDefault();
    var form = $(this);
    var formData = new FormData(form[0]);
    $.ajax({
      type: "POST",
      enctype: "multipart/form-data",
      url: "/upload-csv",
      data: formData,
      async: false,
      processData: false,
      contentType: false,
      cache: false,
      timeout: 600000,
      success: function (data) {
        $("#response").empty();
        if (data.status !== "error") {
          let displayInfo = response.filename + " " + response.message + "<br>";

          $("#response").append(displayInfo);
          // add some css
          $("#response").css("background-color", "lightgreen");
          $("#response").css("border", "1px solid green");
          $("#response").css("border-radius", "10px");
          $("#response").css("display", "block");
          // add margin padding 10px
          $("#response").css("margin", "10px");
          $("#response").css("padding", "10px");
        } else {
          $("#response").append("Error: " + data.message + "<br>");
          // add some css
          $("#response").css("background-color", "red");
          $("#response").css("border", "1px solid darkred");
          $("#response").css("border-radius", "10px");
          $("#response").css("display", "block");
          // add margin padding 10px
          $("#response").css("margin", "10px");
          $("#response").css("padding", "10px");
        }
      },
      error: function (e) {
        alert(e.responseText);
      },
    });
  });

  $("#uploadMultipleFilesForm").submit(function (event) {
    event.preventDefault();
    var form = $(this);

    let formData = new FormData(form[0]);

    $.ajax({
      type: "POST",
      enctype: "multipart/form-data",
      url: "/upload-multiple-csv",
      data: new formData(),
      async: false,
      processData: false,
      contentType: false,
      cache: false,
      timeout: 600000,
      success: function (data) {
        $("#response").empty();
        if (data.status !== "error") {
          let displayInfo = data.filename + " " + data.message + "<br>";

          $("#response").append(displayInfo);
          // add some css
          $("#response").css("background-color", "lightgreen");
          $("#response").css("border", "1px solid green");
          $("#response").css("border-radius", "10px");
          $("#response").css("display", "block");
          // add margin padding 10px
          $("#response").css("margin", "10px");
          $("#response").css("padding", "10px");
        } else {
          $("#response").append("Error: " + data.message + "<br>");
          // add some css
          $("#response").css("background-color", "red");
          $("#response").css("border", "1px solid darkred");
          $("#response").css("border-radius", "10px");
          $("#response").css("display", "block");
          // add margin padding 10px
          $("#response").css("margin", "10px");
          $("#response").css("padding", "10px");
        }
      },
      error: function (e) {
        alert(e.responseText);
      },
    });
  });

  $("#download-csv-form").submit(function (event) {
    event.preventDefault();
    var form = $(this);
    var formData = form.serialize();
    $.ajax({
      type: "POST",
      url: "/download-csv",
      data: formData,
      success: function (data) {
        var blob = new Blob([data], { type: "text/csv" });
        var link = document.createElement("a");
        link.href = window.URL.createObjectURL(blob);
        link.download = "data.csv";
        link.click();
      },
      error: function (e) {
        alert(e.responseText);
      },
    });
  });
});
