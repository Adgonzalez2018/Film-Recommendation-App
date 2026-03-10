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

  if (!res.ok) {
    let msg = "Import failed.";
    try {
      const data = await res.json();
      msg = extractErrorMessage(msg,data);
    } catch {}
    throw new Error(msg);
  }

  return res.json();
}

export async function submitCSVImport(files, accessToken){
  return importLetterboxd(
    {
      token: accessToken,
      watched: files?.watched || null,
      reviews: files?.reviews || null,
      watchlist: files?.watchlist || null,
      likes: files?.likes || null,
    }
  );
}

export async function submitRSSSync(rssInput, accessToken){
  const res = await apiFetch("/api/import/rss/",{
    token: accessToken,
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({rss: (rssInput || "").trim()}),
  });

  if (!res.ok){
    let msg = "RSS Sync Failed.";
    try {
      const data = await res.json();
      msg = extractErrorMessage(msg, data);
    } catch {}
    throw new Error(msg);
  }

  return res.json();
}

export async function getOnboardingStatus(){
  return apiFetch("/api/onboarding-status/",{
    method: "GET",
  });
}