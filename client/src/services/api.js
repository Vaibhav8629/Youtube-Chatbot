const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

async function request(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not configured.");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.detail || "The backend request failed.");
  }
  return payload;
}

export const api = {
  getHealth: () => request("/health"),
  processVideo: (url) =>
    request("/api/video/process", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  askQuestion: (videoId, question) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ video_id: videoId, question }),
    }),
};
