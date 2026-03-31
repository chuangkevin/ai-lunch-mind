# AI Lunch Mind — Full System Redesign

## Summary

Complete UI/UX overhaul and flow redesign. Replace the current chat-style interface with a search-engine-style dark theme UI. Fix all data reliability issues. Redesign the recommendation pipeline to show real-time progress with step-by-step indicators.

## Design Decisions (User Approved)

| Item | Choice |
|------|--------|
| UI Style | Dark tech theme — `#111827` background, `#7c3aed` purple accent, `#fbbf24` gold ratings |
| Layout | Search engine style — input top, analysis status bar, result grid below |
| Progress | Step dots — 4 phases (Intent → Weather → Search → Score), checkmark animation |
| Restaurant Cards | Full cards — all info visible, no collapse needed |
| Device | Desktop-first, responsive to mobile |
| Grid | Desktop 2-column, mobile 1-column |

---

## 1. Page Structure

```
┌─────────────────────────────────────────────────────┐
│  🍜 AI 午餐推薦    [📍 大安區敦化南路 ✕] [⚙️ 設定] │  ← Header
├─────────────────────────────────────────────────────┤
│  [想吃什麼？                              ] [推薦]  │  ← Input bar
├─────────────────────────────────────────────────────┤
│  ○意圖 → ○天氣 → ●搜尋中... → ○排序     3.2s      │  ← Progress bar
├─────────────────────────────────────────────────────┤
│  📍大安區 | 🔑拉麵,日式 | 🌡28°C | 😅6 | 📏800m   │  ← Analysis summary
├─────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐                 │
│  │ 麵屋武藏     │  │ 一蘭拉麵     │                 │  ← Result grid
│  │ ⭐4.5  3分   │  │ ⭐4.3  5分   │                 │     (2-col desktop)
│  │ $150-250     │  │ $200-350     │                 │
│  │ 🤖 湯頭濃郁 │  │ 🔥PTT 推薦  │                 │
│  │ 🚶步行導航  │  │ 🚶步行導航  │                 │
│  └──────────────┘  └──────────────┘                 │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │ 武藏家       │  │ 豚王拉麵     │                 │
│  │ ...          │  │ ...          │                 │
│  └──────────────┘  └──────────────┘                 │
├─────────────────────────────────────────────────────┤
│  ✅ 共推薦 6 間餐廳 · 800m內沒有結果，顯示最近的   │  ← Summary footer
└─────────────────────────────────────────────────────┘
```

### Header
- App title left-aligned
- Current location pill (click to edit, × to clear)
- Settings gear icon right-aligned
- Dark background `#1f2937`, purple accent text

### Input Bar
- Full-width text input with placeholder "想吃什麼？午餐、拉麵、200元以內的便當..."
- Purple gradient submit button
- GPS button (📍) left of input
- Stays fixed at top (not part of scroll area)

### Progress Bar
- 4 steps: 意圖分析 → 天氣查詢 → 餐廳搜尋 → 評分排序
- Each step: circle dot (pending=gray outline, active=pulse animation, done=purple fill+checkmark)
- Connected by lines (done=purple, pending=gray)
- Right-aligned elapsed time counter
- Hidden before first search, visible during/after

### Analysis Summary
- Single row of pill tags showing analysis results
- Each pill: icon + value (e.g., "📍 大安區", "🔑 拉麵, 日式", "🌡️ 28°C", "😅 6/10", "📏 800m")
- Rain warning: if >= 50%, show "🌧️ 65% 記得帶傘！" in red pill
- Hidden before first search

### Result Grid
- CSS Grid: `grid-template-columns: repeat(2, 1fr)` on desktop, `1fr` on mobile
- Breakpoint: 768px
- Gap: 16px
- Cards animate in one by one (fade-in + slide-up)

### Summary Footer
- Shows after all cards rendered
- Total count + timing + any distance expansion message

---

## 2. Restaurant Card Design

```
┌─────────────────────────────────────────┐
│  麵屋武藏                    ⭐ 4.5     │  ← Name + rating badge
│  日式拉麵 · 大安區                       │  ← Category + district
│                                          │
│  🚶 3分 (250m)  💰 $150-250             │  ← Distance + price pills
│  🔥 PTT 推薦  💬 Dcard                  │  ← Social proof pills
│                                          │
│  📍 大安區敦化南路二段81巷38號           │  ← Full address
│                                          │
│  ┃ 湯頭濃郁，麵條Q彈，是附近上班族      │  ← AI reason (purple left border)
│  ┃ 午餐首選。                            │
│                                          │
│  [🚶 步行導航]  [🗺️ Google Maps]        │  ← Action buttons
└─────────────────────────────────────────┘
```

### Card Styling
- Background: `#1f2937`
- Border: `1px solid #374151`, hover: `1px solid #6366f1`
- Border-radius: `14px`
- Padding: `16px`

### Card Elements (top to bottom)
1. **Header row**: Restaurant name (white, bold 15px) + rating badge (gold `#fbbf24` background)
2. **Subtitle**: Food type + district (gray `#9ca3af`, 12px)
3. **Info pills row**: Walking distance (green bg), price (purple bg), social proof (purple bg)
4. **Address**: Full address with 📍 icon (gray, 12px)
5. **AI reason**: Left purple border, gray text, 12px
6. **Action buttons**: Walking navigation + Google Maps links (purple text, 12px)

