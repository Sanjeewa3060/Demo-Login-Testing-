import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { SignedIn, SignedOut, SignInButton, SignOutButton, useAsgardeo } from "@asgardeo/react";

const otherUrl = import.meta.env.VITE_OTHER_PRODUCT_URL || "http://localhost:5173";

function Shell({ children }) {
  return (
    <div className="wrap">
      <header className="bar">
        <Link to="/" className="brand">Product 2</Link>
        <nav>
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/profile">Profile</Link>
          <a href={otherUrl}>Open Product 1</a>
        </nav>
        <div className="auth">
          <SignedOut>
            <SignInButton>Sign in with WSO2</SignInButton>
          </SignedOut>
          <SignedIn>
            <SignOutButton>Sign out</SignOutButton>
          </SignedIn>
        </div>
      </header>
      {children}
    </div>
  );
}

function Home() {
  return (
    <Shell>
      <section className="card">
        <p className="kicker">WSO2 Asgardeo · techloomai</p>
        <h1>Product 2</h1>
        <p>
          This is a second application with its own OIDC client. It uses the same
          WSO2 organization. If you already signed in to Product 1, signing in here
          continues that WSO2 session instead of asking for credentials again.
        </p>
        <SignedOut>
          <SignInButton>Sign in with WSO2</SignInButton>
        </SignedOut>
        <SignedIn>
          <p className="ok">Signed in. The dashboard and profile are available.</p>
          <Link className="button" to="/dashboard">Go to the dashboard</Link>
        </SignedIn>
      </section>
    </Shell>
  );
}

function Protected({ children }) {
  const { isSignedIn, isLoading } = useAsgardeo();
  const location = useLocation();
  if (isLoading) return <Shell><p className="card">Checking the WSO2 session…</p></Shell>;
  if (!isSignedIn) return <Navigate to="/" replace state={{ from: location.pathname }} />;
  return children;
}

function useIdToken() {
  const { getDecodedIdToken, isSignedIn } = useAsgardeo();
  const [claims, setClaims] = useState(null);
  useEffect(() => {
    if (!isSignedIn) return;
    let active = true;
    getDecodedIdToken()
      .then((token) => {
        if (active) setClaims(token);
      })
      .catch(() => {
        if (active) setClaims(null);
      });
    return () => {
      active = false;
    };
  }, [getDecodedIdToken, isSignedIn]);
  return claims;
}

function Dashboard() {
  const claims = useIdToken();
  return (
    <Protected>
      <Shell>
        <section className="card">
          <p className="kicker">Protected page</p>
          <h1>Product 2 dashboard</h1>
          <p>Only a signed-in WSO2 user can see this page. Product 2 does not keep its own password.</p>
          <p>Signed in as subject <code>{claims?.sub || "Reading the ID token…"}</code></p>
        </section>
      </Shell>
    </Protected>
  );
}

function Profile() {
  const claims = useIdToken();
  return (
    <Protected>
      <Shell>
        <section className="card">
          <p className="kicker">WSO2 profile</p>
          <h1>Same person in both products</h1>
          <dl>
            <dt>sub</dt>
            <dd><code>{claims?.sub || "The ID token did not include sub."}</code></dd>
            <dt>username</dt>
            <dd>{claims?.preferred_username || claims?.username || "Not released"}</dd>
            <dt>email</dt>
            <dd>{claims?.email || "Not released. The application currently requests openid and profile."}</dd>
          </dl>
          <p>
            Compare this <code>sub</code> with the profile in Product 1. A match means both
            applications recognized the same WSO2 identity.
          </p>
        </section>
      </Shell>
    </Protected>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
