import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { TopBar, formatWhen } from "../components";

export default function Report() {
  const [me, setMe] = useState(null);
  const [config, setConfig] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/auth/me").then(setMe).catch(() => setMe(null));
    api("/api/auth/config").then(setConfig).catch(() => setConfig(null));
    api("/api/security/report").then(setReport).catch((err) => setError(err.message));
  }, []);

  const counts = report?.summary || { pass: 0, fail: 0, not_tested: 0 };

  return (
    <div className="page">
      <TopBar me={me} />
      <main className="content">
        <div className="page-head">
          <h1>Security report</h1>
          <p className="lede">
            {report
              ? `Passed ${counts.pass}. Failed ${counts.fail}. Not tested ${counts.not_tested}. Not tested is not a pass.`
              : "Loading the latest report."}
          </p>
        </div>

        {config && (
          <p className={config.server_mode === "mock" ? "banner warn" : "banner ok"} role="status">
            This running server is in {config.server_mode === "mock" ? "mock mode" : "Asgardeo mode"}.
            {config.server_mode === "mock"
              ? " Local sign-in is active because Asgardeo credentials were not found, or mock mode was forced."
              : " Hosted Asgardeo steps still need a real login before they can be marked passed."}
          </p>
        )}

        {report && <p className="disclaimer">{report.disclaimer}</p>}
        {report && (
          <p className="hint">
            Generated {formatWhen(report.generated_at)}. Project MOCK_MODE is{" "}
            {report.project_env?.mock_mode_setting}. Asgardeo client configured:{" "}
            {report.project_env?.asgardeo_client_configured ? "yes" : "no"}.
          </p>
        )}
        {error && (
          <p className="banner bad">
            {error} From the backend folder, run <code>python run_security_tests.py</code>.
          </p>
        )}
        {!report && !error && <p>Loading report…</p>}
        {report && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Check</th>
                  <th>Result</th>
                  <th>Scope</th>
                  <th>What happened</th>
                </tr>
              </thead>
              <tbody>
                {report.tests.map((test) => (
                  <tr key={test.id}>
                    <td>{test.name}</td>
                    <td><span className={`pill ${test.status}`}>{test.status.replace("_", " ")}</span></td>
                    <td>{test.scope}</td>
                    <td className="evidence">{test.evidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="hint"><Link to="/portal">Back to the portal</Link></p>
      </main>
      <footer>Dummy data only. This demo is not connected to a production system.</footer>
    </div>
  );
}