### Social Proof Pills
- PTT: `background:#4c1d95; color:#c4b5fd`
- Dcard: `background:#4c1d95; color:#c4b5fd`
- Clickable: opens the social media link

### Distance Display
- Always show walking time + distance: "🚶 3分 (250m)"
- If distance unknown: show "📍 地址已知" (don't show fake distance)
- Green pill: `background:#064e3b; color:#6ee7b7`

### Price Display
- Show price range from Google Maps or Gemini enrichment
- Purple pill: `background:#1e1b4b; color:#a5b4fc`
- If no price data: don't show pill (not "N/A")

---

## 3. SSE Pipeline (Unchanged Backend, New Frontend Rendering)

### Phase 1: Intent Analysis (~1s)
- Progress: step 1 active (pulse)
- SSE events: `thinking(intent)` → `intent(location, keywords, budget)`
- UI: Progress dot 1 fills purple + checkmark, analysis pills appear

### Phase 2: Weather (~1s)
- Progress: step 2 active
- SSE events: `weather(temp, humidity, sweat, rain)`
- UI: Progress dot 2 fills, weather pills appear, distance pill updates

### Phase 3: Search (~3-5s)
- Progress: step 3 active
- SSE events: `thinking(search)` → `thinking(search_done)` → `thinking(enrich)` → `thinking(distance)`
- UI: Progress dot 3 pulse during entire search phase

### Phase 4: Results (~0.5s)
- Progress: step 4 active briefly, then all 4 done
- SSE events: `restaurant(0)`, `restaurant(1)`, ... → `done(total)`
- UI: Cards fade in one by one (100ms delay between), progress shows all checkmarks
- Summary footer appears after last card

### Error Handling
- Timeout: Show "搜尋超時" in red banner, keep any partial results
- No results: Show "附近沒有符合的餐廳，試試換個關鍵字" with retry button
- Distance expanded: Show "800m 內沒有結果，顯示最近的 N 間" as info banner

---

## 4. Data Flow Constraints

### Gemini is ONLY for:
- Intent analysis (extract location, keywords, budget from user message)
- Enrichment (add AI reason + filter non-restaurants for existing Google Maps results)
- NEVER generates restaurant names, addresses, or ratings

### Real Data Sources:
- Restaurant names, addresses, ratings: **Google Maps (Selenium headless)**
- Walking distance: **ArcGIS geocode + geodesic formula**
- Weather: **CWB API via sweat_index module**
- Social proof: **Google search (Selenium) for Dcard/PTT links**

### Distance Rules:
- Good weather (sweat < 5, rain < 50%): max 800m (10 min walk)
- Bad weather (sweat >= 7 OR rain >= 50%): max 400m (5 min walk)
- Moderate: max 600m (8 min walk)
- If nothing within range: auto-expand, show closest N with explanation

---

## 5. Settings Page Redesign

Minimal changes — keep functional, match dark theme:
- Same layout: textarea import, key status table, usage stats
- Restyle to dark theme (`#111827` background, `#1f2937` cards)
- Add link back to main page in header

---

## 6. Files to Create/Modify

### New Files
- `frontend/ai_lunch_v2.html` — Complete rewrite of main UI

### Modified Files
- `main.py` — Update `/ai_lunch` route to serve new HTML; SSE endpoint stays same
- `frontend/settings.html` — Restyle to dark theme

### Unchanged
- `modules/fast_search.py` — Backend search pipeline stays
- `modules/ai/` — All AI modules stay
- `modules/scraper/` — All scraper modules stay
- `main.py` SSE endpoint — Event format stays same, frontend rendering changes

---

## 7. Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#111827` | Page background |
| `--bg-card` | `#1f2937` | Card/panel background |
| `--bg-input` | `#374151` | Input fields |
| `--border` | `#374151` | Card borders |
| `--border-active` | `#6366f1` | Hover/active borders |
| `--accent` | `#7c3aed` | Primary accent (buttons, progress) |
| `--accent-light` | `#a78bfa` | Secondary accent |
| `--text-primary` | `#f9fafb` | Main text |
| `--text-secondary` | `#9ca3af` | Secondary text |
| `--text-muted` | `#6b7280` | Muted text |
| `--rating` | `#fbbf24` | Rating gold |
| `--success` | `#6ee7b7` | Distance/success green |
| `--danger` | `#ef4444` | Error/rain warning red |
| `--pill-green-bg` | `#064e3b` | Distance pill |
| `--pill-purple-bg` | `#1e1b4b` | Price/social pill |
| `--pill-blue-bg` | `#1e3a5f` | Weather pill |

---

## Implementation Status

**Implemented: 2026-03-31**

| Component | File | Status |
|-----------|------|--------|
| New UI (dark theme, search engine layout) | `frontend/ai_lunch_v2.html` | Done |
| Settings dark theme | `frontend/settings.html` | Done |
| Route update | `main.py` | Done |
| SSE endpoint | `main.py` | Unchanged, verified compatible |

### Self-Test Results
- `/ai_lunch` serves dark theme page with correct colors (#111827, #7c3aed) — verified
- SSE events (intent/weather/analysis/search) format correct — verified via curl
- Gemini intent analysis returns location + keywords correctly — verified
- Settings page restyled to matching dark theme — verified
