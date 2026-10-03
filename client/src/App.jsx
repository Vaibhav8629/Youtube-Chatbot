import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./services/api";

const suggestions = [
  "What are the main ideas in this video?",
  "Summarize the important points.",
  "Explain this in simple terms.",
];

function getVideoTitle(url) {
  try {
    const parsed = new URL(url);
    return parsed.searchParams.get("v") || parsed.pathname.split("/").filter(Boolean).pop() || "YouTube video";
  } catch {
    return "YouTube video";
  }
}

function App() {
  const [theme, setTheme] = useState(() => {
    const savedTheme = localStorage.getItem("context-theme");
    if (savedTheme) return savedTheme;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  });
  const [state, setState] = useState("EMPTY");
  const [url, setUrl] = useState("");
  const [video, setVideo] = useState(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState("");
  const [isAsking, setIsAsking] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("context-theme", theme);
  }, [theme]);

  async function processVideo(event) {
    event.preventDefault();
    if (!url.trim() || state === "PROCESSING") return;
    setState("PROCESSING");
    setError("");
    try {
      const result = await api.processVideo(url.trim());
      setVideo({ ...result, title: getVideoTitle(url.trim()), url: url.trim() });
      setState("READY");
    } catch (requestError) {
      setError(requestError.message);
      setState("ERROR");
    }
  }

  async function askQuestion(event, suggestedQuestion = question) {
    event?.preventDefault();
    const text = suggestedQuestion.trim();
    if (!text || !video || isAsking) return;
    setQuestion("");
    setMessages((current) => [...current, { role: "user", text }]);
    setState("CHATTING");
    setIsAsking(true);
    try {
      const result = await api.askQuestion(video.video_id, text);
      setMessages((current) => [
        ...current,
        { role: "assistant", text: result.answer, sources: result.sources || [] },
      ]);
    } catch (requestError) {
      setError(requestError.message);
      setMessages((current) => [...current, { role: "error", text: requestError.message }]);
    } finally {
      setIsAsking(false);
    }
  }

  function reset() {
    setState("EMPTY");
    setUrl("");
    setVideo(null);
    setMessages([]);
    setQuestion("");
    setError("");
  }

  const hasChat = state === "READY" || state === "CHATTING";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">✦</span><span>context</span></div>
        <div className="header-actions">
          <button className="theme-toggle" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            <span>{theme === "dark" ? "☼" : "☾"}</span>
          </button>
          {hasChat && <button className="new-video" onClick={reset}>＋ New video</button>}
        </div>
      </header>

      <section className={`workspace ${hasChat ? "workspace-ready" : ""}`}>
        <motion.div layout className="intro">
          <p className="eyebrow">YOUTUBE RAG</p>
          <h1>{hasChat ? "Ask anything about your video." : "Turn a video into a conversation."}</h1>
          <p className="subheading">
            {hasChat ? "Answers are grounded in the transcript you provided." : "Paste a YouTube link and explore its ideas with AI."}
          </p>
        </motion.div>

        <AnimatePresence mode="wait" initial={false}>
          {state === "EMPTY" && (
            <motion.form key="empty" className="url-card" onSubmit={processVideo}
              initial={{ opacity: 0, y: 18, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.98 }} transition={{ duration: 0.4 }}>
              <label htmlFor="video-url">YouTube URL</label>
              <div className="url-row">
                <input id="video-url" value={url} onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://youtube.com/watch?v=..." autoComplete="off" />
                <button className="primary-button" type="submit" disabled={!url.trim()}>Analyze video <span>↗</span></button>
              </div>
              <p className="hint">We’ll read the transcript and keep your video context throughout the chat.</p>
            </motion.form>
          )}

          {state === "PROCESSING" && (
            <motion.div key="processing" className="status-card" initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }}>
              <div className="loader" /><div><strong>Analyzing your video...</strong><p>Finding the transcript and building your context.</p></div>
            </motion.div>
          )}

          {state === "ERROR" && (
            <motion.div key="error" className="status-card error-card" initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <div className="error-icon">!</div><div><strong>We couldn’t analyze that video.</strong><p>{error}</p><button className="text-button" onClick={() => setState("EMPTY")}>Try another URL</button></div>
            </motion.div>
          )}

          {hasChat && (
            <motion.div key="chat" className="chat-card" layout initial={{ opacity: 0, y: 25, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.45 }}>
              <div className="video-context"><div className="youtube-icon">▶</div><div><strong>{video.title}</strong><span>{video.chunks} transcript chunks · Ready</span></div><span className="ready-dot" /></div>
              <div className="conversation">
                {messages.length === 0 && <motion.div className="empty-chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><span className="sparkle">✦</span><h2>What would you like to know?</h2><p>Ask a question or choose a starting point below.</p><div className="suggestions">{suggestions.map((item) => <button key={item} onClick={() => askQuestion(null, item)}>{item}<span>→</span></button>)}</div></motion.div>}
                {messages.map((message, index) => <div className={`message ${message.role}`} key={`${message.role}-${index}`}><span className="message-label">{message.role === "user" ? "YOU" : "CONTEXT"}</span><p>{message.text}</p>{message.sources?.length > 0 && <small>{message.sources.length} transcript source{message.sources.length === 1 ? "" : "s"}</small>}</div>)}
                {isAsking && <div className="typing"><span /><span /><span /></div>}
              </div>
              <form className="composer" onSubmit={askQuestion}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question about this video..." disabled={isAsking} /><button type="submit" disabled={!question.trim() || isAsking}>↑</button></form>
            </motion.div>
          )}
        </AnimatePresence>
      </section>
      <footer><span>Answers grounded in your transcript</span><span className="footer-status"><i /> System operational</span></footer>
    </main>
  );
}

export default App;
