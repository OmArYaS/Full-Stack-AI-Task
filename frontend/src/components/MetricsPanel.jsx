import React from 'react';

const STATUS_COLORS = {
  pending_review: '#d97706',
  approved: '#059669',
  rejected: '#dc2626',
  failed_validation: '#b91c1c',
  needs_manual_fix: '#7c3aed',
};

export default function MetricsPanel({ metrics }) {
  if (!metrics) {
    return (
      <section className="card">
        <div className="empty-state">
          <p>Loading metrics…</p>
        </div>
      </section>
    );
  }

  const statusEntries = Object.entries(metrics.status_counts || {});
  const maxCount = Math.max(1, ...statusEntries.map(([, count]) => count));
  const successPct = Math.round((metrics.schema_validation_success_rate || 0) * 100);

  return (
    <div className="metrics-page">
      <section className="stats-grid large">
        <div className="stat-card">
          <span>Total tasks</span>
          <strong>{metrics.total_tasks}</strong>
          <small>Records persisted in SQLite</small>
        </div>
        <div className="stat-card">
          <span>Schema validation</span>
          <strong>{successPct}%</strong>
          <small>
            {metrics.schema_validation_success_count} of {metrics.tasks_with_metrics} successful
          </small>
        </div>
        <div className="stat-card">
          <span>Avg latency</span>
          <strong>{Math.round(metrics.avg_latency_ms || 0)} ms</strong>
          <small>Per extraction request</small>
        </div>
        <div className="stat-card">
          <span>Repair retries</span>
          <strong>{metrics.total_retries}</strong>
          <small>Avg {metrics.avg_retry_count || 0} per task</small>
        </div>
      </section>

      <section className="card">
        <div className="card-heading">
          <div>
            <h2>Status distribution</h2>
            <p>Human review outcomes and validation failures.</p>
          </div>
        </div>
        {statusEntries.every(([, count]) => count === 0) ? (
          <div className="empty-state">
            <span className="empty-icon">◇</span>
            <p>No tasks recorded yet — submit text in the workspace to see metrics.</p>
          </div>
        ) : (
          <div className="status-bars">
            {statusEntries.map(([status, count]) => (
              <div className="status-bar-row" key={status}>
                <span className="status-bar-label">{status}</span>
                <div className="status-bar-track">
                  <div
                    className="status-bar-fill"
                    style={{
                      width: `${Math.round((count / maxCount) * 100)}%`,
                      background: STATUS_COLORS[status] || '#64748b',
                    }}
                  />
                </div>
                <span className="status-bar-count">{count}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-heading">
          <div>
            <h2>Models used</h2>
            <p>Model-agnostic: swap Ollama models via environment configuration.</p>
          </div>
        </div>
        {(metrics.models_used || []).length === 0 ? (
          <p className="muted small">No model calls recorded.</p>
        ) : (
          <div className="model-list">
            {metrics.models_used.map((model) => (
              <span className="model-chip mono" key={model}>
                {model}
              </span>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
