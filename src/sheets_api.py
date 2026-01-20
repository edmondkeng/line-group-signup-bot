import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import re
from datetime import datetime

class SheetManager:
    def __init__(self, credentials_file, spreadsheet_url):
        self.scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        self.credentials_file = credentials_file
        self.spreadsheet_url = spreadsheet_url
        self.client = None
        self.sheet = None
        self.connect()

    def connect(self):
        """連線至 Google Sheets"""
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_file, self.scope)
            self.client = gspread.authorize(creds)
            # 透過 URL 開啟試算表
            self.doc = self.client.open_by_url(self.spreadsheet_url)
            
            # 嘗試取得指定名稱的主分頁 (優先順序: Signups > 工作表1 > 第一個分頁)
            try:
                self.sheet = self.doc.worksheet("Signups")
            except:
                try:
                    self.sheet = self.doc.worksheet("工作表1")
                except:
                    # 如果都找不到，就使用第一個分頁
                    self.sheet = self.doc.sheet1
            
            # 嘗試取得或建立 Setting 分頁
            try:
                self.setting_sheet = self.doc.worksheet("Setting")
            except:
                self.setting_sheet = self.doc.add_worksheet(title="Setting", rows=20, cols=2)
                self.setting_sheet.append_row(["項目", "內容"])
            
            # 檢查並補齊預設設定
            current_settings = self.get_settings()
            default_settings = {
                "活動標題": "歡樂活動報名",
                "活動說明": "請準時參加！",
                "人數上限": "10",
                "報名功能": "TRUE", # 預設開啟 (CheckBox Checked = TRUE)
                "查詢功能": "TRUE"
            }
            
            rows_to_append = []
            for key, value in default_settings.items():
                if key not in current_settings:
                    rows_to_append.append([key, value])
            
            if rows_to_append:
                for row in rows_to_append:
                    self.setting_sheet.append_row(row)
                    # 如果是開關類的功能，嘗試加入 Checkbox 驗證 (需視 gspread 版本支援度，最簡單是使用者手動設，這裡先只填值)
                    # 註：API 設定 Checkbox 較複雜，這裡先填入 "TRUE" 字串，使用者在 Sheet 上可選取該格 -> 插入 -> 核取方塊


            # 確保主表標題列存在
            self._init_headers()
            
            # 嘗試取得或建立 Stats 分頁
            try:
                self.stats_sheet = self.doc.worksheet("Stats")
            except:
                self.stats_sheet = self.doc.add_worksheet(title="Stats", rows=100, cols=3)
                self.stats_sheet.append_row(["User ID", "Name", "Description"])

        except Exception as e:
            print(f"Google Sheets 連線失敗: {e}")
            raise

    def _init_headers(self):
        """初始化標題列 (如果沒有的話)"""
        if not self.sheet:
            return
        
        headers = ["User ID", "顯示名稱", "報名人數", "狀態", "報名時間", "備註"]
        current_headers = self.sheet.row_values(1)
        if not current_headers:
            self.sheet.append_row(headers)

    def get_settings(self):
        """讀取活動設定"""
        try:
            records = self.setting_sheet.get_all_values()
            settings = {}
            # 跳過標題列，轉成 dict
            for row in records[1:]:
                if len(row) >= 2:
                    settings[row[0]] = row[1]
            return settings
        except:
            return {"活動標題": "活動", "人數上限": "10", "報名功能": "開啟", "查詢功能": "開啟"}

    def is_signup_enabled(self):
        """檢查報名功能是否開啟 (支援 '開啟' 中文或 'TRUE' 布林字串)"""
        settings = self.get_settings()
        val = str(settings.get("報名功能", "TRUE")).upper()
        return val == "開啟" or val == "TRUE"

    def is_query_enabled(self):
        """檢查查詢功能是否開啟 (支援 '開啟' 中文或 'TRUE' 布林字串)"""
        settings = self.get_settings()
        val = str(settings.get("查詢功能", "TRUE")).upper()
        return val == "開啟" or val == "TRUE"

    def add_signup(self, user_id, user_name, count):
        """新增或更新報名 (支援部分正取/部分候補)"""
        return self._reconcile_user_status(user_id, user_name, count)

    def remove_signup(self, user_id, count):
        """取消報名"""
        msg = self._reconcile_user_status(user_id, "", -count)
        # 取消後觸發自動遞補
        self._check_and_promote_waitlist()
        return msg

    def _reconcile_user_status(self, user_id, user_name, delta):
        """核心邏輯：重新計算並分配用戶的 正取/候補 狀態"""
        settings = self.get_settings()
        try:
            max_people = int(settings.get("人數上限", 10))
        except:
            max_people = 10
            
        records = self.get_all_records_with_row_index()
        
        # 1. 蒐集當前用戶資訊與全域正取計數
        user_rows = [] # (index_in_list, record_dict)
        other_approved_count = 0
        current_user_total = 0
        current_user_name = user_name # 優先使用傳入的名字
        
        for i, r in enumerate(records):
            r_uid = str(r.get('User ID'))
            r_count = 0
            try:
                r_count = int(r.get('報名人數', 0))
            except: pass
            
            status = r.get('狀態')
            
            if r_uid == user_id:
                user_rows.append((i, r))
                current_user_total += r_count
                if not current_user_name and r.get('顯示名稱'):
                    current_user_name = r.get('顯示名稱')
            else:
                if status == '正取':
                    other_approved_count += r_count

        # 2. 計算新總數
        new_total = current_user_total + delta
        if new_total < 0: new_total = 0
        
        if new_total == 0 and current_user_total == 0:
            return "您尚未報名喔！"
        
        if new_total == 0:
            # 刪除所有該用戶資料 (從後面刪避免 index 跑掉)
            # 需先將 row index 轉為實際 sheet row index (1-based header + 1-based list = +2)
            rows_to_delete = sorted([x[0] + 2 for x in user_rows], reverse=True)
            for r_idx in rows_to_delete:
                self.sheet.delete_rows(r_idx)
            return "已取消您的所有報名。"

        # 3. 分配 正取 vs 候補
        # 剩餘名額 = 上限 - 其他人已佔用的
        remaining_for_user = max_people - other_approved_count
        if remaining_for_user < 0: remaining_for_user = 0
        
        new_approved = min(new_total, remaining_for_user)
        new_waitlist = new_total - new_approved
        
        # 4. 更新 Google Sheet
        # 策略：重複利用既有的 row，多餘的刪除，不足的 append
        # 分類既有 row
        row_approved_idx = None
        row_waitlist_idx = None
        
        # 尋找既有的正取與候補 row (取第一個找到的)
        for idx, r in user_rows:
            if r.get('狀態') == '正取' and row_approved_idx is None:
                row_approved_idx = idx + 2
            elif r.get('狀態') == '候補' and row_waitlist_idx is None:
                row_waitlist_idx = idx + 2
        
        # 收集需要刪除的 row (多餘的)
        rows_to_delete = []
        used_indices = set()
        if row_approved_idx: used_indices.add(row_approved_idx)
        if row_waitlist_idx: used_indices.add(row_waitlist_idx)
        
        for idx, r in user_rows:
            sheet_idx = idx + 2
            if sheet_idx not in used_indices:
                rows_to_delete.append(sheet_idx)
        
        # 執行刪除 (倒序)
        for r_idx in sorted(rows_to_delete, reverse=True):
            self.sheet.delete_rows(r_idx)
            # 調整 index: 如果刪除的在我們保留的前面，保留的 index 要扣 (稍微複雜，簡單一點：重新整理或相信 gspread)
            # 為了安全，如果發生刪除，後續的 update 操作可能會有風險。
            # 但因為我們通常只有 1-2 筆資料，刪除重來可能更簡單？
            # 不，保留 row 可以保留「報名時間」。
            # 簡單解法：如果刪了 row，我們手動更新 local 的 row_approved_idx / row_waitlist_idx
            if row_approved_idx and r_idx < row_approved_idx: row_approved_idx -= 1
            if row_waitlist_idx and r_idx < row_waitlist_idx: row_waitlist_idx -= 1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 更新/建立 正取 Row
        if new_approved > 0:
            if row_approved_idx:
                self.sheet.update_cell(row_approved_idx, 3, new_approved)
                self.sheet.update_cell(row_approved_idx, 5, timestamp)
            else:
                self.sheet.append_row([user_id, current_user_name, new_approved, "正取", timestamp, ""])
                # Append 後，如果緊接著要 update waitlist，要注意 row count 變了，但 waitlist 是找既有的 index，不受 append 影響
        else:
            # 如果原本有正取但現在變成 0 (例如人數上限變少)，前面已經規劃刪除多餘 row
            # 若 row_approved_idx 仍然存在 (被選為保留的)，則需刪除
            if row_approved_idx:
                self.sheet.delete_rows(row_approved_idx)
                if row_waitlist_idx and row_approved_idx < row_waitlist_idx: row_waitlist_idx -= 1

        # 更新/建立 候補 Row
        if new_waitlist > 0:
            if row_waitlist_idx:
                self.sheet.update_cell(row_waitlist_idx, 3, new_waitlist)
                self.sheet.update_cell(row_waitlist_idx, 5, timestamp)
            else:
                self.sheet.append_row([user_id, current_user_name, new_waitlist, "候補", timestamp, ""])
        else:
             if row_waitlist_idx:
                self.sheet.delete_rows(row_waitlist_idx)

        # 回傳訊息
        status_msg = ""
        if new_approved > 0 and new_waitlist > 0:
            status_msg = f"已更新！ {new_approved} 人正取，{new_waitlist} 人候補。"
        elif new_approved > 0:
            status_msg = f"已更新！ {new_approved} 人正取。"
        elif new_waitlist > 0:
            status_msg = f"已更新！ {new_waitlist} 人排入候補。"
            
        return status_msg

    def _check_and_promote_waitlist(self):
        """檢查並遞補"""
        # 取得所有非重複的候補名單 User IDs
        records = self.sheet.get_all_records()
        waitlist_users = set()
        for r in records:
            if r.get('狀態') == '候補':
                waitlist_users.add(str(r.get('User ID')))
        
        # 逐一重新計算 (因為邏輯共用，直接帶入 delta=0 即可觸發重分配)
        for uid in waitlist_users:
            # 找出該 uid 對應名字 (雖然 _reconcile 會自找，但傳入較保險)
            name = ""
            for r in records:
                if str(r.get('User ID')) == uid:
                    name = r.get('顯示名稱')
                    break
            self._reconcile_user_status(uid, name, 0)
                    
    def get_summary(self):
        """取得統計資訊文字"""
        settings = self.get_settings()
        title = settings.get("活動標題", "活動報名")
        desc = settings.get("活動說明", "")
        
        records = self.sheet.get_all_records()
        total_count = 0
        summary_lines = []
        
        summary_lines.append(f"🎉 {title}")
        if desc:
            summary_lines.append(f"� {desc}")
        summary_lines.append("----------------")
        
        for idx, record in enumerate(records):
             try:
                 c = int(record.get('報名人數', 0))
             except:
                 c = 0
             status = record.get('狀態', '正取')
             if status == '正取':
                 total_count += c
             
             name = record.get('顯示名稱', 'Unknown')
             # 簡單排版
             icon = "✅" if status == "正取" else "⏳"
             summary_lines.append(f"{idx+1}. {name} (+{c}) {icon}{status}")
             
        summary_lines.append("----------------")
        summary_lines.append(f"目前正取人數: {total_count} / 上限 {settings.get('人數上限', 10)}")
        
        return "\n".join(summary_lines)

    def get_all_records_with_row_index(self):
        """輔助函式：取得資料並自行處理 (get_all_records 有時標題對不上會怪怪的)"""
        return self.sheet.get_all_records()

    def query_stats(self, user_id=None, name=None):
        """查詢統計資料"""
        if not self.stats_sheet:
            return []
            
        records = self.stats_sheet.get_all_records()
        results = []
        
        for record in records:
            # 根據 User ID 查詢
            if user_id and str(record.get('User ID')) == user_id:
                results.append(f"{record.get('Description')} ({record.get('Name')})")
            # 根據 Name 查詢 (如果不完全匹配，可以改用 in)
            elif name and str(record.get('Name')) == name:
                results.append(f"{record.get('Description')} ({record.get('Name')})")
                
        return results

    def get_all_stats(self):
        """取得所有統計資料"""
        if not self.stats_sheet:
            return "尚無資料"
            
        records = self.stats_sheet.get_all_records()
        if not records:
             return "尚無資料"

        lines = ["📊 統計資料一覽:"]
        for record in records:
            lines.append(f"{record.get('Name')}: {record.get('Description')}")
            
        return "\n".join(lines)
