import React, { useState } from 'react';
import { api } from '../api.js';

const SAMPLE_TEXT = `Ada Lovelace wrote the first algorithm for the Analytical Engine in 1843.
She is widely recognized as the first computer programmer. Her work was
published in a translation of a paper about Babbage's engine.`;

const SAMPLE_SCHEMA = JSON.stringify(
  {
    type: 'object',
    properties: {
      summary: { type: 'string' },
      entities: { type: 'array', items: { type: 'string' } },
      sentiment: { type: 'string', enum: ['positive', 'negative', 'neutral'] },
    },
    required: ['summary'],
  },
  null,
  2,
);

export default function TaskSubmission({ onCreated }) {
  const [text, setText] = useState(SAMPLE_TEXT);
  const [schemaText, setSchemaText] = useState(SAMPLE_SCHEMA);
  const [maxRetries, setMaxRetries] = useState(2);
  const [showSchema, setShowSchema] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setResult(null);

    let schema = null;
    if (schemaText.trim()) {
      try {
        schema = JSON.parse(schemaText);
      } catch (err) {
        setError(`Schema is not valid JSON: ${err.message}`);
        return;
      }
    }

    setLoading(true);
    try {
      const created = await api.createTask({ inputText: text, schema, maxRetries });
      setResult(created);
      setText('');
      onCreated(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="workspace-grid">
      <section className="card form-card">
        <div className="card-heading">
          <div>
            <h2>New extraction</h2>
            <p>Submit unstructured text; the local LLM returns schema-valid JSON.</p>
          </div>
          <button
            type="button"
            className="link-button"
            onClick={() => setShowSchema((value) => !value)}
          >
            {showSchema ? 'Hide schema' : 'Customize schema'}
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <label htmlFor="input-text">Unstructured input text</label>
          <textarea
            id="input-text"
            rows={10}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Paste notes, emails, reports, or any unstructured text…"
          />

          {showSchema && (
            <div className="schema-block">
              <label htmlFor="schema-text">
                JSON Schema <span className="muted">(optional)</span>
              </label>
              <textarea
                id="schema-text"
                className="mono"
                rows={12}
                value={schemaText}
                onChange={(event) => setSchemaText(event.target.value)}
              />
              <label htmlFor="max-retries">Max repair retries</label>
              <input
                id="max-retries"
                type="number"
                min="0"
                max="10"
                value={maxRetries}
                onChange={(event) => setMaxRetries(event.target.value)}
              />
            </div>
          )}

          {error && <div className="alert error">{error}</div>}

          <div className="form-actions">
            <button type="submit" className="button primary" disabled={loading}>
              {loading ? 'Extracting…' : 'Run extraction'}
            </button>
            <span className="muted small">Model runs locally via Ollama — no cloud APIs.</span>
          </div>
        </form>
      </section>

      <aside className="card result-card">
        <div className="card-heading">
          <div>
            <h2>Latest result</h2>
            <p>Review, edit, and approve in the Tasks view.</p>
          </div>
        </div>
        {result ? (
          <>
            <div className="result-meta">
              <span className={`badge ${result.status}`}>{result.status}</span>
              <span className="muted small mono">{result.id.slice(0, 8)}</span>
            </div>
            <pre className="json-view">
              {JSON.stringify(result.extracted_payload?.fields ?? {}, null, 2)}
            </pre>
            {result.metrics && (
              <div className="metric-strip">
                <span>{Math.round(result.metrics.latency_ms)} ms</span>
                <span>{result.metrics.retry_count} retries</span>
                <span className="mono small">{result.metrics.model_used}</span>
              </div>
            )}
            {result.error_diagnostic && (
              <div className="alert warning small">{result.error_diagnostic}</div>
            )}
          </>
        ) : (
          <div className="empty-state">
            <span className="empty-icon">◇</span>
            <p>No extraction yet. Submit text to see structured fields here.</p>
          </div>
        )}
      </aside>
    </div>
  );
}
