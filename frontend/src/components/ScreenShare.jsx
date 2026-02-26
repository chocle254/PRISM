import React, { useState, useRef, useEffect, useCallback } from "react";
import { Monitor, MonitorOff, Eye } from "lucide-react";

const FRAME_INTERVAL_MS = 1000; // Send a frame every 1 second

export default function ScreenShare({ active, onToggle, onFrame, connected }) {
  const [stream, setStream] = useState(null);
  const [frameCount, setFrameCount] = useState(0);
  const [previewVisible, setPreviewVisible] = useState(false);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const intervalRef = useRef(null);

  // ── Start / Stop Screen Share ────────────────────────────────────────────────
  useEffect(() => {
    if (active && connected) {
      startScreenShare();
    } else {
      stopScreenShare();
    }
    return () => stopScreenShare();
  }, [active, connected]);

  const startScreenShare = async () => {
    try {
      const mediaStream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          mediaSource: "screen",
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 5 },
        },
        audio: false,
      });

      setStream(mediaStream);

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        await videoRef.current.play();
      }

      // Listen for user stopping share via browser UI
      mediaStream.getVideoTracks()[0].onended = () => {
        onToggle(); // Signal parent to update state
      };

      // Start frame capture loop
      intervalRef.current = setInterval(() => captureFrame(), FRAME_INTERVAL_MS);
    } catch (err) {
      console.error("Screen share error:", err);
      if (err.name !== "NotAllowedError") {
        onToggle(); // Reset active state on error
      }
    }
  };

  const stopScreenShare = () => {
    clearInterval(intervalRef.current);
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      setStream(null);
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setFrameCount(0);
  };

  // ── Frame Capture ────────────────────────────────────────────────────────────
  const captureFrame = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;

    if (video.videoWidth === 0) return;

    canvas.width = Math.min(video.videoWidth, 1280);
    canvas.height = Math.min(video.videoHeight, 720);

    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Convert to JPEG base64 (lower quality for efficiency)
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    const base64 = dataUrl.split(",")[1];

    if (base64 && onFrame) {
      onFrame(base64);
      setFrameCount((n) => n + 1);
    }
  }, [onFrame]);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="screen-share">
      <div className="screen-share-header">
        <span className="screen-title">
          <Monitor size={16} />
          Screen Sharing
        </span>
        {active && stream && (
          <span className="frame-counter">
            {frameCount} frames sent
          </span>
        )}
      </div>

      <div className="screen-controls">
        <button
          className={`screen-btn ${active ? "screen-active" : ""}`}
          onClick={onToggle}
          disabled={!connected}
          title={active ? "Stop sharing" : "Share your screen"}
        >
          {active ? (
            <>
              <MonitorOff size={16} />
              Stop Sharing
            </>
          ) : (
            <>
              <Monitor size={16} />
              Share Screen
            </>
          )}
        </button>

        {active && stream && (
          <button
            className="preview-btn"
            onClick={() => setPreviewVisible((v) => !v)}
            title="Toggle preview"
          >
            <Eye size={16} />
            {previewVisible ? "Hide" : "Preview"}
          </button>
        )}
      </div>

      {/* Hidden video element for capture */}
      <video ref={videoRef} style={{ display: "none" }} muted playsInline />
      <canvas ref={canvasRef} style={{ display: "none" }} />

      {/* Preview */}
      {active && stream && previewVisible && (
        <div className="screen-preview">
          <p className="preview-label">PRISM can see this</p>
          <video
            srcObject={stream}
            autoPlay
            muted
            playsInline
            className="preview-video"
          />
        </div>
      )}

      {!active && (
        <p className="screen-hint">
          Share your screen so PRISM can see your apps and help you navigate them.
        </p>
      )}
    </div>
  );
}
