import FrameCard from './FrameCard';
import styles from './ResultsGrid.module.css';

export default function ResultsGrid({ results, query, onFrameClick }) {
  if (!results || results.length === 0) return null;

  return (
    <section className={styles.section} aria-label="Search results">
      {/* Section header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.dot} />
          <h2 className={styles.title}>
            Top <span className={styles.accentNum}>{results.length}</span> matches
          </h2>
          {query && (
            <span className={styles.queryChip}>"{query}"</span>
          )}
        </div>
        <span className={styles.hint}>Click a frame to seek video</span>
      </div>

      {/* Grid */}
      <div className={styles.grid}>
        {results.map((result, i) => (
          <FrameCard
            key={result.frame_index}
            result={result}
            query={query}
            onClick={onFrameClick}
            style={{ animationDelay: `${i * 60}ms` }}
          />
        ))}
      </div>
    </section>
  );
}
