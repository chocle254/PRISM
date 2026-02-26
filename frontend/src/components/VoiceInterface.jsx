import React, { useState, useRef, useEffect, useCallback } from "react";
import { Mic, MicOff, Send, StopCircle, Volume2 } from "lucide-react";

const EMOTION_COLORS = {
  neutral: "#6366f1",
  excited: "#f59e0b",
  calm: "#10b981",
  authoritative: "#3b82f6",
};

export default function VoiceInterface({
  connected,
  isListening,
  onListeningChange,
  onAudioChunk,
  onInterrupt,
  onTextInput,
  messages,
  emotion = "neutral",
}) {
  const [textInput, setTextInput] = useState("");
  const [audioLevel, setAudioLevel] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const animFrameRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Microphone ───────────────────────────────────────────────────────────────
  const startListening = useCallback(async () => {
    if (!connected) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // Audio level visualization
      audioContextRef.current = new AudioContext();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);

      const updateLevel = () => {
        const data = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        setAudioLevel(Math.min(100, avg * 2));
        animFrameRef.current = requestAnimationFrame(updateLevel);
      };
      updateLevel();

      // MediaRecorder for streaming chunks
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      mediaRecorderRef.current = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) onAudioChunk(e.data);
      };

      // Send 500ms chunks
      mediaRecorderRef.current.start(500);
      onListeningChange(true);
    } catch (err) {
      console.error("Microphone error:", err);
    }
  }, [connected, onAudioChunk, onListeningChange]);

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current?.state !== "inactive") {
      mediaRecorderRef.current?.stop();
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioContextRef.current?.close();
    cancelAnimationFrame(animFrameRef.current);
    setAudioLevel(0);
    onListeningChange(false);
  }, [onListeningChange]);

  const toggleListening = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  const handleInterruptClick = () => {
    stopListening();
    onInterrupt("Stop and wait for new instructions");
  };

  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (textInput.trim()) {
      onTextInput(textInput.trim());
      setTextInput("");
    }
  };

  const accentColor = EMOTION_COLORS[emotion] || EMOTION_COLORS.neutral;

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="voice-interface">
      <div className="voice-header">
        <span className="voice-title">
          <Volume2 size={16} />
          Voice Channel
        </span>
        {isListening && (
          <span className="listening-badge">
            <span className="pulse-dot" />
            Listening
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="messages-container">
        {messages.length === 0 && (
          <div className="empty-messages">
            <p>Start talking to PRISM or type below</p>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`message message-${msg.role}`}>
            <div className="message-label">
              {msg.role === "user" ? "You" : msg.role === "assistant" ? "PRISM" : "System"}
            </div>
            <div className="message-text">{msg.text}</div>
            <div className="message-time">
              {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Audio Visualizer */}
      {isListening && (
        <div className="audio-visualizer">
          {Array.from({ length: 20 }).map((_, i) => (
            <div
              key={i}
              className="audio-bar"
              style={{
                height: `${Math.max(4, (audioLevel * (0.5 + Math.sin(i) * 0.5)))}px`,
                background: accentColor,
                opacity: 0.6 + Math.random() * 0.4,
              }}
            />
          ))}
        </div>
      )}

      {/* Controls */}
      <div className="voice-controls">
        <button
          className={`mic-btn ${isListening ? "mic-active" : ""} ${!connected ? "disabled" : ""}`}
          onClick={toggleListening}
          disabled={!connected}
          style={{ "--accent": accentColor }}
          title={isListening ? "Stop listening" : "Start listening"}
        >
          {isListening ? <MicOff size={20} /> : <Mic size={20} />}
        </button>

        {isListening && (
          <button
            className="interrupt-btn"
            onClick={handleInterruptClick}
            title="Interrupt PRISM"
          >
            <StopCircle size={20} />
            Interrupt
          </button>
        )}

        <form className="text-input-form" onSubmit={handleTextSubmit}>
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder={connected ? "Or type here..." : "Connect first..."}
            disabled={!connected}
            className="text-input"
          />
          <button
            type="submit"
            disabled={!connected || !textInput.trim()}
            className="send-btn"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
