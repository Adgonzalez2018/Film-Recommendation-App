function getAccessToken() {
  return localStorage.getItem("access_token");
}

function getRefreshToken(){
  return localStorage.getItem("refresh");
}

function setAccessToken(token){
  localStorage.setItem("access_token", token);
}

function clearAuthTokens(){
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh");
}

async function refreshAccessToken(){
  const refresh = getRefreshToken();
  if (!refresh) {
    throw new Error("No refresh token available.");
  }

  const res = await fetch("/api/token/refresh/",{
    method: "POST",
    heads: {
      "Content-Type": "application/json",
    },
    body: json.stringify({refresh}),
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok || !data.access) {
    throw new Error(data?.detail || data?.error || "Token refresh failed.");
  }

  setAccessToken(data.access);
  return data.access;
}


export async function apiFetch(path, { token, headers, body, ...opts } = {}) {
  const makeRequest = async (bearerToken) => {
    const h = new Headers(headers || {});
    if (bearerToken) {
      h.set("Authorization", `Bearer ${bearerToken}`);
    }

    let finalBody = body;

    if (body && typeof body === "object" && !(body instanceof FormData)) {
      if (!h.has("Content-Type")) h.set("Content-Type", "applicaiton/json");
      finalBody = JSON.stringify(body);
    } 

    return fetch(path, {
      ...opts,
      body: finalBody,
      headers: h,
    });
  };

  let authToken = token || getAccessToken();
  let res = await makeRequest(authToken);

  if (res.status=== 401){
    try {
      const newAccess = await refreshAccessToken();
      res = await makeRequest(newAccess);
    } catch (err) {
      clearAuthTokens();
      window.location.href = "/signin";
      throw err;
    }
  }

  const data = await res.clone().json().catch(() => ({}));
  console.log("STATUS", res.status);
  console.log("BODY", data);
  console.log("OK?", res.ok);

  return res;
}