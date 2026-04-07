# Tasks - UX and Performance Optimization

## ✅ UX Fixes
- [x] 修改 `frontend/ai_lunch_v2.html`：將完整 `userCoords` 存入 `localStorage`
- [x] 修改 `frontend/ai_lunch_v2.html`：啟動時從 `user_location_info` 恢復地點
- [x] 修改 `frontend/ai_lunch_v2.html`：向下兼容舊版 `manual_location`

## ✅ Performance Optimization
- [x] 修改 `main.py`：將意圖分析超時縮短至 12s
- [x] 修改 `modules/ai/intent_analyzer.py`：精簡 `_SYSTEM_PROMPT`
- [x] 修改 `modules/sqlite_cache_manager.py`：將天氣快取 TTL 改為 180 分鐘 (3h)
- [x] 修改 `src/modules/cache.ts`：同步延長天氣快取 TTL

## ✅ Documentation
- [x] 更新 `CLAUDE.md`：快取策略與效能說明
- [x] 建立 `openspec/changes/ux-and-perf-optimization/` 記錄變更
