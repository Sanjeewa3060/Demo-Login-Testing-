import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

const params = new URLSearchParams(window.location.search);
if (params.get("state") && (params.get("code") || params.get("error"))) {
  window.location.replace(`/api/auth/callback${window.location.search}`);
} else {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>
  );
}
