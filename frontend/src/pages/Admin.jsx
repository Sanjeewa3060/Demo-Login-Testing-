import { useEffect, useState } from "react";
import { api } from "../api";
import { useSession } from "../session";

const PRODUCTS = [
  { id: "fms", label: "FMS", paid: "fms_paid", flag: "fms_access" },
  { id: "pos", label: "POS", paid: "pos_paid", flag: "pos_access" },
  { id: "ecommerce", label: "E-Commerce", paid: "ecommerce_paid", flag: "ecommerce_access" },
  { id: "ems", label: "EMS", paid: "ems_paid", flag: "ems_access" },
];

const EMPTY_PRODUCTS = { fms: false, pos: true, ecommerce: false, ems: false };

function productList(flags) {
  const names = PRODUCTS.filter((item) => flags[item.id]).map((item) => item.label);
  return names.length ? names.join(", ") : "None";
}

export default function Admin() {
  const me = useSession();
  const [accounts, setAccounts] = useState(null);
  const [audit, setAudit] = useState([]);
  const [identityAdmin, setIdentityAdmin] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [products, setProducts] = useState(EMPTY_PRODUCTS);
  const [pendingCreate, setPendingCreate] = useState(null);
  const [pendingChange, setPendingChange] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [saving, setSaving] = useState(false);

  function load() {
    return api("/api/admin/customers")
      .then((body) => {
        setAccounts(body.accounts);
        setAudit(body.audit || []);
        setIdentityAdmin(body.identity_admin || "");
      })
      .catch((err) => setError(err.message));
  }

  useEffect(() => {
    load();
  }, []);

  function reviewCreate(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!Object.values(products).some(Boolean)) {
      setError("Choose at least one product this company paid for.");
      return;
    }
    setPendingCreate({
      companyName: companyName.trim(),
      email: email.trim(),
      products: { ...products },
    });
  }

  async function confirmCreate() {
    if (!pendingCreate) return;
    setSaving(true);
    setError("");
    try {
      const account = await api("/api/admin/companies", {
        method: "POST",
        body: JSON.stringify({
          company_name: pendingCreate.companyName,
          email: pendingCreate.email,
          fms_paid: pendingCreate.products.fms,
          pos_paid: pendingCreate.products.pos,
          ecommerce_paid: pendingCreate.products.ecommerce,
          ems_paid: pendingCreate.products.ems,
        }),
      });
      setNotice(
        account.invitation === "existing_identity"
          ? `${account.email} already has a WSO2 identity. Product access was added. No second user was created.`
          : account.invitation === "sent"
            ? `WSO2 created ${account.email} and will email the password setup link. No password was stored here.`
            : `${account.email} was recorded without a WSO2 identity because management API credentials are not set.`,
      );
      setCompanyName("");
      setEmail("");
      setProducts(EMPTY_PRODUCTS);
      setPendingCreate(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function confirmChange() {
    if (!pendingChange) return;
    setSaving(true);
    setError("");
    try {
      await api(`/api/admin/customers/${pendingChange.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          fms_access: pendingChange.products.fms,
          pos_access: pendingChange.products.pos,
          ecommerce_access: pendingChange.products.ecommerce,
          ems_access: pendingChange.products.ems,
        }),
      });
      setNotice("Product access was updated. The WSO2 identity was not replaced.");
      setPendingChange(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function setActive(account, active) {
    setSaving(true);
    setError("");
    try {
      await api(`/api/admin/customers/${account.id}`, {
        method: "PATCH",
        body: JSON.stringify({ active }),
      });
      setNotice(active ? "WSO2 account enabled." : "WSO2 account disabled and its sessions were terminated.");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function resetPassword(account) {
    setSaving(true);
    setError("");
    try {
      await api(`/api/admin/customers/${account.id}/password-reset`, { method: "POST" });
      setNotice(`WSO2 will email ${account.email} a password reset. No password was stored here.`);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function flagsOf(account) {
    return {
      fms: account.fms_access,
      pos: account.pos_access,
      ecommerce: account.ecommerce_access,
      ems: account.ems_access,
    };
  }

  return (
    <>
      <div className="page-head">
        <h1>Customers</h1>
        <p className="lede">
          WSO2 keeps one identity per email. KAIONEX keeps the products that identity paid for.
          A password is never saved here. Signed in as {me.display_name}.
        </p>
      </div>
      {identityAdmin === "not_configured" && (
        <p className="banner warn" role="status">
          NOT CONFIGURED. WSO2 user creation, account disable, and password reset need
          ASGARDEO_MANAGEMENT_CLIENT_ID and ASGARDEO_MANAGEMENT_CLIENT_SECRET.
          Until then, no identity is created and no password is stored.
        </p>
      )}
      <form className="company-form" onSubmit={reviewCreate}>
        <h2>New customer</h2>
        <label htmlFor="company-name">Customer name</label>
        <input id="company-name" value={companyName} onChange={(event) => setCompanyName(event.target.value)} required />
        <label htmlFor="company-email">Email</label>
        <input id="company-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        <fieldset>
          <legend>Products paid for</legend>
          {PRODUCTS.map((item) => (
            <label className="check" key={item.id}>
              <input
                type="checkbox"
                checked={products[item.id]}
                onChange={(event) => setProducts((current) => ({ ...current, [item.id]: event.target.checked }))}
              />
              {item.label}
            </label>
          ))}
        </fieldset>
        <button type="submit">Review customer</button>
      </form>
      {pendingCreate && (
        <section className="banner warn" role="alert">
          <strong>Confirm before WSO2 is asked to create or reuse this identity.</strong>
          <span>
            {pendingCreate.companyName} ({pendingCreate.email}) will be allowed to use {productList(pendingCreate.products)}.
          </span>
          <span>If that email already exists in WSO2, only the product access is added.</span>
          <div className="confirm-actions">
            <button type="button" onClick={confirmCreate} disabled={saving}>
              {saving ? "Saving…" : "Create in WSO2"}
            </button>
            <button type="button" className="ghost" onClick={() => setPendingCreate(null)} disabled={saving}>Go back</button>
          </div>
        </section>
      )}
      {pendingChange && (
        <section className="banner warn" role="alert">
          <strong>Confirm this product change.</strong>
          <span>
            {pendingChange.email} will be allowed to use {productList(pendingChange.products)}. The WSO2 user stays the same.
          </span>
          <div className="confirm-actions">
            <button type="button" onClick={confirmChange} disabled={saving}>
              {saving ? "Saving…" : "Save product access"}
            </button>
            <button type="button" className="ghost" onClick={() => setPendingChange(null)} disabled={saving}>Cancel</button>
          </div>
        </section>
      )}
      {notice && <p className="banner ok" role="status">{notice}</p>}
      {error && <p className="banner bad">{error}</p>}
      {!accounts && !error && <p>Loading accounts…</p>}
      {accounts && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Customer</th>
                <th>Email</th>
                <th>Identity</th>
                <th>Status</th>
                <th>Products</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => {
                const draft = drafts[account.id] || flagsOf(account);
                return (
                  <tr key={account.id}>
                    <td>{account.display_name}</td>
                    <td>{account.email}</td>
                    <td>{account.identity === "asgardeo" ? "WSO2" : "Not linked"}</td>
                    <td>
                      <button type="button" className="ghost" disabled={saving} onClick={() => setActive(account, !account.active)}>
                        {account.active ? "Deactivate" : "Activate"}
                      </button>
                      {account.subject && (
                        <button type="button" className="ghost" disabled={saving} onClick={() => resetPassword(account)}>
                          Reset password
                        </button>
                      )}
                    </td>
                    <td>
                      {account.role === "customer" ? (
                        <div className="change-permission">
                          {PRODUCTS.map((item) => (
                            <label className="check" key={item.id}>
                              <input
                                type="checkbox"
                                checked={draft[item.id]}
                                onChange={(event) =>
                                  setDrafts((current) => ({
                                    ...current,
                                    [account.id]: { ...draft, [item.id]: event.target.checked },
                                  }))
                                }
                              />
                              {item.label}
                            </label>
                          ))}
                          <button
                            type="button"
                            className="ghost"
                            disabled={saving || productList(draft) === productList(flagsOf(account))}
                            onClick={() =>
                              setPendingChange({
                                id: account.id,
                                email: account.email,
                                products: draft,
                              })
                            }
                          >
                            Review products
                          </button>
                        </div>
                      ) : (
                        "Administrator"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {audit.length > 0 && (
        <section>
          <h2>Audit</h2>
          <ul>
            {audit.map((item) => (
              <li key={item.id}>
                {item.created_at}: {item.actor_email} {item.action} {item.target_email} ({item.detail})
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
