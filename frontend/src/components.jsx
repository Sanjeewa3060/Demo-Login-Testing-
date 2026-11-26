import { Link } from "react-router-dom";

export function TopBar({ me }) {
  return (
    <header className="topbar">
      <Link to={me ? "/portal" : "/"} className="brand-lockup">
        <span className="brand">Identity Portal</span>
      </Link>
      <nav>
        <Link to="/portal">Portal</Link>
        <Link to="/admin">Admin</Link>
        <Link to="/report">Security report</Link>
      </nav>
      <div className="who">
        {me ? (
          <>
            <span className="who-name">{me.display_name}</span>
            <a href="/api/auth/logout">Log out</a>
          </>
        ) : (
          <Link to="/">Sign in</Link>
        )}
      </div>
    </header>
  );
}

export function Shell({ me, children }) {
  return (
    <div className="page">
      <TopBar me={me} />
      {me?.server_mode === "mock" && (
        <p className="banner warn" role="status">
          MOCK MODE. This session came from the local dummy sign-in. It does not
          prove WSO2 Asgardeo login, email verification, email OTP, TOTP, or
          Asgardeo single sign-on.
        </p>
      )}
      {me?.server_mode === "asgardeo" && (
        <p className="banner ok" role="status">
          Sign-in was delegated to WSO2 Asgardeo. FMS and POS permissions are
          still read from this demo&apos;s database on every request.
        </p>
      )}
      <main className="content">{children}</main>
      <footer>Dummy data only. This demo is not connected to a production system.</footer>
    </div>
  );
}

export function formatWhen(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
