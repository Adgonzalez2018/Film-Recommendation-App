import { apiFetch } from "./client";

export async function importLetterboxd({ token, reviews, watchlist, likes }) {
  const fd = new FormData();
  if (reviews) fd.append("reviews", reviews);
  if (watchlist) fd.append("watchlist", watchlist);
  if (likes) fd.append("likes", likes);

  const res = await apiFetch("/api/letterboxd/import/", {
    token,
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    let msg = "Import failed.";
    try {
      const data = await res.json();
      msg = data?.error || msg;
    } catch {}
    throw new Error(msg);
  }

  return res.json();
}
