import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

const STATUS_OPTIONS = [
  ['', 'All statuses'],
  ['pending_review', 'Pending review'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
  ['needs_manual_fix', 'Needs manual fix'],
  ['failed_validation', 'Failed validation'],
];

export default function TaskList({ tasks, status, setStatus, onSelect, selectedId }) {
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api
      .listTasks(status)
      .then(() => {
        if (active) setError('');
      })
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
    };
  }, [status]);

  return (
    <section className="card">
      <div className="card-heading">
        <div>
          <h2>Tasks</h2>
          <p>Inspect extracted fields, review, and export verified records.</p>
        </div>
        <div className="toolbar">
          <select
            aria-label="Filter by status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            {STATUS_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <a className="button ghost" href={api.exportTasks('json', status)}>
            Export JSON
          </a>
          <a className="button ghost" href={api.exportTasks('csv', status)}>
            Export CSV
          </a>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      {tasks.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">◇</span>
          <p>No tasks match this filter yet.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Summary</th>
                <th>Latency</th>
                <th>Retries</th>
                <th>Valid</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr
                  key={task.id}
                  className={selectedId === task.id ? 'selected' : ''}
                  onClick={() => onSelect(task.id)}
                >
                  <td className="mono">{task.id.slice(0, 8)}</td>
                  <td>
                    <span className={`badge ${task.status}`}>{task.status}</span>
                  </td>
                  <td className="truncate">
                    {task.extracted_payload?.fields?.summary ?? '—'}
                  </td>
                  <td>{Math.round(task.metrics?.latency_ms ?? 0)} ms</td>
                  <td>{task.metrics?.retry_count ?? 0}</td>
                  <td>
                    {task.metrics?.schema_validation_success ? '✓' : '✕'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
