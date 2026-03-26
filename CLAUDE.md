# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Shell Tools Usage Guidelines

⚠️ **IMPORTANT**: Use the following specialized tools instead of traditional Unix commands:

| Task Type | Must Use | Do Not Use |
|-----------|----------|------------|
| Find Files | `fd` | `find`, `ls -R` |
| Search Text | `rg` (ripgrep) | `grep`, `ag` |
| Analyze Code Structure | `ast-grep` | `grep`, `sed` |
| Interactive Selection | `fzf` | Manual filtering |
| Process JSON | `jq` | `python -m json.tool` |
| Process YAML/XML | `yq` | Manual parsing |

### Tool Descriptions

**fd** - Fast file finding
- 3-10x faster than traditional find, automatically respects .gitignore
- Example: `fd main.go` to quickly locate files

**rg (ripgrep)** - High-performance text search
- Faster than grep, searches entire repositories efficiently
- Use for finding function calls and code references

**ast-grep** - Structural code search
- Searches code syntax trees (AST) rather than plain text
- Example: Find all variable declarations or deprecated API calls

**fzf** - Interactive fuzzy finder
- Combine with other tools: `fd | fzf`
- Provides interactive selection with fuzzy matching

**jq** - JSON processor
- Parse and filter JSON data efficiently
- Example: `jq '.[] | select(.price > 0.5)'`

**yq** - YAML/XML processor
- Process configuration files (Kubernetes, CI/CD)
- Example: `yq -e '.spec.template' deploy.yaml`

## Project Overview

AI-powered lunch recommendation system that integrates ChatGPT semantic analysis, weather data, sweat index calculations, and Google Maps restaurant search to provide personalized dining suggestions based on location, weather conditions, and user preferences.

**Tech Stack:** Python 3.11+, FastAPI, Selenium, OpenAI GPT-4o-mini, SQLite

## Development Commands

### Running the Application

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Start the development server (default port 5000)
python main.py

# Access the main chat interface
http://localhost:5000/ai_lunch
```

### Testing

```bash
# Run AI validation tests
python test_ai_validation.py

# Run performance optimization tests (full suite)
python test_performance_optimization.py

# Run quick performance tests
python test_performance_quick.py

# Run SQLite cache tests
python test_sqlite_cache.py

