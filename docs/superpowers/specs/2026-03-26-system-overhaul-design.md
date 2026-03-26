# AI Lunch Mind System Overhaul Design

## Summary

Rewrite the AI recommendation brain, replace OpenAI with Gemini 2.5 Flash, add API Key Pool with SQLite storage, implement dual-track search (Google Maps + social crawling), and redesign the scoring/ranking system with budget awareness.

## Problems Being Solved

| Problem | Severity | Current State |
|---------|----------|---------------|
| Distance-only ranking | Critical | 1-star restaurant at 500m beats 4.8-star at 1.5km |
| Budget extracted but never used | Critical | dialog_analysis.py parses budget, downstream ignores it |
| Judge Agent too strict | High | Binary relevant/irrelevant, filters valid restaurants |
| Keywords don't combine | High | Weather/time/intent are mutually exclusive fallbacks |
| No social data | High | Only Google Maps, no human recommendations |
| google_maps.py 3000 lines | Medium | 27 CSS selectors, monolithic, unmaintainable |
| OpenAI lock-in | Medium | 5 API call points across 2 modules |

## Architecture

### Module Structure

```
modules/
├── scraper/
│   ├── __init__.py
│   ├── browser_pool.py      # Unified browser pool for all Selenium scrapers
│   ├── google_maps.py       # Maps search + restaurant data extraction (~800 lines)
│   ├── google_search.py     # Google search results scraper (new)
│   ├── ptt_scraper.py       # PTT Food board scraper using requests (new)
│   └── selectors.py         # Centralized CSS selector management
├── ai/
│   ├── __init__.py
│   ├── gemini_pool.py       # API Key Pool with SQLite storage
│   ├── intent_analyzer.py   # Gemini Call #1: intent + keywords + budget + weather fusion
│   └── restaurant_scorer.py # Gemini Call #2: relevance scoring + price estimation
├── geo/
│   ├── __init__.py
│   ├── geocoding.py         # Address parsing, coordinate conversion, Taiwan normalization
│   └── distance.py          # Distance calculation (straight-line + walking)
├── recommendation_engine.py # Main orchestration
├── sqlite_cache_manager.py  # Existing, no changes
├── weather.py               # Existing, no changes
└── sweat_index.py           # Existing, no changes
```

---

## 1. Gemini API Key Pool

### SQLite Schema

```sql
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT NOT NULL UNIQUE,
    status TEXT DEFAULT 'active',        -- active | disabled
    cooldown_until REAL DEFAULT 0,       -- Unix timestamp, 0 = not cooling
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE api_key_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_suffix TEXT NOT NULL,            -- Last 4 chars only (security)
    model TEXT,
    call_type TEXT,                      -- 'intent_analysis' | 'restaurant_scoring' | etc
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Key Selection: Random (Not Round-Robin)

- `get_key()`: Randomly select from all non-cooldown keys. Random distribution avoids hotspotting the first few keys which causes 429.
- `get_key_excluding(failed_key)`: Randomly select from available keys excluding the failed one.
- `mark_bad(key)`: Set `cooldown_until = now + 120 seconds`. Key auto-recovers after cooldown.

### Auto-Retry Decorator

```python
@gemini_pool.auto_retry
def call_gemini(prompt, **kwargs):
    # Pool injects api_key automatically
    # On 429: mark_bad(key) → random pick another → retry
    # Max retries = number of available keys - 1
    # If all keys exhausted: raise GeminiPoolExhausted
```

### Key Management API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/keys/import` | POST | Bulk import keys from textarea (one per line) |
| `/api/keys/status` | GET | List all keys (suffix only) with status + usage |
| `/api/keys/{suffix}` | DELETE | Remove a key by last 4 chars |

### Key Import Logic

- Accept multiline text, one key per line
- Auto-filter: empty lines, duplicates, invalid format (must start with `AIza`, length >= 20)
- Validate each key with a test Gemini call
- Store in SQLite only (never in .env, never in git)
- Logs only show last 4 chars of key

### Security

