import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AsgardeoProvider } from "@asgardeo/react";
import App from "./App";
import "./styles.css";

const clientId = import.meta.env.VITE_ASGARDEO_CLIENT_ID;
const baseUrl = import.meta.env.VITE_ASGARDEO_BASE_URL;

function MissingClient() {
  return (
    <main className="wrap">
      <section className="card">
        <h1>Product 2</h1>
        <p>
          Product 2 needs its own Asgardeo application in the techloomai organization.
          Register a second single-page application with redirect URL http://localhost:5174,
          then set VITE_ASGARDEO_CLIENT_ID. Do not reuse Product 1's client ID.
        </p>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {clientId ? (
      <AsgardeoProvider
        clientId={clientId}
        baseUrl={baseUrl}
        scopes={["openid", "profile"]}
        afterSignInUrl={import.meta.env.VITE_APP_ORIGIN}
        afterSignOutUrl={import.meta.env.VITE_APP_ORIGIN}
      >
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AsgardeoProvider>
    ) : (
      <MissingClient />
    )}
  </React.StrictMode>
);
