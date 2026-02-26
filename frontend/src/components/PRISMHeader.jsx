import React from "react";
import { Power, PowerOff, Wifi, WifiOff, Cpu } from "lucide-react";

const STATUS_CONFIG = {
  idle: { label: "Offline", color: "#6b7280", dot: "#6b7280" },
  connecting: { label: "Connecting...", color: "#f59e0b", dot: "#f59e0b" },
  active: { label: "Active", color: "#10b981", dot: "#10b981" },
  error: { label: "Error", color: "#ef4444", dot: "#ef4444" },
};

export default function PRISMHeader({ status, connected, onStart, onStop, sessionId }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  return (
    <header className="prism-header">
      <div className="header-logo">
        <div className="logo-icon">
          <Cpu size={24} />
        </div>
        <div className="logo-text">
          <span className="logo-name">PRISM</span>
          <span className="logo-tagline">Ambient Intelligence Agent</span>
        </div>
      </div>

      <div className="header-status">
        <div className="status-indicator">
          <span
            className={`status-dot ${status === "active" ? "pulse" : ""}`}
            style={{ background: config.dot }}
          />
          <span className="status-label" style={{ color: config.color }}>
            {config.label}
          </span>
        </div>

        {sessionId && (
          <span className="session-id">
            Session: {sessionId.slice(0, 8)}...
          </span>
        )}

        <div className="connection-indicator">
          {connected ? (
            <Wifi size={16} className="connected-icon" />
          ) : (
            <WifiOff size={16} className="disconnected-icon" />
          )}
        </div>
      </div>

      <div className="header-actions">
        {status === "idle" || status === "error" ? (
          <button className="start-btn" onClick={onStart}>
            <Power size={16} />
            Start PRISM
          </button>
        ) : (
          <button className="stop-btn" onClick={onStop}>
            <PowerOff size={16} />
            Stop
          </button>
        )}
      </div>
    </header>
  );
}
