# UX and Performance Optimization

## Problem Statement
1. **PWA 地點遺失**: iOS PWA 用戶透過 GPS 定位後，重新開啟 App 地點會消失，需重新定位。
2. **意圖分析過慢**: Gemini 2.5 Flash 有時因 Prompt 過長導致處理時間超過 20s 觸發超時。
3. **天氣重複請求**: 天氣快取時間過短（15-30m），導致不必要的 API 呼叫。

## Proposed Solution
- **地點持久化**: 將完整的 `userCoords`（含 GPS 座標）存入 `localStorage`。
- **AI 效能優化**: 縮短意圖分析超時至 12s，並精簡 System Prompt 以降低延遲。
- **快取策略調整**: 將天氣資料的 TTL 延長至 3 小時。

## Success Criteria
- [x] PWA 重新開啟後能自動恢復上一次的地點（GPS/手動/對話）。
- [x] 意圖解析在 12s 內完成或快速進入 Fallback 模式。
- [x] 天氣資料快取時間延長至 3 小時。
