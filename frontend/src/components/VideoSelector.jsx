import { useState, useEffect, useRef } from 'react';
import { startIndexing, getIndexStatus } from '../api';
import styles from './VideoSelector.module.css';

export default function VideoSelector({ onReady }) {
  const [path, setPath] = useState('');
  const [status, setStatus] = useState(null); // null | 'indexing' | 'ready' | 'error'
  const [progress, setProgress] = useState({ pct: 0, msg: '' });
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const pollRef = useRef(null);

  /* Poll /index/status while indexing */
  useEffect(() => {
    if (status === 'indexing') {
      pollRef.current = setInterval(async () => {
        try {
          const data = await getIndexStatus();
          setProgress({ pct: data.progress_pct, msg: data.progress_msg });
          if (data.status === 'ready') {
            setStatus('ready');
            setStats(data.stats);
            onReady(data.video_path);
            clearInterval(pollRef.current);
          } else if (data.status === 'error') {
            setStatus('error');
            setError(data.error || 'Unknown error');
            clearInterval(pollRef.current);
          }
        } catch {
          /* network hiccup — keep polling */
        }
      }, 1000);
    }
    return () => clearInterval(pollRef.current);
  }, [status, onReady]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!path.trim()) return;
    setError('');
    setStats(null);
    try {
      await startIndexing(path.trim());
      setStatus('indexing');
      setProgress({ pct: 0, msg: 'Starting…' });
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.logoWrap}>
          <span className={styles.logoIcon}>⬡</span>
          <span className={styles.logoText}>camiq</span>
        </div>
        <p className={styles.tagline}>AI-powered natural language search for CCTV footage</p>
      </div>

      {/* Input form */}
      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.inputGroup}>
          <span className={styles.inputIcon}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M15 10l4.553-2.069A1 1 0 0121 8.869v6.262a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
            </svg>
          </span>
          <input
            id="video-path-input"
            className={styles.input}
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="Enter full path to video file  (e.g. C:\footage\cctv.mp4)"
            disabled={status === 'indexing'}
            autoComplete="off"
            spellCheck="false"
          />
        </div>
        <button
          id="index-video-btn"
          className={styles.btn}
          type="submit"
          disabled={status === 'indexing' || !path.trim()}
        >
          {status === 'indexing' ? (
            <>
              <span className={styles.spinner} />
              Indexing…
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              Index Video
            </>
          )}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className={styles.errorBanner} role="alert">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </div>
      )}

      {/* Progress bar */}
      {status === 'indexing' && (
        <div className={styles.progressWrap}>
          <div className={styles.progressHeader}>
            <span className={styles.progressMsg}>{progress.msg}</span>
            <span className={styles.progressPct}>{Math.round(progress.pct)}%</span>
          </div>
          <div className={styles.progressTrack}>
            <div
              className={styles.progressBar}
              style={{ width: `${progress.pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Stats badge on ready */}
      {status === 'ready' && stats && (
        <div className={styles.statsBanner + ' fade-in'}>
          <div className={styles.statItem}>
            <span className={styles.statVal}>{stats.total_frames}</span>
            <span className={styles.statLabel}>Indexed Frames</span>
          </div>
          {stats.skipped_static !== undefined && (
            <>
              <div className={styles.statDivider} />
              <div className={styles.statItem}>
                <span className={styles.statVal}>{stats.skipped_static}</span>
                <span className={styles.statLabel}>Static Skipped</span>
              </div>
              <div className={styles.statDivider} />
              <div className={styles.statItem}>
                <span className={styles.statVal}>{stats.skipped_semantic}</span>
                <span className={styles.statLabel}>Duplicates Skipped</span>
              </div>
              <div className={styles.statDivider} />
              <div className={styles.statItem}>
                <span className={styles.statVal}>{stats.elapsed_seconds}s</span>
                <span className={styles.statLabel}>Elapsed</span>
              </div>
            </>
          )}
          {stats.source === 'cached' && (
            <>
              <div className={styles.statDivider} />
              <div className={`${styles.statItem} ${styles.cachedBadge}`}>
                <span>⚡ Loaded from cache</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
