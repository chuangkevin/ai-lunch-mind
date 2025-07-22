# 資料庫遷移 TODO 清單

## 概述
目前專案中存在多個硬編碼的字典資料，應改用 SQLite 等資料庫進行存儲和管理。

## 需要遷移的硬編碼資料

### 1. 地理位置相關資料

#### `modules/sweat_index.py`
- **taiwan_locations 字典** (第 37 行)
  - 包含 50+ 台灣景點、車站、夜市等地點座標
  - 建議資料表結構：
    ```sql
    CREATE TABLE locations (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        display_name TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        type TEXT, -- 景點類型：車站、夜市、古蹟等
        verified BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE location_aliases (
        id INTEGER PRIMARY KEY,
        location_id INTEGER,
        alias_name TEXT,
        FOREIGN KEY (location_id) REFERENCES locations(id)
    );
    ```

- **city_coords 字典** (第 133 行)
  - 台灣各縣市中心座標
  - 建議資料表結構：
    ```sql
    CREATE TABLE cities (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        display_name TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        admin_code TEXT, -- 行政代碼
        region TEXT, -- 區域：北部、中部、南部等
        active_status BOOLEAN DEFAULT TRUE
    );
    ```

#### `modules/taiwan_locations.py`
- **locations 清單** (第 9 行)
  - 58 個台灣主要地點的縣市、座標資料
  - 可整合進上述 locations 資料表

#### `modules/weather.py`
- **city_code_map 字典** (第 16 行)
  - 縣市名稱對應中央氣象署 API 代碼
  - 建議資料表結構：
    ```sql
    CREATE TABLE city_weather_codes (
        id INTEGER PRIMARY KEY,
        city_name TEXT NOT NULL,
        api_code TEXT NOT NULL,
        region TEXT,
        active_status BOOLEAN DEFAULT TRUE,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    ```

### 2. 網路請求相關資料

#### `modules/google_maps.py`
- **USER_AGENTS 清單** (第 39 行)
  - 5 個瀏覽器 User-Agent 字串
  - 建議資料表結構：
    ```sql
    CREATE TABLE user_agents (
        id INTEGER PRIMARY KEY,
        agent_string TEXT NOT NULL,
        browser_type TEXT, -- Chrome, Firefox, Safari等
        active_status BOOLEAN DEFAULT TRUE,
        usage_count INTEGER DEFAULT 0,
        last_used DATETIME,
        success_rate REAL DEFAULT 1.0 -- 成功率追蹤
    );
    ```

## 遷移優點

### 1. 動態管理
- 可在不修改程式碼的情況下新增、修改、刪除資料
- 支援批量更新和匯入功能

### 2. 資料一致性
- 避免多處硬編碼導致的資料不一致
- 統一的資料來源和管理介面

### 3. 擴展性
- 支援更複雜的查詢和篩選
- 可添加更多欄位（如建立時間、更新時間、狀態等）

### 4. 維護性
- 更容易追蹤資料變更歷史
- 支援備份和還原機制

### 5. 效能優化
- 資料庫索引可提升查詢效能
- 支援快取機制

## 實施建議

### 階段一：資料庫設計
1. 設計上述資料表結構
2. 建立資料庫連接和操作類別
3. 實作資料庫初始化腳本

### 階段二：資料遷移
1. 建立資料遷移腳本，將現有硬編碼資料匯入資料庫
2. 添加資料驗證和清理邏輯

### 階段三：程式碼重構
1. 修改各模組以從資料庫讀取資料
2. 添加快取機制以提升效能
3. 實作降級機制（資料庫不可用時的備用方案）

### 階段四：管理介面
1. 建立資料管理介面
2. 實作批量匯入/匯出功能
3. 添加資料驗證和審核機制

## 技術選擇

### 資料庫
- **SQLite**: 適合單機應用，無需額外配置
- **PostgreSQL**: 適合多使用者環境，功能更豐富

### ORM 框架
- **SQLAlchemy**: Python 主流 ORM，功能完整
- **Peewee**: 輕量級 ORM，適合簡單應用

### 快取機制
- **Redis**: 分散式快取，適合多機環境
- **記憶體快取**: 簡單的 Python dict，適合單機

## 注意事項

1. **向下相容性**: 在遷移過程中保持現有 API 介面不變
2. **錯誤處理**: 資料庫不可用時的降級機制
3. **效能考量**: 添加適當的快取機制
4. **資料驗證**: 確保資料的正確性和完整性
5. **備份策略**: 定期備份資料庫資料

## 預估工作量

- 資料庫設計與實作：2-3 工作天
- 資料遷移：1-2 工作天  
- 程式碼重構：3-4 工作天
- 測試與優化：2-3 工作天
- **總計：8-12 工作天**