- `cache.db` already in `.gitignore` — verify this before implementation
- API key values never appear in logs, only `...{last4}`
- No key data in any committed file
- Key management endpoints should be local-only (no auth needed since it's a personal tool, but bind to 127.0.0.1)

### Thread Safety

- `get_key()` / `mark_bad()` must be thread-safe (multiple search threads call concurrently)
- Use `threading.Lock` around key selection and cooldown updates
- SQLite connections use `check_same_thread=False` with lock protection

---

## 2. AI Brain Rewrite

### Gemini Call #1: Intent Analysis

**Input:** user_input + weather data + current time
**Output:**
```json
{
  "location": "台北101",
  "primary_keywords": ["拉麵", "日式拉麵"],
  "secondary_keywords": ["涼麵", "冷麵"],
  "budget": { "max": 200 },
  "estimated_price_range": "平價",
  "search_radius_hint": "近距離",
  "intent": "search_food_type"
}
```

Key improvements over current system:
- **Single call fuses all context**: user intent + weather + time of day + budget
- **Primary + secondary keywords**: Main search terms + weather/time-aware alternatives
- **AI price estimation**: Gemini infers budget tier from user input context
- **Replaces**: `dialog_analysis.analyze_user_request()` + `_get_search_keywords()` + `get_weather_based_keywords()`

### Gemini Call #2: Restaurant Scoring

**Input:** merged restaurant list + original user request
**Output per restaurant:**
```json
{
  "relevance_score": 8.5,
  "estimated_price": "$180-250",
  "reason": "日式豚骨拉麵，距離近，PTT多人推薦"
}
```

Key improvements:
- **Score 0-10 instead of binary**: "麵屋武藏" scores 9 for "拉麵", "牛肉麵店" scores 3 (not filtered)
- **Price estimation**: Fills in missing price data using restaurant name + type inference
- **Recommendation reason**: One-line explanation for the user

### Replaces

| Old Module | New Module |
|------------|------------|
| `dialog_analysis.py` (OpenAI gpt-4o-mini) | `ai/intent_analyzer.py` (Gemini 2.5 Flash) |
| `ai_validator.py` judge agent (OpenAI + Claude fallback) | `ai/restaurant_scorer.py` (Gemini 2.5 Flash) |
| `ai_validator.py` 3 validation stages (gpt-3.5-turbo) | Removed. Scoring replaces validation. |

---

## 3. Dual-Track Search

### Track A: Google Maps (Existing, Refactored)

- Search Google Maps for each keyword near the location
- Extract: name, rating, review_count, price_level, coordinates, open_now, hours
- Provides the structural data backbone

### Track B: Google Search Scraper (New)

- Search: `https://www.google.com/search?q={location}+{keyword}+推薦&hl=zh-TW`
- Use Selenium from shared browser pool
- Extract only titles + snippets from search results (don't visit individual sites)
- Feed snippets to Gemini to extract mentioned restaurant names

### Track C: PTT Scraper (New)

- Search: `https://www.ptt.cc/bbs/Food/search?q={keyword}+{location}`
- Use `requests` (no Selenium needed, doesn't consume browser pool)
- Extract: article titles, upvote count, first 500 chars of content
- Feed to Gemini to extract recommended restaurant names

### Merge Logic

1. Google Maps results form the base list (have structured data)
2. Social sources (Google Search + PTT) produce restaurant names
3. Match social names against Maps results → add `social_proof` tag + bonus score
4. Unmatched social names → search Maps for coordinates/rating to fill in
5. Still unmatched → keep with "社群推薦，無Maps資料" label

### Social Proof Scoring

| Condition | Bonus |
|-----------|-------|
| Mentioned in Google Search snippet | +1.0 |
| Mentioned in PTT article title | +1.5 |
| PTT article upvotes > 20 | +0.5 |
| Multiple sources mention same restaurant | +1.0 extra |

---

## 4. Scoring Formula

```
Final Score = 0.30 x distance_score
            + 0.25 x relevance_score (from Gemini Call #2)
            + 0.20 x google_rating_score
            + 0.15 x social_proof_score
            + 0.10 x budget_match_score
```

### Score Normalization

- **distance_score**: Inverse distance, normalized 0-10 (closer = higher)
- **relevance_score**: Direct from Gemini (0-10)
- **google_rating_score**: Google Maps rating scaled (3.0=0, 5.0=10)
- **social_proof_score**: Sum of social bonuses, capped at 10
- **budget_match_score**: 10 if within budget, 5 if unknown, 0 if over budget

---

## 5. Performance Design

### Target: < 6 seconds total

```
Phase 1: Intent Analysis        < 1.0s    Gemini 2.5 Flash
Phase 2: Triple-Track Search    < 3.0s    All parallel, 3s hard timeout
Phase 3: Scoring + Ranking      < 1.5s    Gemini scoring + formula
Buffer                            0.5s
Total                           < 6.0s
```

### Parallelism

- Phase 2 runs all tracks in ThreadPoolExecutor concurrently
- PTT uses requests (no browser), runs truly independent
- Google Maps + Google Search share browser pool but different instances

### Hard Timeouts

- Each search track: 3 second deadline
- Timed-out tracks are abandoned, results from completed tracks are used
- Gemini Call #2: 2 second timeout, falls back to simple formula

### Degradation Strategy

```
Best case:  Maps + Google Search + PTT + Gemini scoring     (full experience)
Fallback 1: Maps + partial social + Gemini scoring          (some tracks timed out)
Fallback 2: Maps + simple formula (distance + rating)       (Gemini scoring timed out)
Worst case: Maps only + distance sort                       (same as current system)
```

### Caching (Existing SQLite cache, adjusted TTLs)

| Data | TTL | Reason |
|------|-----|--------|
| Restaurant search results | 30 min | Selenium searches are expensive |
| Weather data | 15 min | Balances freshness with API limits |
| AI intent analysis | 60 min | Same input = same output |
| Social search results | 60 min | Blog/PTT content changes slowly |
| Gemini restaurant scores | 30 min | Tied to specific restaurant list |

---

## 6. Frontend Changes

### New: Settings Page (`/settings`)

Key management interface:
- **Textarea** for bulk key import (one key per line, paste-friendly)
- Auto-validates format (`AIza` prefix, length >= 20)
- Test-validates each key with a Gemini call
- Shows key status table: suffix, status (active/cooldown/disabled), daily usage count, cooldown timer

### Updated: Recommendation Result Cards

```
┌─ Restaurant Card ─────────────────────┐
│  🍜 麵屋武藏 台北101店                │
│  ⭐ 4.5 (328則)  💰 約$180-250       │
│  📍 350m · 步行5分鐘                 │
│  💬 PTT/部落格多人推薦               │  ← New: social proof tag
│  🤖 日式豚骨拉麵，符合您的需求        │  ← New: AI reason
│  [Google Maps]                        │
└───────────────────────────────────────┘
```

New fields in recommendation API response:
- `social_proof`: social source tags
- `ai_reason`: one-line recommendation reason
- `estimated_price`: AI-estimated price range
- `relevance_score`: 0-10 score

### API Endpoints

| Endpoint | Method | Change |
|----------|--------|--------|
| `GET /settings` | GET | New: settings page |
| `POST /api/keys/import` | POST | New: bulk import keys |
| `GET /api/keys/status` | GET | New: key status list (suffix only) |
| `DELETE /api/keys/{suffix}` | DELETE | New: remove key |
| Existing recommendation APIs | - | Add social_proof, ai_reason, estimated_price, relevance_score fields |

---

## 7. Migration Plan

### What Gets Deleted

- `modules/dialog_analysis.py` → replaced by `modules/ai/intent_analyzer.py`
- `modules/ai_validator.py` → replaced by `modules/ai/restaurant_scorer.py`
- OpenAI SDK dependency from `requirements.txt`

### What Gets Refactored

- `modules/google_maps.py` (3000 lines) → split into `scraper/google_maps.py`, `scraper/selectors.py`, `geo/geocoding.py`, `geo/distance.py`
- `modules/browser_pool.py` → merged into `scraper/browser_pool.py`
- `modules/ai_recommendation_engine.py` → rewritten as `modules/recommendation_engine.py`

### What Stays

- `modules/sqlite_cache_manager.py` — works fine
- `modules/weather.py` — works fine
- `modules/sweat_index.py` — works fine
- `frontend/ai_lunch.html` — updated, not rewritten
- `main.py` — updated endpoints

### New Dependencies

- `google-generativeai` (Gemini SDK)
- Remove: `openai`
- Remove: `anthropic` (if present, was used as Claude fallback in ai_validator.py)

### Gemini Model

- Model: `gemini-2.5-flash` for all AI calls (intent analysis + restaurant scoring)
- Temperature: 0.1 for intent analysis (deterministic), 0.3 for scoring (slight creativity for reasons)
- Response format: JSON mode where supported

---

## Implementation Status

**Completed: 2026-03-26**

All sections implemented and verified through multi-round AI review panel (Echo/Lisa/Bob/Nova).

| Component | File(s) | Status | Tests |
|-----------|---------|--------|-------|
| Gemini API Key Pool | `modules/ai/gemini_pool.py` | Done | 10 tests |
| Intent Analyzer | `modules/ai/intent_analyzer.py` | Done | 6 tests |
| Restaurant Scorer | `modules/ai/restaurant_scorer.py` | Done | 19 tests |
| Browser Pool | `modules/scraper/browser_pool.py` | Done | - |
| CSS Selectors | `modules/scraper/selectors.py` | Done | - |
| Google Maps Scraper | `modules/scraper/google_maps.py` | Done | - |
| Google Search Scraper | `modules/scraper/google_search.py` | Done | - |
| PTT Scraper | `modules/scraper/ptt_scraper.py` | Done | - |
| Geocoding | `modules/geo/geocoding.py` | Done | - |
| Distance | `modules/geo/distance.py` | Done | - |
| Recommendation Engine | `modules/recommendation_engine.py` | Done | 7 tests |
| Main API | `main.py` | Done | - |
| Settings Page | `frontend/settings.html` | Done | - |
| Chat UI Update | `frontend/ai_lunch.html` | Done | - |
| Integration Tests | `test_system_overhaul.py` | 43/43 pass | - |

### Review Issues Resolved
- Thread-safe per-model api_key (no global genai.configure)
- auto_retry uses tried_keys set (no TOCTOU race)
- GeminiPoolExhausted custom exception
- Social proof weighted scoring per spec
- Google Maps $$ price notation support
- CJK fuzzy matching 2-char minimum
- Capped social proof lookups (max 3, deadline guard)
- Google Search timeout fixed (0.5s sleep)
- Deduplicated _parse_price_avg
