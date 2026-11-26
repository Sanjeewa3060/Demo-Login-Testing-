import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

const NAMES = {
  fms: "FMS",
  pos: "POS",
};

export default function Product({ kind }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    api(`/api/${kind}/summary`)
      .then((body) => {
        if (live) setData(body);
      })
      .catch((err) => {
        if (!live) return;
        if (err.status === 401) {
          navigate("/", { replace: true });
          return;
        }
        setError(err);
      });
    return () => {
      live = false;
    };
  }, [kind, navigate]);

  const columns = data?.records?.[0] ? Object.keys(data.records[0]) : [];

  return (
    <>
      <p className="back"><Link to="/portal">Back to portal</Link></p>
      <div className="page-head">
        <h1>{data?.application || NAMES[kind]}</h1>
        <p className="lede">
          {data?.description || (error ? "The server did not return any records." : "Waiting for the API.")}
        </p>
      </div>
      {error && (
        <section className="banner bad" role="alert">
          <strong>Access refused by the API.</strong>
          <span>{error.message}{error.code ? ` (${error.code})` : ""}</span>
          <span>No records are shown unless the server returns them.</span>
        </section>
      )}
      {!error && !data && <p>Loading records…</p>}
      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.records.map((record) => (
                <tr key={record.id}>
                  {columns.map((column) => (
                    <td key={column}>{record[column]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
