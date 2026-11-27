import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

const returning = new URLSearchParams(window.location.search);
const oauthState = returning.get("state");
const oauthCode = returning.get("code");
const oauthError = returning.get("error");
if (oauthState && (oauthCode || oauthError)) {
  const next = new URLSearchParams();
  next.set("state", oauthState);
  if (oauthCode) next.set("code", oauthCode);
  if (oauthError) next.set("error", oauthError);
  window.location.replace(`/api/auth/callback?${next.toString()}`);
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
