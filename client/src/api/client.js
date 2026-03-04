export async function apiFetch(path, { token, headers, body, ...opts } = {}) {
  const h = new Headers(headers || {});

  if (token) h.set("Authorization", `Bearer ${token}`);

  let finalBody = body;

  // if body is a plain obj, JSON encode it
  if (body && typeof body === "object" && !(body instanceof FormData)){
    if (!h.has("Content-Type")) h.set("Content-Type", "application/json");
    finalBody = JSON.stringify(body);
  }

  const res = await fetch(path, { ...opts, body: finalBody, headers: h });
  return res;
}
