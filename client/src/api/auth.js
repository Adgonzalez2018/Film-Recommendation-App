import { apiFetch } from "./client";

export async function ping(token) {
  const res = await apiFetch("/api/ping/", {
    token,
    method: "GET",
  });

  return res;
}

export async function loginAction({ email, password }) {
  const res = await apiFetch("/api/login/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(extractErrorMessage("Login failed.", data));
  return data; // expect { access_token, ... }
}

export async function registerAction({ first_name, email, password }) {
  const res = await apiFetch("/api/register/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ first_name, email, password }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(extractErrorMessage("Registration failed.", data));
  return data;
}