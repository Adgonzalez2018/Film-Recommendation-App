import { apiFetch } from "./client";

export async function ping(token) {
  const res = await apiFetch("/api/ping/", {
    token,
    method: "GET",
  });

  return res;
}

export function extractErrorMessage(fallback, data) {
  if (!data) return fallback;
  if (typeof data === "string") return data;

  if (typeof data === "object") {
    if (typeof data.error === "string" && data.error.trim()) return data.error.trim();
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail.trim();
    for (const v of Object.values(data)) {
      if (Array.isArray(v) && typeof v[0] === "string") return v[0];
      if (typeof v === "string" && v.trim()) return v.trim();
    }
  }
  return fallback;
}

export async function loginAction({ email, password }) {
  let res;
  try {
    res = await apiFetch("/api/login/", {
      method: "POST",
      body: { email, password }, // <-- pass object, apiFetch will JSON stringify
      retryOn401: false,
      redirectOnAuthFailure: false,
    });
  } catch (e) {
    throw new Error("Network error: could not reach backend (/api/login/). Check dev proxy + backend server.");
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(extractErrorMessage("Login failed.", data));
  return data;
}

export async function registerAction({ email, password, first_name = "" }) {
  const res = await apiFetch("/api/register/",{
    method: "POST",
    body: { email, password, first_name},
    retryOn401: false,
    redirectOnAuthFailure: false,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(extractErrorMessage("Registration failed.", data));
  return data;

}