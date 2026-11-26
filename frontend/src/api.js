export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const detail = data && data.detail;
    const message =
      (detail && typeof detail === "object" && detail.message) ||
      (typeof detail === "string" && detail) ||
      "The request failed.";
    const error = new Error(message);
    error.status = response.status;
    error.code = detail && typeof detail === "object" ? detail.code : undefined;
    throw error;
  }

  return data;
}