# Run specific scenario tests
python test_ramen_scenario.py
python test_distance_run.py
```

### Environment Setup

Required environment variables in `.env`:
```bash
OPENAI_API_KEY=your_openai_api_key
CWB_API_KEY=your_cwb_api_key  # Optional, for real weather data
```

## Architecture Overview

### Core System Flow

1. **User Input Processing** (`modules/dialog_analysis.py`): ChatGPT analyzes natural language input to extract location, food preferences, and intent
2. **Weather & Sweat Index** (`modules/weather.py`, `modules/sweat_index.py`): Fetches weather data and calculates comfort index to determine search radius (500m-3000m)
3. **Search Planning** (`modules/ai_recommendation_engine.py`): Generates search keywords with fallback strategies (ChatGPT → keyword detection → time-based → weather-based)
4. **Restaurant Search** (`modules/google_maps.py`): Selenium-based parallel search across multiple keywords with browser pooling
5. **AI Validation** (`modules/ai_validator.py`): Three-layer validation (location, intent matching, recommendation quality)
6. **Result Ranking**: Distance-prioritized scoring with weather adaptability and price considerations

### Key Modules

**`modules/ai_recommendation_engine.py`** - Main orchestration engine
- Coordinates the entire recommendation pipeline
- Implements staged response (search plan → actual search)
- Manages parallel keyword searches with ThreadPoolExecutor
- Dynamic search radius based on sweat index: ≥8 → 500m, 6-7 → 1km, 4-5 → 2km, ≤3 → 3km

**`modules/dialog_analysis.py`** - ChatGPT integration
- Natural language understanding for extracting food preferences, location, and context
- Intelligent keyword expansion (e.g., "拉麵" → ["拉麵", "日式拉麵", "豚骨拉麵"])
- Supports both new (1.0+) and old (0.x) OpenAI SDK versions

**`modules/google_maps.py`** - Restaurant search engine
- Selenium automation for Google Maps searches
- Short URL expansion for Google Maps links (maps.app.goo.gl, g.co/kgs)
- Multi-layered URL fallback strategy for reliability
- Geocoding with disambiguation support

**`modules/sqlite_cache_manager.py`** - Performance optimization
- Persistent SQLite-based caching (replaces in-memory cache)
- TTL-based expiration: restaurants (30m), weather (15m), AI analysis (60m)
- Thread-safe with cache statistics tracking
- Database: `cache.db` in project root

**`modules/browser_pool.py`** - Browser resource management
- Pre-initialized Chrome instances (default pool size: 2)
- Prevents 30-60s startup overhead on each search
- Auto-cleanup of idle browsers (5min timeout)
- Context manager pattern for safe resource handling

**`modules/ai_validator.py`** - Quality assurance
- Location validation: Verifies extracted landmarks and coordinates
- Intent matching: Detects over-generalization (e.g., "拉麵" → "麵食" is too broad)
- Recommendation quality: Assesses diversity, coverage, and satisfaction

**`modules/sweat_index.py`** - Weather-based optimization
- Calculates discomfort index from temperature, humidity, wind speed
- Contains hardcoded Taiwan landmark coordinates (`taiwan_locations` dict at line 37)
- City coordinates mapping (`city_coords` dict at line 133)
- Note: See `DATABASE_MIGRATION_TODO.md` for planned database migration

**`modules/weather.py`** - CWB API integration
- Central Weather Bureau API client
- City code mapping (`city_code_map` dict at line 16)
- Fetches temperature, humidity, wind speed, rain probability

### FastAPI Endpoints

**Main Recommendation APIs:**
- `GET /chat-recommendation` - Staged conversational recommendation (phase: "start" | "search")
- `POST /chat/recommend` - JSON-based staged recommendation
- `GET /ai-lunch-recommendation` - Direct recommendation with location + user_input

**Support APIs:**
- `GET /weather` - Weather query (supports lat/long or location name)
- `GET /sweat-index` - Sweat index calculation
- `GET /restaurants` - Direct restaurant search
- `GET /location-options` - Location disambiguation

**Pages:**
- `/` - Homepage
- `/ai_lunch` - Main chat interface (primary UI)
- `/restaurant` - Restaurant search page
- `/weather_page` - Weather query page
- `/sweat_index` - Sweat index page

## Important Implementation Details

### Caching Strategy

The system uses SQLite for persistent caching to improve performance:
- **Restaurant searches:** 30-minute TTL (searches are expensive due to Selenium)
- **Weather data:** 15-minute TTL (balances freshness with API rate limits)
- **AI analysis:** 60-minute TTL (ChatGPT analysis is deterministic for same inputs)
- Cache keys use SHA256 hashing of parameters
- Database location: `cache.db` (excluded from git)

### Browser Pool Management

Browser instances are precious resources. Key points:
- Pool initializes 2 Chrome instances on startup
- Use `browser_pool.get_browser()` context manager for safe access
- Don't create new Selenium drivers directly in `google_maps.py`
- Browsers are reused across searches to avoid 30-60s startup penalty
- Auto-cleanup after 5 minutes of idle time

### ChatGPT Integration

The system supports both OpenAI SDK versions:
- Detects version on startup (checks for `openai.OpenAI` class)
- New version (1.0+): Uses `OpenAI` client class
- Old version (0.x): Uses module-level `openai.api_key`
- Global variable `OPENAI_VERSION` tracks which is in use
- Model: `gpt-4o-mini` for cost efficiency

### Search Keyword Strategy

Multi-layered fallback for robustness:
1. **ChatGPT analysis** - Primary method, most intelligent
2. **Keyword detection** - Regex matching against `FOOD_PATTERNS` dict
3. **Time-based** - Breakfast/lunch/dinner based on current hour
4. **Weather-based** - Hot weather → cold foods, cold weather → hot foods
5. **Ultimate fallback** - ["熱炒", "便當", "麵食"]

### Distance Calculation

The system calculates distance in two ways:
- **Direct distance** - Haversine formula (as-the-crow-flies)
- **Walking distance** - Google Maps walking route API (when available)
- Walking distance is preferred for ranking but has rate limits

### AI Validation System

Three-stage validation runs automatically:
1. **Location extraction validation** - Ensures correct landmark identification
2. **Plan validation** - Checks if search keywords match user intent; detects over-generalization
3. **Result validation** - Assesses recommendation diversity and quality

Validation warnings are logged but don't block the recommendation flow.

## Development Notes

### Hardcoded Data (Future Migration)

Several modules contain hardcoded dictionaries that should be migrated to database:
- `modules/sweat_index.py`: `taiwan_locations` (50+ landmarks), `city_coords` (city centers)
- `modules/weather.py`: `city_code_map` (CWB API codes)
- `modules/google_maps.py`: `USER_AGENTS` (browser strings)
- `modules/dialog_analysis.py`: `FOOD_PATTERNS` (food type regex)

See `DATABASE_MIGRATION_TODO.md` for detailed migration plan.

### Performance Targets

System aims for <6s total recommendation time:
- Plan generation: <1s
- Parallel searches: 3-4s (with browser pool + cache)
- Result ranking: <1s

### Selenium Configuration

Chrome options optimized for speed:
- `--disable-images` - Skip image loading
- `--disable-javascript` - Not needed for Maps (pre-rendered HTML)
- `--disable-gpu` - Reduce resource usage
- Custom user agent to avoid bot detection
- Runs in foreground (headless mode causes detection issues)

### Common Issues

**Selenium WebDriverException**: Usually means Chrome/Chromedriver version mismatch or missing Chrome installation. Install Chrome browser if running in container.

**OpenAI API errors**: Check `OPENAI_API_KEY` in `.env`. System will fail without it (no graceful degradation).

**Cache database locked**: SQLite has limited concurrency. The `_lock` in `SQLiteCacheManager` handles this, but very high load may cause timeouts.

**Browser pool exhausted**: Default pool size is 2. Increase `pool_size` in `BrowserPool.__init__()` if needed, but be aware of memory usage.

## Testing Strategy

Performance tests verify:
- Cache hit/miss ratios
- Browser pool reuse efficiency
- End-to-end recommendation timing
- Parallel search correctness

AI validation tests check:
- Location extraction accuracy
- Intent matching quality
- Over-generalization detection
- Recommendation diversity

Run `test_performance_optimization.py` for comprehensive benchmarking before and after changes.
