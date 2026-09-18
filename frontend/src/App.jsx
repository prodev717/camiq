import { useState, useCallback } from 'react';
import VideoSelector from './components/VideoSelector';
import SearchBar from './components/SearchBar';
import ResultsGrid from './components/ResultsGrid';
import VideoPlayer from './components/VideoPlayer';
import styles from './App.module.css';

export default function App() {
  const [indexed, setIndexed] = useState(false);         // video is ready to search
  const [results, setResults] = useState([]);
  const [lastQuery, setLastQuery] = useState('');
  const [playerSeek, setPlayerSeek] = useState(null);   // null = closed
  const [showPlayer, setShowPlayer] = useState(false);

  const handleIndexed = useCallback(() => {
    setIndexed(true);
    setResults([]);
    setLastQuery('');
  }, []);

  const handleResults = useCallback((res, query) => {
    setResults(res);
    setLastQuery(query);
  }, []);

  const handleFrameClick = useCallback((result) => {
    setPlayerSeek(result.timestamp);
    setShowPlayer(true);
  }, []);

  const closePlayer = useCallback(() => {
    setShowPlayer(false);
  }, []);

  return (
    <div className={styles.app}>
      {/* Background gradient orbs */}
      <div className={styles.orb1} aria-hidden />
      <div className={styles.orb2} aria-hidden />

      {/* Main layout */}
      <main className={styles.main}>
        {/* Video selector + indexing */}
        <VideoSelector onReady={handleIndexed} />

        {/* Divider that appears after indexing */}
        {indexed && (
          <div className={styles.divider + ' fade-in'}>
            <div className={styles.dividerLine} />
            <span className={styles.dividerLabel}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              Search
            </span>
            <div className={styles.dividerLine} />
          </div>
        )}

        {/* Search section */}
        {indexed && (
          <div className="slide-up">
            <SearchBar
              onResults={handleResults}
              disabled={!indexed}
            />
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <ResultsGrid
            results={results}
            query={lastQuery}
            onFrameClick={handleFrameClick}
          />
        )}

        {/* Empty state when indexed but no results yet */}
        {indexed && results.length === 0 && lastQuery && (
          <div className={styles.emptyState + ' fade-in'}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="40" height="40">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <p>No results for <em>"{lastQuery}"</em></p>
            <small>Try a different description</small>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className={styles.footer}>
        <span>camiq</span>
        <span className={styles.footerDot}>·</span>
        <span>SigLIP semantic search</span>
        <span className={styles.footerDot}>·</span>
        <span>ViT-B-16</span>
      </footer>

      {/* Video player modal */}
      {showPlayer && (
        <VideoPlayer seekTo={playerSeek} onClose={closePlayer} />
      )}
    </div>
  );
}
