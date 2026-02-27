import { apiFetch } from "./client";

export async function fetchWeeklyStats(token) {
  const res = await apiFetch("/api/stats/", {
    token,
    method: "GET",
  });

  if (!res.ok) {
    throw new Error("Failed to fetch stats");
  }

  return res.json();
}

export async function fetchAllTimeStats(token) {
  const res = await apiFetch("/api/stats/all-time", {
    token,
    method: "GET",
  });

  if (!res.ok) {
    throw new Error("Failed to fetch stats");
  }

  return res.json();
}
