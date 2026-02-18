import { apiFetch } from "./client";

export async function ping(token) {
  const res = await apiFetch("/api/ping/", {
    token,
    method: "GET",
  });

  return res;
}
