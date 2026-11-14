import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import './CsvImports.css';

const API = (process.env.REACT_APP_BASE_URL || '/api').replace(/\/$/, '');
let clientScript;
function socketClient() {
  if (window.io) return Promise.resolve(window.io);
  if (!clientScript) clientScript = new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = API + '/import-socket/socket.io.js';
    script.onload = () => resolve(window.io); script.onerror = () => { clientScript = null; reject(Error('Progress connection unavailable')); };
    document.head.appendChild(script);
  });
  return clientScript;
}
const names = { queued: 'Queued', validating: 'Validating CSV', ready: 'Ready for review', activating: 'Storing policies', publishing: 'Publishing policies', completed: 'Published / existing policies kept', failed: 'Needs attention', removing: 'Removing owned policies', removed: 'Owned policies removed' };
export const policyPhase = job => ['activating', 'publishing', 'completed'].includes(job.status) || (job.status === 'failed' && ['activation', 'publication'].includes(job.error_phase));
export const progressOf = job => job.status === 'removed' ? 100 : job.status === 'removing' || (job.status === 'failed' && job.error_phase === 'removal') ? 0
  : policyPhase(job) ? (job.valid_records ? Math.min(100, job.activated_records * 100 / job.valid_records) : 0)
    : (job.total_records ? Math.min(100, job.processed_records * 100 / job.total_records) : job.status === 'ready' ? 100 : 0);
