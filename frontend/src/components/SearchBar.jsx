import { useState, useRef } from 'react';
import { searchQuery } from '../api';
import styles from './SearchBar.module.css';

const SUGGESTIONS = [
  'person carrying a backpack',
  'car parked near the entrance',
  'two people talking',
  'someone running',
  'empty corridor',
  'group of people',
];

export default function SearchBar({ onResults, disabled }) {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  const handleSearch = async (e) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q || loading) return;
    setError('');
    setLoading(true);
    try {
      const data = await searchQuery(q, topK);
      onResults(data.results, q);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestion = (s) => {
    setQuery(s);
    inputRef.current?.focus();
  };

  return (
    <div className={styles.wrapper}>
      <form className={styles.form} onSubmit={handleSearch}>
        <div className={styles.inputWrap}>
          {/* Search icon */}
          <span className={styles.searchIcon}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>

          <input
            id="search-query-input"
            ref={inputRef}
            className={styles.input}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe what you're looking for…"
            disabled={disabled || loading}
            autoComplete="off"
          />

          {query && (
            <button
              type="button"
              className={styles.clearBtn}
              onClick={() => { setQuery(''); inputRef.current?.focus(); }}
              aria-label="Clear"
            >
              ✕
            </button>
          )}
        </div>

        {/* Top-K slider */}
        <div className={styles.sliderWrap}>
          <label className={styles.sliderLabel} htmlFor="topk-slider">
            Top <span className={styles.sliderVal}>{topK}</span>
          </label>
          <input
            id="topk-slider"
            className={styles.slider}
            type="range"
            min={1}
            max={20}
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            disabled={disabled || loading}
          />
        </div>

        <button
          id="search-submit-btn"
          className={styles.btn}
          type="submit"
          disabled={disabled || loading || !query.trim()}
        >
          {loading ? <span className={styles.spinner} /> : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="18" height="18">
              <polyline points="5 12 12 5 19 12" /><line x1="12" y1="5" x2="12" y2="19" />
            </svg>
          )}
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {/* Suggestion chips */}
      <div className={styles.suggestions} aria-label="Suggested searches">
        <span className={styles.suggestLabel}>Try:</span>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            id={`suggestion-${s.replace(/\s+/g, '-')}`}
            className={styles.chip}
            type="button"
            onClick={() => handleSuggestion(s)}
            disabled={disabled || loading}
          >
            {s}
          </button>
        ))}
      </div>

      {error && (
        <div className={styles.error} role="alert">{error}</div>
      )}
    </div>
  );
}
