import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";

const NOTICES = {
  saved: "The change was saved after the email code was confirmed.",
};

const ERRORS = {
  invalid_credentials: "That email or password is not correct.",
  account_inactive: "This account is deactivated.",
  otp_missing: "The email code was not confirmed. Nothing was saved.",
  otp_failed: "The change could not be saved.",
  otp_session: "Sign in again, then repeat the change. Nothing was saved.",
  asgardeo_denied: "Email verification was cancelled. Nothing was saved.",
  email_taken: "That email already has a login.",
  invalid_callback: "Email verification could not be confirmed. Nothing was saved.",
  email_verification_required: "Confirm the email code before this access is saved. Nothing was saved.",
};

function useSession() {
  const [me, setMe] = useState(undefined);
  useEffect(() => {
    api("/api/auth/me")
      .then(setMe)
      .catch(() => setMe(null));
  }, []);
  return me;
}

function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("error");
    if (code) setError(ERRORS[code] || "Sign-in could not be completed.");
  }, []);

  async function onSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/company-login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      navigate("/home", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="login-brand">
          <img src="/logo.svg" alt="" />
          <span>Portal</span>
        </div>
        <h1>Sign in</h1>
        <p className="lede">Use the email and password for your company.</p>
        {error && <p className="banner bad">{error}</p>}
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      <section className="login-card company-side">
        <h2>Company side</h2>
        <p className="lede">Use your passkey. You do not type an email and password here.</p>
        <a className="button" href="/api/auth/passkey">Sign in with passkey</a>
      </section>
    </main>
  );
}

const CATALOG = [
  { id: "1", name: "Product 1", blurb: "Operations", href: "/product-1", flag: "product1_access" },
  { id: "2", name: "Product 2", blurb: "Sales", href: "/product-2", flag: "product2_access" },
];

function Launcher({ me, current }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="launcher">
      <button
        type="button"
        className="waffle"
        aria-label="All products"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {Array.from({ length: 9 }, (_, index) => <span key={index} />)}
      </button>
      {open && (
        <>
          <button type="button" className="launcher-backdrop" aria-label="Close products" onClick={() => setOpen(false)} />
          <div className="launcher-menu">
            <p>Your products</p>
            {CATALOG.map((product) => {
              const owned = Boolean(me[product.flag]);
              return (
                <Link
                  key={product.id}
                  to={product.href}
                  className={current === product.id ? "on" : ""}
                  onClick={() => setOpen(false)}
                >
                  <strong>{product.name}</strong>
                  <span>{owned ? "Open and use" : "Not on this login"}</span>
                </Link>
              );
            })}
            <Link to="/account" onClick={() => setOpen(false)}>Account</Link>
            {me.role === "admin" && <Link to="/admin" onClick={() => setOpen(false)}>Companies</Link>}
          </div>
        </>
      )}
    </div>
  );
}

