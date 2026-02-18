export async function apiFetch(path, { token, headers, ...opts } = {}) {
  const h = new Headers(headers || {});
  if (token) h.set("Authorization", `Bearer ${token}`);

  const res = await fetch(path, { ...opts, headers: h });
  return res;
}
