// ── useWebSocket.js ─────────────────────────────────────────────────────────
import { useEffect, useRef, useState, useCallback } from "react";

export function useWebSocket(url, { onMessage, onConnect, onDisconnect } = {}) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef(null);
  const retryCount = useRef(0);
  const MAX_RETRIES = 5;

  const connect = useCallback(() => {
    if (!url) return;

    console.log("Connecting to WebSocket:", url);

    const ws = new WebSocket(url);
    wsRef.current = ws;

    // Give the connection 15 seconds to establish
    const connectionTimeout = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        console.warn("WebSocket connection timeout, retrying...");
        ws.close();
      }
    }, 15000);

    ws.onopen = () => {
      clearTimeout(connectionTimeout);
      console.log("WebSocket connected");
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
      clearTimeout(connectionTimeout);
      console.log("WebSocket closed:", event.code, event.reason);
      setConnected(false);
      onDisconnect?.();

      // Auto-reconnect for unexpected closes
      if (!event.wasClean && retryCount.current < MAX_RETRIES) {
        retryCount.current++;
        const delay = Math.pow(2, retryCount.current) * 1000;
        console.log(`Reconnecting in ${delay}ms (attempt ${retryCount.current})`);
        reconnectTimer.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = (err) => {
      clearTimeout(connectionTimeout);
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
      console.warn("WebSocket not open, message dropped:", data);
    }
  }, []);

  return { ws: wsRef.current, send, connected };
}


// ── usePRISMSession ───────────────────────────────────────────────────────────
export function usePRISMSession(backendUrl) {
  const createSession = async (userId) => {
    console.log("Creating session at:", backendUrl);

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
    console.log("Session created:", data.session_id);
    return data.session_id;
  };

  const endSession = async (sessionId) => {
    try {
      await fetch(`${backendUrl}/session/${sessionId}`, { method: "DELETE" });
      console.log("Session ended:", sessionId);
    } catch (err) {
      console.warn("Session end error:", err);
    }
  };

  return { createSession, endSession };
}