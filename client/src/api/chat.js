import { apiFetch } from "./client";

function extractErrorMessage(defaultMsg, data) {
  return data?.error || data?.detail || defaultMsg;
}

export async function sendChatMessage(message, token) {
    const res = await apiFetch("/api/chat/recommend/",{
        token,
        method: "POST",
        body: { message },
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok){
        throw new Error(extractErrorMessage("Chat request failed.", data));
    }
    return data;
}

export async function fetchFilmBank(token, page = 1, pageSize = 20){
    const res = await apiFetch(`/api/film-bank/?page=${page}&page_size=${pageSize}`,{
        token,
        method:"GET",
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(extractErrorMessage("Failed to load film bank.", data));
    }

    return data;
}

export async function dismissFilmBankMovie(movieId, token){
    const res = await apiFetch(`/api/film-bank/${movieId}/`,{
        token,
        method: "DELETE",
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok){
        throw new Error(extractErrorMessage("Failed to remove film.", data));
    }

    return data;
}

export async function submitFilmBankFeedback(movieId, token, feedback){
    const res = await apiFetch(`/api/film-bank/${movieId}/feedback/`, {
        token,
        method: "POST",
        body: {
            rating: feedback.rating,
            watched: feedback.watched,
            text: feedback.text ?? "",
        },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(extractErrorMessage("Failed to submit feedback.", data));
    return data;
}