function Shell({ me, current, children }) {
  const here = CATALOG.find((product) => product.id === current);
  return (
    <div className="page">
      <header className="topbar">
        <div className="brand-row">
          <Launcher me={me} current={current} />
          <img className="brand-mark" src="/logo.svg" alt="" />
          <Link to="/home" className="brand">{here ? here.name : me.display_name}</Link>
        </div>
        <nav>
          <Link to="/home">All products</Link>
          <Link to="/account">Account</Link>
          {me.role === "admin" && <Link to="/admin">Companies</Link>}
        </nav>
        <div className="who">
          <span className="who-name">{me.email}</span>
          <a className="ghost" href="/api/auth/logout">Sign out</a>
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}

function Home() {
  const me = useSession();
  if (me === undefined) return <main className="login-wrap"><p>Loading…</p></main>;
  if (!me) return <Navigate to="/" replace />;
  return (
    <Shell me={me}>
      <div className="page-head">
        <h1>Welcome, {me.display_name}</h1>
        <p className="lede">Open a purchased product and use it. The other product stays in the menu on every page.</p>
      </div>
      <section className="cards">
        {CATALOG.map((product) => {
          const owned = Boolean(me[product.flag]);
          return (
            <article className="card" key={product.id}>
              <div className="card-top">
                <h2>{product.name}</h2>
                <span className={owned ? "pill ok" : "pill"}>{owned ? "Ready to use" : "Not purchased"}</span>
              </div>
              <p className="lede">{product.blurb}</p>
              {owned ? (
                <Link className="button" to={product.href}>Use {product.name}</Link>
              ) : (
                <p className="lede">Shown here so you can see it. The seller can add it to this same login.</p>
              )}
            </article>
          );
        })}
      </section>
    </Shell>
  );
}

function Product({ which }) {
  const me = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!me) return;
    api(`/api/product-${which}/summary`)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [me, which]);
  if (me === undefined) return <main className="login-wrap"><p>Loading…</p></main>;
  if (!me) return <Navigate to="/" replace />;
  const other = CATALOG.find((product) => product.id !== which);
  const otherOwned = other ? Boolean(me[other.flag]) : false;
  const openCount = data ? data.records.filter((row) => row.status !== "Closed" && row.status !== "Void").length : 0;
  return (
    <Shell me={me} current={which}>
      <div className="page-head">
        <h1>{data?.application || `Product ${which}`}</h1>
        <p className="lede">{error || data?.description || "Loading…"} Signed in as {me.display_name}.</p>
      </div>
      {data && (
        <>
          <section className="stats">
            <article className="card"><h2>{data.records.length}</h2><p className="lede">Records</p></article>
            <article className="card"><h2>{openCount}</h2><p className="lede">Still active</p></article>
            <article className="card"><h2>{me.display_name}</h2><p className="lede">Company</p></article>
          </section>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Reference</th><th>Item</th><th>Status</th></tr>
              </thead>
              <tbody>
                {data.records.map((row) => (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td>{row.item}</td>
                    <td>{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {other && (
        <article className="card other-product">
          <div className="card-top">
            <h2>{other.name} is also here</h2>
            <span className={otherOwned ? "pill ok" : "pill"}>{otherOwned ? "Ready to use" : "Not purchased"}</span>
          </div>
          {otherOwned ? (
            <Link className="button" to={other.href}>Use {other.name}</Link>
          ) : (
            <p className="lede">This login does not include {other.name} yet. It stays visible so you can see it.</p>
          )}
        </article>
      )}
    </Shell>
  );
}

function Account() {
  const me = useSession();
  if (me === undefined) return <main className="login-wrap"><p>Loading…</p></main>;
  if (!me) return <Navigate to="/" replace />;
  return (
    <Shell me={me}>
      <div className="page-head">
        <h1>Account</h1>
        <p className="lede">One company login. Every purchased product uses it.</p>
      </div>
      <section className="card">
        <dl>
          <div><dt>Company</dt><dd>{me.display_name}</dd></div>
          <div><dt>Email</dt><dd>{me.email}</dd></div>
          <div><dt>Product 1</dt><dd>{me.product1_access ? "Purchased" : "Not purchased"}</dd></div>
          <div><dt>Product 2</dt><dd>{me.product2_access ? "Purchased" : "Not purchased"}</dd></div>
        </dl>
      </section>
    </Shell>
  );
}

function Admin() {
  const me = useSession();
  const [accounts, setAccounts] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [product1, setProduct1] = useState(true);
  const [product2, setProduct2] = useState(false);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() {
    return api("/api/admin/customers")
      .then((body) => setAccounts((body.accounts || []).filter((row) => row.role === "customer")))
      .catch((err) => setError(err.message));
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("notice")) setNotice(NOTICES[params.get("notice")] || "Saved.");
    if (params.get("error")) setError(ERRORS[params.get("error")] || "The email verification did not save the change.");
    if (me && me.role === "admin") load();
  }, [me]);

  async function verify(body) {
    setBusy(true);
    setError("");
    try {
      const result = await api("/api/auth/email-otp", { method: "POST", body: JSON.stringify(body) });
      window.location.assign(result.redirect);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (me === undefined) return <main className="login-wrap"><p>Loading…</p></main>;
  if (!me) return <Navigate to="/" replace />;
  if (me.role !== "admin") return <Navigate to="/home" replace />;

  return (
    <Shell me={me}>
      <div className="page-head">
        <h1>Companies</h1>
        <p className="lede">Give a company the products they bought. Every new company and every product change emails you a code first. Nothing is saved until you enter that code.</p>
      </div>
      {notice && <p className="banner ok">{notice}</p>}
      {error && <p className="banner bad">{error}</p>}

      <form
        className="card form"
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          setNotice("");
          if (!product1 && !product2) {
            setError("Choose at least one product.");
            return;
          }
          setPending({
            kind: "create",
            company_name: companyName.trim(),
            email: email.trim(),
            password,
            product1,
            product2,
          });
        }}
      >
        <h2>New company</h2>
        <label htmlFor="company">Company</label>
        <input id="company" value={companyName} onChange={(event) => setCompanyName(event.target.value)} required />
        <label htmlFor="new-email">Email</label>
        <input id="new-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        <label htmlFor="new-password">Password</label>
        <input id="new-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
        <label className="check"><input type="checkbox" checked={product1} onChange={(event) => setProduct1(event.target.checked)} /> Product 1</label>
        <label className="check"><input type="checkbox" checked={product2} onChange={(event) => setProduct2(event.target.checked)} /> Product 2</label>
        <button type="submit">Review</button>
      </form>

      <section className="stack">
        {accounts.map((account) => (
          <CompanyRow key={account.id} account={account} onReview={setPending} />
        ))}
      </section>

      {pending && (
        <div className="modal-back" role="presentation">
          <section className="card modal" role="dialog" aria-modal="true" aria-labelledby="save-title">
            <h2 id="save-title">{pending.kind === "create" ? "Confirm this company" : "Confirm product access"}</h2>
            <p className="lede">
              {pending.kind === "create"
                ? `${pending.company_name} (${pending.email}) will receive ${[pending.product1 && "Product 1", pending.product2 && "Product 2"].filter(Boolean).join(" and ")}.`
                : `${pending.email} will have ${[pending.product1 && "Product 1", pending.product2 && "Product 2"].filter(Boolean).join(" and ")}.`}
            </p>
            <p className="lede">Nothing is saved yet. Asgardeo emails you a code. Enter that code on the next page. Use the email code, not the passkey.</p>
            <div className="row">
              <button type="button" disabled={busy} onClick={() => verify(pending)}>{busy ? "Sending…" : "Email me a code"}</button>
              <button type="button" className="quiet" disabled={busy} onClick={() => setPending(null)}>Cancel</button>
            </div>
          </section>
        </div>
      )}
    </Shell>
  );
}

function CompanyRow({ account, onReview }) {
  const [product1, setProduct1] = useState(account.product1_access);
  const [product2, setProduct2] = useState(account.product2_access);
  return (
    <article className="card">
      <div className="card-top">
        <h2>{account.display_name}</h2>
        <span className="who-name">{account.email}</span>
      </div>
      <label className="check"><input type="checkbox" checked={product1} onChange={(event) => setProduct1(event.target.checked)} /> Product 1</label>
      <label className="check"><input type="checkbox" checked={product2} onChange={(event) => setProduct2(event.target.checked)} /> Product 2</label>
      <button
        type="button"
        onClick={() => onReview({
          kind: "permission",
          user_id: account.id,
          email: account.email,
          product1,
          product2,
        })}
      >
        Review access
      </button>
    </article>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/home" element={<Home />} />
      <Route path="/product-1" element={<Product which="1" />} />
      <Route path="/product-2" element={<Product which="2" />} />
      <Route path="/account" element={<Account />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
