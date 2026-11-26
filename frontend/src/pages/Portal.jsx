import { Link } from "react-router-dom";
import { api } from "../api";
import { formatWhen } from "../components";
import { useSession } from "../session";

const APPS = [
  {
    kind: "fms",
    name: "FMS",
    text: "Dummy facilities work orders.",
    href: "/fms",
    flag: "fms_access",
  },
  {
    kind: "pos",
    name: "POS",
    text: "Dummy point-of-sale receipts.",
    href: "/pos",
    flag: "pos_access",
  },
];

export default function Portal() {
  const me = useSession();

  async function expire() {
    await api("/api/auth/expire", { method: "POST" });
    window.location.href = "/?error=session_expired";
  }

  return (
    <>
      <div className="page-head">
        <h1>Identity Portal</h1>
        <p className="lede">Choose an application. The API allows or refuses it from the account record.</p>
      </div>

      <section className="profile">
        <div>
          <h2>Signed in</h2>
          <dl>
            <div><dt>Name</dt><dd>{me.display_name}</dd></div>
            <div><dt>Email</dt><dd>{me.email}</dd></div>
            <div><dt>Role</dt><dd>{me.role}</dd></div>
            <div><dt>Session expires</dt><dd>{formatWhen(me.session_expires_at)}</dd></div>
            <div><dt>Sign-in</dt><dd>{me.auth_mode === "mock" ? "Local mock" : "WSO2 Asgardeo"}</dd></div>
            {me.auth_mode === "asgardeo" && (
              <>
                <div><dt>email_verified</dt><dd>{me.email_verified}</dd></div>
                <div>
                  <dt>amr</dt>
                  <dd>{me.amr?.length ? me.amr.join(", ") : "Not present in the ID token"}</dd>
                </div>
              </>
            )}
          </dl>
          {me.auth_mode === "mock" && (
            <p className="hint">Email verification, email OTP, and TOTP were not part of this sign-in.</p>
          )}
        </div>
        <button type="button" className="ghost" onClick={expire}>
          Expire session now
        </button>
      </section>

      <section className="cards">
        {APPS.map((app) => {
          const allowed = Boolean(me[app.flag]);
          return (
            <article key={app.kind} className="card">
              <div className="card-top">
                <h2>{app.name}</h2>
                <span className={allowed ? "pill ok" : "pill bad"}>{allowed ? "Allowed" : "No access"}</span>
              </div>
              <p>{app.text}</p>
              <p className="hint">The API checks this again when the application opens.</p>
              <Link className="button-link" to={app.href}>
                {allowed ? "Open" : "Open and check access"}
              </Link>
            </article>
          );
        })}
      </section>
    </>
  );
}
