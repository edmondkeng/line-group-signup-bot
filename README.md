# Line Group Signup Bot

這是一個 Line 群組專用的活動報名機器人，使用 Google Sheets 作為資料庫。

## 功能
- **+1, +N**: 報名活動 (支援多人)
- **-1, -N**: 取消報名 (支援多人)
- **?**: 查詢目前狀態

## 安裝與執行

1. **安裝相依套件**
   ```bash
   pip install -r requirements.txt
   ```

2. **設定環境變數**
   複製 `.env.example` 為 `.env` 並填入以下資訊：
   - `LINE_CHANNEL_ACCESS_TOKEN`: Line Developers Console 取得
   - `LINE_CHANNEL_SECRET`: Line Developers Console 取得
   - `GOOGLE_SHEETS_CREDENTIALS_FILE`: google_credentials.json 的路徑

3. **啟動伺服器**
   ```bash
   python src/app.py
   ```

## 目錄結構
- `src/app.py`: Flask 主程式與 Webhook 入口
- `src/bot_logic.py`: 機器人對話邏輯核心
- `src/sheets_api.py`: Google Sheets 操作介面 (開發中)
