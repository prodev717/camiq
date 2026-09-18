import { useRef, useEffect, useState } from 'react';
import { videoStreamUrl } from '../api';
import styles from './VideoPlayer.module.css';

export default function VideoPlayer({ seekTo, onClose }) {
  const videoRef = useRef(null);
  const seekToRef = useRef(seekTo);     // always up-to-date inside callbacks
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  // Keep ref in sync so event listeners always see the latest value
  useEffect(() => {
    seekToRef.current = seekTo;
  }, [seekTo]);

  // Attempt to seek whenever seekTo changes
  useEffect(() => {
    if (seekTo === null || seekTo === undefined) return;
    const vid = videoRef.current;
    if (!vid) return;

    const doSeek = () => {
      vid.currentTime = seekTo;
      vid.play().catch(() => {});
    };

    // readyState >= 1 means HAVE_METADATA — safe to set currentTime
    if (vid.readyState >= 1) {
      doSeek();
    } else {
      vid.addEventListener('loadedmetadata', doSeek, { once: true });
      return () => vid.removeEventListener('loadedmetadata', doSeek);
    }
  }, [seekTo]);

  return (
    <div className={styles.backdrop} onClick={onClose} role="dialog" aria-label="Video player">
      <div className={styles.panel} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.panelHeader}>
          <div className={styles.panelTitle}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            Video Playback
            {seekTo !== null && seekTo !== undefined && (
              <span className={styles.seekBadge}>
                ⏱ {new Date(seekTo * 1000).toISOString().substr(11, 8)}
              </span>
            )}
          </div>
          <button
            id="close-player-btn"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close player"
          >
            ✕
          </button>
        </div>

        {/* Video */}
        <div className={styles.videoWrap}>
          {error ? (
            <div className={styles.errorState}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="40" height="40">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <p>Could not load video stream.</p>
              <small>Make sure the video path is accessible to the backend.</small>
            </div>
          ) : (
            <>
              {!loaded && (
                <div className={styles.loadingState}>
                  <span className={styles.spinner} />
                  <p>Loading video…</p>
                </div>
              )}
              <video
                ref={videoRef}
                className={styles.video}
                style={{ opacity: loaded ? 1 : 0 }}
                src={videoStreamUrl()}
                controls
                playsInline
                onLoadedMetadata={() => setLoaded(true)}
                onError={() => setError(true)}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

