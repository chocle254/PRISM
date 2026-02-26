// ── ActionFeed.jsx ──────────────────────────────────────────────────────────
import React from "react";
import { CheckCircle, Circle, Loader, AlertCircle, Zap } from "lucide-react";

export function ActionFeed({ actions }) {
  if (!actions || actions.length === 0) {
    return (
      <div className="action-feed action-feed-empty">
        <Zap size={32} strokeWidth={1} />
        <h3>Action Queue</h3>
        <p>PRISM will execute UI actions here — navigating apps, filling forms, creating content.</p>
      </div>
    );
  }

  return (
    <div className="action-feed">
      <div className="action-feed-header">
        <Zap size={16} />
        <span>Execution Plan</span>
        <span className="action-count">{actions.length} steps</span>
      </div>
      <div className="action-list">
        {actions.map((action, i) => (
          <ActionStep key={i} action={action} index={i} />
        ))}
      </div>
    </div>
  );
}

function ActionStep({ action, index }) {
  const status = action.status || "pending";
  const icons = {
    pending: <Circle size={16} className="step-icon pending" />,
    running: <Loader size={16} className="step-icon running spin" />,
    done: <CheckCircle size={16} className="step-icon done" />,
    error: <AlertCircle size={16} className="step-icon error" />,
  };

  return (
    <div className={`action-step action-step-${status}`}>
      <div className="step-number">{index + 1}</div>
      {icons[status]}
      <div className="step-content">
        <div className="step-action">{action.action}</div>
        <div className="step-description">{action.target_description || action.description}</div>
        {action.value && <div className="step-value">"{action.value}"</div>}
        {action.wait_for && (
          <div className="step-wait">⏳ Wait for: {action.wait_for}</div>
        )}
      </div>
    </div>
  );
}

export default ActionFeed;
