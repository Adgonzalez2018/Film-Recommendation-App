import { apiFetch } from "./client";

function extractError(defaultMsg, data){
    return data?.error || data?.detail || defaultMsg;
}

export async function apiJson(path, {token, method = "GET", headers, body} = {}){
    const h = new Headers(headers || {});
    let finalBody = body;

    // auto JSON encode
    if (body && typeof body === "object" && !(body instanceof FormData)){
        if (!h.has("Content_Type")) h.set("Content-Type", "application/json");
        finalBody = JSON.stringify(body);
    }

    const res = await apiFetch(path, {
        token,
        method,
        headers: Object.fromEntries(h.entries()),
        body: finalBody,
    });
    
    const data = await res.json().catch(() => ({}));

    // centralized auth failure behavior
    if (res.status === 401 || res.status === 403){
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("userId");
        localStorage.removeItem("username");
        throw new Error("Session expired please sign in again.");
    }

    if (!res.ok) throw new Error(extractError("Request failed.", data));
    return data;
}