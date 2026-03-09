import { apiFetch } from "./client";

function extractErrorMessage(defaultMsg, data) {
  return data?.error || data?.detail || defaultMsg;
}

export async function fetchWeeklyStats(token) {
  const res = await apiFetch("/api/stats/weekly", {
    token,
    method: "GET",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok){
    throw new Error(extractErrorMessage("Failed to fetch weekly stats.", data));
  }
  return data;
}

export async function fetchAllTimeStats(token) {
  const res = await apiFetch("/api/stats/all-time/", {
    token,
    method: "GET",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(extractErrorMessage("Failed to fetch all-time stats.", data));
  }
  return data;
}
