import { apiFetch } from "./client";

export async function fetchStats(token) {
  const res = await apiFetch("/api/stats/", {
    token,
    method: "GET",
  });

  if (!res.ok) {
    throw new Error("Failed to fetch stats");
  }

  return res.json();
}
