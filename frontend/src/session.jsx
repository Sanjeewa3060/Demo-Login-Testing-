import { createContext, useContext, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "./api";
import { Shell } from "./components";

const SessionContext = createContext(null);

export function useSession() {
  return useContext(SessionContext);
}

export function RequireAuth({ children }) {
  const [state, setState] = useState({ loading: true, me: null });

  useEffect(() => {
    let live = true;
    api("/api/auth/me")
      .then((me) => {
        if (live) setState({ loading: false, me });
      })
      .catch(() => {
        if (live) setState({ loading: false, me: null });
      });
    return () => {
      live = false;
    };
  }, []);

  if (state.loading) {
    return <p className="center">Loading session…</p>;
  }
  if (!state.me) {
    return <Navigate to="/" replace />;
  }
  return (
    <SessionContext.Provider value={state.me}>
      <Shell me={state.me}>{children}</Shell>
    </SessionContext.Provider>
  );
}
