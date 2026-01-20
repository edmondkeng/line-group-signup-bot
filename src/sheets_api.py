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
            self.sheet = self.doc.sheet1
            
            # 嘗試取得或建立 Setting 分頁
            try:
                self.setting_sheet = self.doc.worksheet("Setting")
            except:
                self.setting_sheet = self.doc.add_worksheet(title="Setting", rows=10, cols=2)
                self.setting_sheet.append_row(["項目", "內容"])
                self.setting_sheet.append_row(["活動標題", "歡樂活動報名"])
                self.setting_sheet.append_row(["活動說明", "請準時參加！"])
                self.setting_sheet.append_row(["人數上限", "10"])
                self.setting_sheet.append_row(["報名功能", "開啟"])
                self.setting_sheet.append_row(["查詢功能", "開啟"])

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
        """檢查報名功能是否開啟"""
        settings = self.get_settings()
        return settings.get("報名功能", "開啟") == "開啟"

    def is_query_enabled(self):
        """檢查查詢功能是否開啟"""
        settings = self.get_settings()
        return settings.get("查詢功能", "開啟") == "開啟"

    def add_signup(self, user_id, user_name, count):
        """新增或更新報名 (包含滿額判斷)"""
        # 取得設定與目前名單
        settings = self.get_settings()
        try:
            max_people = int(settings.get("人數上限", 10))
        except:
            max_people = 10
            
        records = self.get_all_records_with_row_index()
        
        # 計算目前正取人數
        current_total = 0
        for r in records:
            if r.get('狀態') == '正取':
                try:
                    current_total += int(r.get('報名人數', 0))
                except:
                    pass

        target_row = None
        user_current_count = 0
        
        # 找尋使用者是否已報名
        for i, record in enumerate(records):
            if str(record.get('User ID')) == user_id:
                target_row = i + 2
                user_current_count = int(record.get('報名人數', 0))
                break
        
        if target_row:
            # 更新現有報名
            new_count = user_current_count + count
            # 這裡簡化邏輯：如果之前是候補，現在還是候補；如果是正取，增加的人數是否導致爆量?
            # 為求簡單，我們重新評估該用戶狀態：只要目前總人數(扣掉他原本的) + 新人數 <= 上限，就是正取
            
            # 但這樣太複雜，Line群組報名通常是：只要還沒滿，報名就是正取。
            # 如果已經滿了，新的人就是候補。
            # 如果是「增加」報名，通常直接疊加。
            
            # 最簡單邏輯：
            # 1. 計算剩餘名額
            remaining = max_people - (current_total - (user_current_count if str(records[target_row-2].get('狀態')) == '正取' else 0))
            
            # 判斷狀態
            # 如果本來就是候補，或是這次報名後會超過上限 -> 簡易處理：視為新狀態
            # 但通常我們會希望：正取的人加人，如果不超過上限，繼續正取。
            
            new_status = "正取"
            # 這裡邏輯可以很複雜，先做簡易版：
            # 只要還有名額，就是正取。如果名額滿了，就是候補。
            # 注意：這裡沒處理「部分正取部分候補」的情況 (如剩1個名額但報+2)，通常直接讓最後這個人變候補或正取。
            
            if current_total - (user_current_count if str(records[target_row-2].get('狀態')) == '正取' else 0) + new_count > max_people:
                 new_status = "候補"
            
            # 保持原狀態邏輯 (如果已經是正取，通常不會因為加人變候補，除非非常嚴格)
             # 我們採用：如果原本是正取，就維持正取 (或是提示已滿)。
            if str(records[target_row-2].get('狀態')) == '正取':
                new_status = "正取" # 確保已報名者權益
            
            self.sheet.update_cell(target_row, 3, new_count)
            self.sheet.update_cell(target_row, 4, new_status)
            self.sheet.update_cell(target_row, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return f"更新成功！您目前報名 {new_count} 人 ({new_status})"
        else:
            # 新增報名
            if current_total + count <= max_people:
                status = "正取"
            else:
                status = "候補"
                
            row = [user_id, user_name, count, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""]
            self.sheet.append_row(row)
            return f"報名成功！您報名 {count} 人 ({status})"

    def remove_signup(self, user_id, count):
        """取消報名"""
        records = self.get_all_records_with_row_index()
        target_row = None
        current_count = 0
        
        for i, record in enumerate(records):
            if str(record.get('User ID')) == user_id:
                target_row = i + 2
                try:
                    current_count = int(record.get('報名人數', 0))
                except:
                    current_count = 0
                break
        
        if not target_row:
            return "您尚未報名喔！"
        
        new_count = current_count - count
        
        if new_count <= 0:
            self.sheet.delete_rows(target_row)
            # 刪除後，這裡可以做「自動遞補」邏輯 (檢查候補名單並轉正)
            # 為了避免過於複雜，先不做自動遞補通知，只做刪除
            self._check_and_promote_waitlist()
            return "已取消您的所有報名。"
        else:
            self.sheet.update_cell(target_row, 3, new_count)
            self.sheet.update_cell(target_row, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return f"已減少報名人數。您目前保留 {new_count} 人。"

    def _check_and_promote_waitlist(self):
        """檢查是否有空缺並遞補 (簡易版)"""
        # 讀取設定
        settings = self.get_settings()
        try:
            max_people = int(settings.get("人數上限", 10))
        except:
            max_people = 10
            
        records = self.get_all_records_with_row_index()
        current_total = 0
        # 計算正取人數
        for r in records:
            if r.get('狀態') == '正取':
                 try:
                    current_total += int(r.get('報名人數', 0))
                 except: pass

        # 找候補
        if current_total < max_people:
            for i, r in enumerate(records):
                if r.get('狀態') == '候補':
                    # 嘗試遞補
                    count = int(r.get('報名人數', 1))
                    if current_total + count <= max_people:
                        # 轉正
                        self.sheet.update_cell(i + 2, 4, "正取")
                        current_total += count
                        # 實務上這裡應該要主動通知該用戶，但 Line 無法主動推播 (除非付費或好友)，所以只能被動更新顯示
                    
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
