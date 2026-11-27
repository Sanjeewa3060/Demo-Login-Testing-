import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const LOGIN_ERRORS = {
  mock_mode: "Passkey sign-in needs the Asgardeo organization name. The local sign-in is still available until that is set.",
  not_configured: "Asgardeo is not configured. Add the organization name next to the client id.",
  asgardeo_denied: "Asgardeo did not complete sign-in.",
  invalid_callback: "The sign-in callback was rejected.",
  token_exchange_failed: "Asgardeo did not issue a token. Check the redirect URL and client settings.",
  no_email: "Asgardeo did not release an email address. Enable the email attribute on the application.",
  email_unverified: "Asgardeo reported that this email is not verified, so a session was not created.",
  account_inactive: "This account is deactivated. An administrator can activate it.",
  session_expired: "The session expired. Sign in again.",
};

export default function Login() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("error");
    if (code) {
      setFormError(LOGIN_ERRORS[code] || "Sign-in could not be completed.");
    }
    api("/api/auth/me")
      .then(() => navigate("/portal", { replace: true }))
      .catch(() => {});
    api("/api/auth/config")
      .then(setConfig)
      .catch(() => setConfigError("The API is not reachable. Start the backend on port 8000."));
  }, [navigate]);

  async function onSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setFormError("");
    try {
      await api("/api/auth/mock-login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      navigate("/portal");
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-wrap">
      <section className="login-card">
        <h1>Identity Portal</h1>
        <p className="lede">Sign-in is handled by WSO2 Asgardeo.</p>

        {config?.server_mode === "asgardeo" && (
          <p className="banner ok" role="status">
            Email, password, passkey, email OTP, and TOTP are Asgardeo login steps.
            This application stores product access only.
          </p>
        )}
        {config?.client_id_set && !config?.organization_set && (
          <p className="banner warn" role="status">
            The client id is saved. Passkey sign-in starts after the Asgardeo organization name is added.
          </p>
        )}
        {!config && !configError && <p>Loading sign-in…</p>}
        {configError && <p className="banner bad">{configError}</p>}
        {formError && <p className="banner bad">{formError}</p>}

        {config?.mock_login_enabled && (
          <form onSubmit={onSubmit}>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button type="submit" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        {config && !config.mock_login_enabled && (
          <div className="stack">
            {config.discovery_error && <p className="banner bad">{config.discovery_error}</p>}
            <a className="button-link" href="/api/auth/login">Sign in with WSO2 Asgardeo</a>
            {config.password_recovery_url && (
              <a href={config.password_recovery_url}>Reset password with Asgardeo</a>
            )}
            {config.identity_admin === "not_configured" && (
              <p className="hint">
                Creating customers in WSO2 is not configured until the management application secret is set.
              </p>
            )}
            {config.issuer && <p className="hint">Issuer: {config.issuer}</p>}
          </div>
        )}
      </section>
    </main>
  );
}
