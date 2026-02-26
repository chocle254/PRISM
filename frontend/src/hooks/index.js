// ── useWebSocket.js ─────────────────────────────────────────────────────────
import { useEffect, useRef, useState, useCallback } from "react";

export function useWebSocket(url, { onMessage, onConnect, onDisconnect } = {}) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef(null);
  const MAX_RETRIES = 3;
  const retryCount = useRef(0);

  const connect = useCallback(() => {
    if (!url) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retryCount.current = 0;
      onConnect?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch (err) {
        console.warn("WebSocket message parse error:", err);
      }
    };

    ws.onclose = (event) => {
      setConnected(false);
      onDisconnect?.();

      // Auto-reconnect for unexpected closes
      if (!event.wasClean && retryCount.current < MAX_RETRIES) {
        retryCount.current++;
        const delay = Math.pow(2, retryCount.current) * 1000;
        reconnectTimer.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };
  }, [url, onMessage, onConnect, onDisconnect]);

  useEffect(() => {
    if (url) {
      connect();
    }
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close(1000, "Component unmounted");
    };
  }, [url]);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn("WebSocket not open, message dropped");
    }
  }, []);

  return { ws: wsRef.current, send, connected };
}


// ── usePRISMSession.js ───────────────────────────────────────────────────────
export function usePRISMSession(backendUrl) {
  const createSession = async (userId) => {
    const res = await fetch(`${backendUrl}/session/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Session creation failed: ${err}`);
    }

    const data = await res.json();
    return data.session_id;
  };

  const endSession = async (sessionId) => {
    try {
      await fetch(`${backendUrl}/session/${sessionId}`, { method: "DELETE" });
    } catch (err) {
      console.warn("Session end error:", err);
    }
  };

  return { createSession, endSession };
}
