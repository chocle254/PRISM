import React, { useRef, useEffect } from "react";
import { Sparkles, Image, Lightbulb, Play, Code } from "lucide-react";

export default function CreativeOutput({ chunks }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chunks]);

  if (chunks.length === 0) {
    return (
      <div className="creative-output creative-empty">
        <div className="creative-empty-icon">
          <Sparkles size={48} strokeWidth={1} />
        </div>
        <h3>Creative Stream</h3>
        <p>PRISM will generate rich, mixed-media content here — narration, images, plans, and insights all woven together.</p>
      </div>
    );
  }

  return (
    <div className="creative-output">
      <div className="creative-header">
        <Sparkles size={16} />
        <span>Creative Stream</span>
        <span className="chunk-count">{chunks.length} items</span>
      </div>

      <div className="creative-stream">
        {chunks.map((chunk, index) => (
          <CreativeChunk key={index} chunk={chunk} index={index} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function CreativeChunk({ chunk, index }) {
  const animStyle = {
    animationDelay: `${index * 0.05}s`,
  };

  switch (chunk.type) {
    case "text":
      return (
        <div className="chunk chunk-text" style={animStyle}>
          <p>{chunk.content}</p>
        </div>
      );

    case "image":
      return (
        <div className="chunk chunk-image" style={animStyle}>
          <div className="chunk-label">
            <Image size={14} />
            Generated Visual
          </div>
          {chunk.image_data ? (
            <img
              src={`data:image/png;base64,${chunk.image_data}`}
              alt={chunk.prompt}
              className="generated-image"
            />
          ) : (
            <div className="image-placeholder">
              <Image size={32} strokeWidth={1} />
              <span className="image-prompt-text">{chunk.prompt}</span>
              <span className="generating-badge">Generating...</span>
            </div>
          )}
        </div>
      );

    case "data":
      return (
        <div className="chunk chunk-data" style={animStyle}>
          <div className="chunk-label">
            <Code size={14} />
            {getDataTypeLabel(chunk.content)}
          </div>
          <DataRenderer data={chunk.content} />
        </div>
      );

    case "action":
      const action = typeof chunk.content === "string"
        ? { description: chunk.content }
        : chunk.content;
      return (
        <div className="chunk chunk-action" style={animStyle}>
          <div className="chunk-label">
            <Play size={14} />
            Action Step {action.step || ""}
          </div>
          <div className="action-card">
            <span className="action-type-badge">{action.action || "execute"}</span>
            <span className="action-description">
              {action.description || action.target || JSON.stringify(action)}
            </span>
          </div>
        </div>
      );

    case "insight":
      return (
        <div className="chunk chunk-insight" style={animStyle}>
          <div className="chunk-label">
            <Lightbulb size={14} />
            Insight
          </div>
          <p className="insight-text">{chunk.content}</p>
        </div>
      );

    default:
      return null;
  }
}

function DataRenderer({ data }) {
  if (!data || typeof data !== "object") {
    return <pre className="data-raw">{String(data)}</pre>;
  }

  const type = data.type;

  if (type === "instagram_post" || type === "social_post") {
    return (
      <div className="social-card">
        <div className="social-platform">📱 {type === "instagram_post" ? "Instagram" : "Social"}</div>
        <p className="social-caption">{data.caption}</p>
        {data.hashtags && (
          <div className="social-hashtags">
            {data.hashtags.map((h, i) => (
              <span key={i} className="hashtag">#{h}</span>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (type === "launch_email") {
    return (
      <div className="email-card">
        <div className="email-subject">📧 {data.subject}</div>
        <p className="email-preview">{data.body?.substring(0, 150)}...</p>
        {data.cta && <div className="email-cta">{data.cta}</div>}
      </div>
    );
  }

  if (type === "landing_page") {
    return (
      <div className="landing-card">
        <h4 className="landing-headline">{data.headline}</h4>
        <p className="landing-sub">{data.subheadline}</p>
        {data.features && (
          <ul className="landing-features">
            {data.features.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        )}
        {data.cta && <div className="landing-cta-btn">{data.cta}</div>}
      </div>
    );
  }

  // Generic JSON display
  return (
    <pre className="data-json">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function getDataTypeLabel(data) {
  if (!data || typeof data !== "object") return "Data";
  const labels = {
    instagram_post: "Instagram Post",
    social_post: "Social Post",
    launch_email: "Launch Email",
    landing_page: "Landing Page",
  };
  return labels[data.type] || "Structured Data";
}
