import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

function toDraft(fields) {
  return Object.fromEntries(
    Object.entries(fields || {}).map(([key, value]) => [
      key,
      value !== null && typeof value === 'object'
        ? JSON.stringify(value, null, 2)
        : String(value ?? ''),
    ]),
  );
}

function fromDraft(draft, originalFields) {
  const result = {};
  for (const [key, raw] of Object.entries(draft)) {
    const original = originalFields?.[key];
    if (typeof original === 'number') result[key] = Number(raw);
    else if (typeof original === 'boolean') result[key] = raw === 'true';
    else if (original && typeof original === 'object') result[key] = JSON.parse(raw);
    else {
      // New fields (no original type): parse JSON when possible, else string.
      try {
        result[key] = JSON.parse(raw);
      } catch {
        result[key] = raw;
      }
    }
  }
  return result;
}

export default function TaskDetail({ task, onUpdated }) {
  const [draft, setDraft] = useState({});
  const [notes, setNotes] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  const originalFields = task?.extracted_payload?.fields ?? {};

  useEffect(() => {
    setDraft(toDraft(originalFields));
    setNotes(task?.review_notes ?? '');
    setReviewer(task?.reviewed_by ?? '');
    setError('');
    setShowRaw(false);
  }, [task?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!task) {
    return (
      <section className="card">
        <div className="empty-state">
          <span className="empty-icon">◇</span>
          <p>Select a task from the list to inspect and review it.</p>
        </div>
      </section>
    );
  }

  function addField() {
    const key = newKey.trim();
    if (!key) return;
    setDraft((current) => ({ ...current, [key]: newValue }));
    setNewKey('');
    setNewValue('');
  }

  async function submit(decision) {
    setError('');
    let fields;
    try {
      fields = fromDraft(draft, originalFields);
    } catch (err) {
      setError(`Invalid JSON in a field: ${err.message}`);
      return;
    }
    setBusy(true);
    try {
      const updated = await api.reviewTask(task.id, {
        decision,
        fields,
        notes,
        reviewer,
      });
      onUpdated(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const terminal = task.status === 'approved' || task.status === 'rejected';

  return (
    <section className="card detail-card">
      <div className="card-heading">
        <div>
          <h2>Task {task.id.slice(0, 8)}</h2>
          <p>
            Created {task.created_at ? new Date(task.created_at).toLocaleString() : '—'}
          </p>
        </div>
        <span className={`badge ${task.status}`}>{task.status}</span>
      </div>

      <div className="detail-grid">
        <div>
          <h3>Input text</h3>
          <p className="input-text">{task.input_text}</p>

          <h3>Extracted fields</h3>
          <div className="field-list">
            {Object.keys(draft).length === 0 && (
              <p className="muted small">No fields extracted.</p>
            )}
            {Object.entries(draft).map(([key, value]) => (
              <div className="field-row" key={key}>
                <label>{key}</label>
                {value.includes('\n') ? (
                  <textarea
                    className="mono"
                    rows={3}
                    value={value}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, [key]: event.target.value }))
                    }
                  />
                ) : (
                  <input
                    type="text"
                    value={value}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, [key]: event.target.value }))
                    }
                  />
                )}
              </div>
            ))}
          </div>

          <div className="add-field">
            <input
              type="text"
              placeholder="new field name"
              value={newKey}
              onChange={(event) => setNewKey(event.target.value)}
            />
            <input
              type="text"
              placeholder='value (e.g. "text" or 42)'
              value={newValue}
              onChange={(event) => setNewValue(event.target.value)}
            />
            <button type="button" className="button ghost" onClick={addField}>
              Add field
            </button>
          </div>

          <div className="review-form">
            <label htmlFor="reviewer">Reviewer</label>
            <input
              id="reviewer"
              type="text"
              value={reviewer}
              onChange={(event) => setReviewer(event.target.value)}
              placeholder="Your name"
            />
            <label htmlFor="notes">Review notes</label>
            <textarea
              id="notes"
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Describe what you verified or corrected…"
            />
            {error && <div className="alert error">{error}</div>}
            <div className="form-actions">
              <button
                type="button"
                className="button primary"
                disabled={busy || terminal}
                onClick={() => submit('approved')}
              >
                {busy ? 'Saving…' : 'Save & Approve'}
              </button>
              <button
                type="button"
                className="button danger"
                disabled={busy || terminal}
                onClick={() => submit('rejected')}
              >
                Save & Reject
              </button>
              {terminal && (
                <span className="muted small">This task is terminal and cannot be re-reviewed.</span>
              )}
            </div>
          </div>
        </div>

        <aside>
          <h3>Observability</h3>
          {task.metrics ? (
            <div className="stats-grid">
              <div className="stat">
                <span>Status</span>
                <strong>{task.status}</strong>
              </div>
              <div className="stat">
                <span>Latency</span>
                <strong>{Math.round(task.metrics.latency_ms)} ms</strong>
              </div>
              <div className="stat">
                <span>Retry count</span>
                <strong>{task.metrics.retry_count}</strong>
              </div>
              <div className="stat">
                <span>Schema valid</span>
                <strong>{task.metrics.schema_validation_success ? 'Yes' : 'No'}</strong>
              </div>
              <div className="stat wide">
                <span>Model used</span>
                <strong className="mono small">{task.metrics.model_used}</strong>
              </div>
            </div>
          ) : (
            <p className="muted small">No metrics recorded.</p>
          )}

          {task.error_diagnostic && (
            <div className="alert warning small">{task.error_diagnostic}</div>
          )}

          <button
            type="button"
            className="link-button"
            onClick={() => setShowRaw((value) => !value)}
          >
            {showRaw ? 'Hide raw LLM output' : 'Show raw LLM output'}
          </button>
          {showRaw && <pre className="json-view">{task.extracted_payload?.raw_llm_response || '—'}</pre>}
        </aside>
      </div>
    </section>
  );
}
