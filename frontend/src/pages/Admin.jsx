import { useEffect, useState } from "react";
import { api } from "../api";
import { useSession } from "../session";

export default function Admin() {
  const me = useSession();
  const [accounts, setAccounts] = useState(null);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);

  useEffect(() => {
    let live = true;
    api("/api/admin/customers")
      .then((body) => {
        if (live) setAccounts(body.accounts);
      })
      .catch((err) => {
        if (live) setError(err.message);
      });
    return () => {
      live = false;
    };
  }, []);

  async function update(account, patch) {
    setSavingId(account.id);
    setError("");
    try {
      const updated = await api(`/api/admin/customers/${account.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setAccounts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingId(null);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Accounts</h1>
        <p className="lede">
          Changes are stored in the demo database and enforced by the product APIs.
          Signed in as {me.display_name}.
        </p>
      </div>
      {error && <p className="banner bad">{error}</p>}
      {!accounts && !error && <p>Loading accounts…</p>}
      {accounts && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>FMS</th>
                <th>POS</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td>{account.display_name}</td>
                  <td>{account.email}</td>
                  <td>{account.role}</td>
                  <td>
                    <button
                      type="button"
                      className="ghost"
                      disabled={savingId === account.id}
                      onClick={() => update(account, { active: !account.active })}
                    >
                      {account.active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="ghost"
                      disabled={savingId === account.id}
                      onClick={() => update(account, { fms_access: !account.fms_access })}
                    >
                      {account.fms_access ? "Disable FMS" : "Enable FMS"}
                    </button>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="ghost"
                      disabled={savingId === account.id}
                      onClick={() => update(account, { pos_access: !account.pos_access })}
                    >
                      {account.pos_access ? "Disable POS" : "Enable POS"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