function CsvImports() {
  const navigate = useNavigate(), token = localStorage.getItem('token');
  const [jobs, setJobs] = useState([]), [selectedId, setSelectedId] = useState(null);
  const [files, setFiles] = useState([]), [transfer, setTransfer] = useState(0), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [connected, setConnected] = useState(false);
  const [preview, setPreview] = useState({ rows: [], failures: [] }), [acceptInvalid, setAcceptInvalid] = useState(false);
  const [dialog, setDialog] = useState(null);
  const refreshBusy = useRef(false), mounted = useRef(true), fileInput = useRef();
  const selected = jobs.find(job => job.id === selectedId);
  const chooseJob = useCallback(id => { setSelectedId(id); setAcceptInvalid(false); setDialog(null); }, []);
  const config = useCallback(() => ({ headers: { Authorization: 'Bearer ' + token }, timeout: 20000 }), [token]);
  const report = useCallback(e => {
    if (!mounted.current) return;
    if (e.response?.status === 401) { localStorage.removeItem('token'); navigate('/'); return; }
    setError(e.response?.data?.message || e.message || 'Request failed');
  }, [navigate]);
  const merge = useCallback(incoming => setJobs(previous => {
    const map = new Map(previous.map(job => [job.id, job]));
    for (const job of incoming) {
      const old = map.get(job.id);
      if (!old || Date.parse(job.updated_at) >= Date.parse(old.updated_at)) map.set(job.id, job);
    }
    return [...map.values()].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 50);
  }), []);
  const refresh = useCallback(async () => {
    if (!token || refreshBusy.current) return;
    refreshBusy.current = true;
    try { const r = await axios.get(API + '/ps/csv-imports', config()); if (mounted.current) merge(r.data.jobs); }
    catch (e) { report(e); }
    finally { refreshBusy.current = false; }
  }, [token, config, merge, report]);
  useEffect(() => {
    mounted.current = true;
    if (!token) { navigate('/'); return; }
    refresh(); const timer = setInterval(refresh, 3000); let socket, stopped = false;
    socketClient().then(io => {
      if (stopped) return;
      const endpoint = new URL(API, window.location.origin);
      socket = io(endpoint.origin, { path: endpoint.pathname.replace(/\/$/, '') + '/import-socket', auth: { token } });
      socket.on('connect', () => { setConnected(true); refresh(); });
      socket.on('disconnect', () => setConnected(false)); socket.on('connect_error', () => setConnected(false));
      socket.on('importProgress', job => merge([job]));
    }).catch(() => { if (!stopped) setConnected(false); });
    return () => { mounted.current = false; stopped = true; clearInterval(timer); socket?.disconnect(); };
  }, [token, navigate, refresh, merge]);
  useEffect(() => { if (!selectedId && jobs.length) chooseJob(jobs[0].id); }, [jobs, selectedId, chooseJob]);
  useEffect(() => {
    let cancelled = false;
    setPreview({ rows: [], failures: [] });
    if (selectedId) axios.get(API + '/ps/csv-imports/' + selectedId + '/preview', config())
      .then(r => { if (!cancelled) setPreview(r.data); }).catch(e => { if (!cancelled) report(e); });
    return () => { cancelled = true; };
  }, [selectedId, selected?.status, config, report]);
  async function upload(event) {
    event.preventDefault(); if (!files.length) return;
    setBusy(true); setError(''); setTransfer(0);
    try {
      const form = new FormData(); for (const file of files) form.append('files', file);
      const response = await axios.post(API + '/ps/csv-imports', form, { ...config(), timeout: 120000,
        onUploadProgress: e => { if (e.total) setTransfer(Math.round(e.loaded * 100 / e.total)); } });
      merge(response.data.jobs); chooseJob(response.data.jobs[0].id); setFiles([]); fileInput.current.value = ''; setTransfer(100);
    } catch (e) { report(e); } finally { setBusy(false); }
  }
  async function action(kind, reviewedInvalid = acceptInvalid) {
    if (!selected) return;
    setBusy(true); setError('');
    try {
      const data = kind === 'activate' ? { confirmation: 'ACTIVATE', acceptInvalid: reviewedInvalid } : kind === 'remove' ? { confirmation: 'REMOVE' } : {};
      const r = await axios.post(API + '/ps/csv-imports/' + selected.id + '/' + kind, data, config());
      merge([r.data.job]); setDialog(null); await refresh();
    } catch (e) { report(e); } finally { setBusy(false); }
  }
  async function download(endpoint, name) {
    setError('');
    try {
      const r = await axios.get(API + '/ps/csv-imports/' + endpoint, { ...config(), responseType: 'blob' });
      const url = URL.createObjectURL(r.data), a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    } catch (e) { report(e); }
  }
  return <main className="csv-imports">
    <header className="csv-heading"><div><p className="csv-crumb"><Link to="/dashboard">Dashboard</Link> / Policy management</p>
      <h1>CSV policy imports</h1><p>Upload → review → activate. Uploading a file does not block traffic.</p></div>
      <span className={'csv-connection ' + (connected ? 'online' : '')}>{connected ? 'Live progress connected' : 'Polling progress · every 3 seconds'}</span></header>
    {error && <div role="alert" className="csv-alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
    <section className="csv-panel" aria-labelledby="csv-upload-heading"><h2 id="csv-upload-heading">1. Upload CSV files</h2>
      <p>Required: <code>domain</code>. Optional: <code>ip_add</code>, <code>name</code>, <code>category</code>. Leave IP blank for a domain-only rule. Use hostnames, not full URLs.</p>
      <p>Up to 5 files, 25 MB each. Duplicate policies are counted; invalid rows are reported before activation.</p>
      <form onSubmit={upload} className="csv-upload-form"><label htmlFor="csv-files">Choose CSV files</label>
        <input ref={fileInput} id="csv-files" type="file" accept=".csv,text/csv" multiple onChange={e => setFiles([...e.target.files])} disabled={busy} />
        <button className="csv-primary" disabled={busy || !files.length} type="submit">{busy ? 'Working…' : 'Upload and validate'}</button>
        <button type="button" onClick={() => download('template.csv', 'netpro-policy-template.csv')}>Download template</button></form>
      {busy && transfer > 0 && <label className="csv-progress-label">File transfer {transfer}%<progress value={transfer} max="100" /></label>}
    </section>
    <div className="csv-workspace"><section className="csv-panel csv-history" aria-labelledby="csv-history-heading"><h2 id="csv-history-heading">Your recent imports</h2>
      {!jobs.length && <p>No imports yet.</p>}
      <ul>{jobs.map(job => <li key={job.id}><button className={selectedId === job.id ? 'selected' : ''} onClick={() => chooseJob(job.id)}>
        <strong>{job.filename}</strong><span>{names[job.status] || job.status}</span><small>{new Date(job.created_at).toLocaleString()}</small></button></li>)}</ul>
    </section><section className="csv-panel csv-details" aria-labelledby="csv-review-heading">
      <h2 id="csv-review-heading">2. Review and activate</h2>{!selected ? <p>Select an import to review its results.</p> : <>
        <div className="csv-job-title"><h3>{selected.filename}</h3><span className={'csv-status ' + selected.status}>{names[selected.status] || selected.status}</span></div>
        <p className="csv-job-id">Job: {selected.id}</p>
        <label className="csv-progress-label">{['removing', 'removed'].includes(selected.status) || selected.error_phase === 'removal' ? 'Removal' : policyPhase(selected) ? 'Policy storage' : 'Validation'} {Math.round(progressOf(selected))}%<progress value={progressOf(selected)} max="100" /></label>
        <dl className="csv-counts">{[['Input rows', selected.total_records], ['Unique valid', selected.valid_records], ['Duplicates', selected.duplicate_records], ['Invalid', selected.invalid_records]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{Number(value).toLocaleString()}</dd></div>)}</dl>
        {selected.error_message && <p role="alert" className="csv-alert">{selected.error_phase}: {selected.error_message}</p>}
        <p>Stored: <strong>{selected.publication.stored.toLocaleString()}</strong> · Kafka published: <strong>{selected.publication.published.toLocaleString()}</strong> · Existing (unverified): <strong>{selected.publication.existing_unverified.toLocaleString()}</strong></p>
        <p className="csv-note">Published means Kafka acknowledged the policy update. The dashboard does not yet receive a Policy Server enforcement acknowledgement.</p>
        {selected.invalid_records > 0 && <div className="csv-invalid"><button onClick={() => download(selected.id + '/failures.csv', 'failed-rows.csv')}>Download failed rows</button>
          {selected.status === 'ready' && <label><input type="checkbox" checked={acceptInvalid} onChange={e => setAcceptInvalid(e.target.checked)} /> I reviewed the failures. Activate valid policies only.</label>}</div>}
        <div className="csv-actions">
          {selected.status === 'ready' && <button className="csv-primary" disabled={busy || !selected.valid_records || (selected.invalid_records > 0 && !acceptInvalid)} onClick={() => setDialog({ kind: 'activate', acceptInvalid })}>Review activation</button>}
          {selected.status === 'failed' && <button disabled={busy} onClick={() => action('retry')}>Retry from checkpoint</button>}
          {['completed', 'publishing', 'failed'].includes(selected.status) && selected.publication.stored > 0 && <button disabled={busy} onClick={() => setDialog({ kind: 'remove' })}>Remove this import’s rules</button>}
        </div>
        <h3>Policy preview <small>(first 20 unique rows)</small></h3>
        <div className="csv-table-scroll"><table><thead><tr><th>CSV row</th><th>Domain</th><th>IPv4</th><th>Category</th></tr></thead><tbody>
          {preview.rows.map(row => <tr key={row.domain}><td>{row.row_number}</td><td>{row.domain}</td><td>{row.payload.ip_add || 'Domain only'}</td><td>{row.payload.category}</td></tr>)}
        </tbody></table></div>
        {preview.failures.length > 0 && <><h3>Validation failures <small>(first 20)</small></h3><ul className="csv-failures">{preview.failures.map(row => <li key={row.row_number}>Row {row.row_number}: {row.error_message}{row.domain ? ' — ' + row.domain : ''}</li>)}</ul></>}
      </>}
    </section></div>
    {dialog && selected && <div className="csv-modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="csv-confirm-heading" className="csv-modal">
      <h2 id="csv-confirm-heading">{dialog.kind === 'activate' ? 'Activate this import?' : 'Remove this import’s rules?'}</h2>
      <p>{dialog.kind === 'activate' ? `Activate ${selected.valid_records.toLocaleString()} unique valid policies from ${selected.filename}. Invalid rows are excluded. Existing policy fields will not be silently overwritten.` : 'Only policies created by this import can be removed. Pre-existing or shared policies are protected.'}</p>
      <p>Updates are queued durably and may take time to reach the Policy Server.</p>
      <div className="csv-actions"><button disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="csv-primary" disabled={busy} onClick={() => action(dialog.kind, dialog.acceptInvalid)}>{busy ? 'Working…' : dialog.kind === 'activate' ? 'Confirm activation' : 'Confirm removal'}</button></div>
    </section></div>}
  </main>;
}
export default CsvImports;
