import React, { useState, useEffect, useRef, useCallback } from "react";
import VoiceInterface from "./components/VoiceInterface";
import ScreenShare from "./components/ScreenShare";
import CreativeOutput from "./components/CreativeOutput";
import ActionFeed from "./components/ActionFeed";
import PRISMHeader from "./components/PRISMHeader";
import { usePRISMSession, useWebSocket } from "./hooks";
import "./App.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000";

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | connecting | active | error
  const [messages, setMessages] = useState([]);
  const [creativeChunks, setCreativeChunks] = useState([]);
  const [actions, setActions] = useState([]);
  const [screenSharing, setScreenSharing] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [currentEmotion, setCurrentEmotion] = useState("neutral");

  const { createSession, endSession } = usePRISMSession(BACKEND_URL);

  // ── Main WebSocket ───────────────────────────────────────────────────────────
  const { ws, send: wsSend, connected } = useWebSocket(
    sessionId ? `${WS_URL}/ws/${sessionId}` : null,
    {
      onMessage: handleWebSocketMessage,
      onConnect: () => setStatus("active"),
      onDisconnect: () => setStatus("idle"),
    }
  );

  // ── Action WebSocket ─────────────────────────────────────────────────────────
  const { ws: actionWs, send: actionSend } = useWebSocket(
    sessionId ? `${WS_URL}/ws/actions/${sessionId}` : null,
    { onMessage: handleActionMessage }
  );

  // ── Message Handler ──────────────────────────────────────────────────────────
  function handleWebSocketMessage(data) {
    switch (data.type) {
      case "voice_response":
        addMessage("assistant", data.text, data.audio, data.emotion);
        if (data.audio) playAudio(data.audio);
        break;

      case "creative_chunk":
        setCreativeChunks((prev) => [...prev, data]);
        break;

      case "action_plan":
        setActions(data.plan?.steps || []);
        break;

      case "screen_analysis":
        // Silently update screen context
        break;

      case "status":
        if (data.status === "interrupted") {
          setIsListening(false);
        }
        break;

      case "error":
        console.error("PRISM error:", data.message);
        addMessage("system", `⚠️ ${data.message}`);
        break;

      default:
        break;
    }
  }

  function handleActionMessage(data) {
    if (data.type === "action") {
      executeAction(data).then((result) => {
        actionSend({ type: "action_result", ...result });
      });
    }
  }

  // ── Session Management ───────────────────────────────────────────────────────
  async function startSession() {
    setStatus("connecting");
    try {
      const id = await createSession("user_" + Date.now());
      setSessionId(id);
      addMessage("system", "✨ PRISM is ready. Say something or start screen sharing!");
    } catch (err) {
      setStatus("error");
      console.error("Session creation failed:", err);
    }
  }

  async function stopSession() {
    if (sessionId) {
      await endSession(sessionId);
      setSessionId(null);
      setStatus("idle");
      setMessages([]);
      setCreativeChunks([]);
      setActions([]);
    }
  }

  // ── Audio Handling ───────────────────────────────────────────────────────────
  function handleAudioChunk(audioBlob) {
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = reader.result.split(",")[1];
      wsSend({ type: "audio_chunk", data: base64 });
    };
    reader.readAsDataURL(audioBlob);
  }

  function handleInterrupt(text = "") {
    wsSend({ type: "interrupt", text });
    setIsListening(false);
  }

  function playAudio(base64Audio) {
    try {
      const bytes = atob(base64Audio);
      const buffer = new ArrayBuffer(bytes.length);
      const view = new Uint8Array(buffer);
      for (let i = 0; i < bytes.length; i++) view[i] = bytes.charCodeAt(i);
      const blob = new Blob([buffer], { type: "audio/pcm" });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().catch(console.warn);
    } catch (err) {
      console.warn("Audio playback error:", err);
    }
  }

  // ── Screen Share ─────────────────────────────────────────────────────────────
  function handleScreenFrame(frameBase64) {
    wsSend({ type: "screen_frame", data: frameBase64 });
  }

  // ── UI Action Execution ──────────────────────────────────────────────────────
  async function executeAction(action) {
    const { action_id, action_type, target, value } = action;
    try {
      switch (action_type) {
        case "navigate":
          window.open(target, "_blank");
          return { action_id, success: true, result: "Opened in new tab" };

        case "click":
          const el = document.querySelector(target);
          if (el) {
            el.click();
            return { action_id, success: true };
          }
          return { action_id, success: false, error: "Element not found" };

        case "type":
          const input = document.querySelector(target);
          if (input) {
            input.value = value;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            return { action_id, success: true };
          }
          return { action_id, success: false, error: "Input not found" };

        case "scroll":
          window.scrollBy(0, parseInt(value) || 300);
          return { action_id, success: true };

        default:
          return { action_id, success: false, error: `Unknown action: ${action_type}` };
      }
    } catch (err) {
      return { action_id, success: false, error: err.message };
    }
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────
  function addMessage(role, text, audio = null, emotion = "neutral") {
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role, text, audio, emotion, timestamp: new Date() },
    ]);
  }

  function handleTextInput(text) {
    if (!text.trim() || !connected) return;
    addMessage("user", text);
    wsSend({ type: "text_input", text });
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="prism-app">
      <PRISMHeader
        status={status}
        connected={connected}
        onStart={startSession}
        onStop={stopSession}
        sessionId={sessionId}
      />

      <div className="prism-workspace">
        {/* Left Panel: Voice + Screen */}
        <div className="prism-left-panel">
          <VoiceInterface
            connected={connected}
            isListening={isListening}
            onListeningChange={setIsListening}
            onAudioChunk={handleAudioChunk}
            onInterrupt={handleInterrupt}
            onTextInput={handleTextInput}
            messages={messages}
            emotion={currentEmotion}
          />

          <ScreenShare
            active={screenSharing}
            onToggle={() => setScreenSharing((s) => !s)}
            onFrame={handleScreenFrame}
            connected={connected}
          />
        </div>

        {/* Center: Creative Output Stream */}
        <div className="prism-center-panel">
          <CreativeOutput chunks={creativeChunks} />
        </div>

        {/* Right Panel: Action Feed */}
        <div className="prism-right-panel">
          <ActionFeed actions={actions} />
        </div>
      </div>
    </div>
  );
}
