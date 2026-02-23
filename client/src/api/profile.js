import { apiFetch } from "./client";

function extractErrorMessage(defaultMsg, data) {
  return data?.error || data?.detail || defaultMsg;
}

export async function fetchProfile(token) {
  const res = await apiFetch("/api/profile/", {
    token,
    method: "GET",
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(extractErrorMessage("Failed to load profile.", data));

  return data;
}

export async function saveProfile(payload, token) {
  const res = await apiFetch("/api/profile/", {
    token,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(extractErrorMessage("Save failed.", data));

  return data;
}
