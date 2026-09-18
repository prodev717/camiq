import { frameUrl } from '../api';
import styles from './FrameCard.module.css';

const SCORE_COLOR = (score) => {
  if (score >= 0.28) return 'hsl(150,70%,50%)';
  if (score >= 0.22) return 'hsl(38,95%,60%)';
  return 'hsl(220,15%,60%)';
};

export default function FrameCard({ result, query, onClick, style }) {
  const { rank, frame_index, timestamp, timestamp_str, score } = result;
  const scoreColor = SCORE_COLOR(score);
  const scorePct = Math.min(100, Math.round(score * 333)); // rough visual scale

  return (
    <div
      id={`frame-card-${rank}`}
      className={styles.card}
      style={style}
      onClick={() => onClick(result)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick(result)}
      aria-label={`Result ${rank}: ${timestamp_str}, score ${score}`}
    >
      {/* Thumbnail */}
      <div className={styles.thumbWrap}>
        <img
          className={styles.thumb}
          src={frameUrl(frame_index)}
          alt={`Frame at ${timestamp_str}`}
          loading="lazy"
        />
        {/* Rank badge */}
        <div className={styles.rankBadge}>#{rank}</div>

        {/* Hover overlay */}
        <div className={styles.overlay}>
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" width="28" height="28">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <span>Jump to timestamp</span>
        </div>
      </div>

      {/* Footer */}
      <div className={styles.footer}>
        <div className={styles.meta}>
          <span className={styles.timestamp}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
              <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
            </svg>
            {timestamp_str}
          </span>
        </div>

        {/* Score bar */}
        <div className={styles.scoreRow}>
          <div className={styles.scoreTrack}>
            <div
              className={styles.scoreBar}
              style={{ width: `${scorePct}%`, background: scoreColor }}
            />
          </div>
          <span className={styles.scoreNum} style={{ color: scoreColor }}>
            {score.toFixed(4)}
          </span>
        </div>
      </div>
    </div>
  );
}
