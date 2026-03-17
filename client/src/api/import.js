import { apiFetch } from "./client";

export const CSV_FILES = [
  { key: "watched", label: "watched.csv", hint: "All of your watched films", icon: "🎬" },
  { key: "reviews", label: "reviews.csv", hint: "Your film ratings & written reviews", icon: "🎬" },
  { key: "watchlist", label: "watchlist.csv", hint: "Films you want to watch", icon: "📋" },
  { key: "likes", label: "films.csv", hint: "Your liked films", icon: "❤️" },
];

function extractErrorMessage(defaultMsg, data) {
  return data?.error || data?.detail || defaultMsg;
}

export async function importLetterboxd({ token, watched, reviews, watchlist, likes }) {
  const fd = new FormData();
  if (watched) fd.append("watched", watched);
  if (reviews) fd.append("reviews", reviews);
  if (watchlist) fd.append("watchlist", watchlist);
  if (likes) fd.append("likes", likes);

  const res = await apiFetch("/api/import/csv/", {
    token,
    method: "POST",
    body: fd,
  });

  let data = {};
  try {
    data = await res.json();
  } catch {}

  if (!res.ok) {
    throw new Error(extractErrorMessage("Import failed.", data));
  }

  return data;
}

export async function submitCSVImport(files, accessToken) {
  return importLetterboxd({
    token: accessToken,
    watched: files?.watched || null,
    reviews: files?.reviews || null,
    watchlist: files?.watchlist || null,
    likes: files?.likes || null,
  });
}

export async function submitRSSSync(rssInput, accessToken) {
  const res = await apiFetch("/api/import/rss/", {
    token: accessToken,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rss: (rssInput || "").trim() }),
  });

  let data = {};
  try {
    data = await res.json();
  } catch {}

  if (!res.ok) {
    throw new Error(extractErrorMessage("RSS sync failed.", data));
  }

  return data;
}

export async function fetchImportBatch(batchId, token) {
  const res = await apiFetch(`/api/import-batches/${batchId}/`, {
    token,
    method: "GET",
  });

  let data = {};
  try {
    data = await res.json();
  } catch {}

  if (!res.ok) {
    throw new Error(extractErrorMessage("Failed to fetch import batch.", data));
  }

  return data;
}

export async function pollImportBatch(batchId, token, options = {}) {
  const intervalMs = options.intervalMs ?? 2000;
  const timeoutMs = options.timeoutMs ?? 300000;
  const startedAt = Date.now();

  while (true) {
    const batch = await fetchImportBatch(batchId, token);

    if (batch.status === "completed" || batch.status === "failed") {
      return batch;
    }

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error("Import is still processing. Please refresh and check again.");
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export async function getOnboardingStatus() {
  return apiFetch("/api/onboarding-status/", {
    method: "GET",
  });
}

export async function markOnboardingSkipped(accessToken) {
  const res = await apiFetch("/api/onboarding/skip/", {
    token: accessToken,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ skipped: true }),
  });

  if (!res.ok) {
    let msg = "Failed to skip onboarding.";
    try {
      const data = await res.json();
      msg = extractErrorMessage(msg, data);
    } catch {}
    throw new Error(msg);
  }

  return res.json();
}