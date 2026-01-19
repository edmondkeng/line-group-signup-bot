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
            self.sheet = self.client.open_by_url(self.spreadsheet_url).sheet1
            # 確保標題列存在
            self._init_headers()
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

    def get_all_signups(self):
        """取得所有報名資料 (回傳 list of dict)"""
        return self.sheet.get_all_records()

    def add_signup(self, user_id, user_name, count):
        """新增或更新報名"""
        # 尋找是否已報名
        records = self.get_all_records_with_row_index()
        
        # 簡單邏輯：如果該 User ID 已經存在，則更新他的數量 (累加)
        # 複雜邏輯：如果 User ID 存在，找出該列並更新 "報名人數"
        
        target_row = None
        current_count = 0
        
        for i, record in enumerate(records):
            # i 是 list index, 實際 row number 要 +2 (因為 headers 佔 row 1, 且 list 0-based)
            if str(record.get('User ID')) == user_id:
                target_row = i + 2
                current_count = int(record.get('報名人數', 0))
                break
        
        if target_row:
            # 更新現有報名
            new_count = current_count + count
            self.sheet.update_cell(target_row, 3, new_count)
            self.sheet.update_cell(target_row, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return f"更新報名成功！目前總共報名 {new_count} 人"
        else:
            # 新增報名
            status = "正取" # 暫時預設都正取，之後加入邏輯
            row = [user_id, user_name, count, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""]
            self.sheet.append_row(row)
            return f"報名成功！報名 {count} 人"

    def remove_signup(self, user_id, count):
        """取消報名 (減少人數)"""
        records = self.get_all_records_with_row_index()
        target_row = None
        current_count = 0
        
        for i, record in enumerate(records):
            # 確保 key 存取安全
            uid = str(record.get('User ID',''))
            if uid == user_id:
                target_row = i + 2
                # 處理可能不是數字的情況
                try:
                    current_count = int(record.get('報名人數', 0))
                except ValueError:
                    current_count = 0
                break
        
        if not target_row:
            return "您尚未報名喔！"
        
        new_count = current_count - count
        
        if new_count <= 0:
            # 人數歸零或變負，直接刪除該行
            self.sheet.delete_rows(target_row)
            return "已取消您的所有報名。"
        else:
            # 更新剩餘人數
            self.sheet.update_cell(target_row, 3, new_count)
            self.sheet.update_cell(target_row, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return f"已減少報名人數。目前剩餘 {new_count} 人。"

    def get_summary(self):
        """取得統計資訊文字"""
        records = self.sheet.get_all_records()
        total_count = 0
        summary_lines = []
        
        summary_lines.append("📋 目前報名名單：")
        
        for idx, record in enumerate(records):
             try:
                 c = int(record.get('報名人數', 0))
             except:
                 c = 0
             total_count += c
             name = record.get('顯示名稱', 'Unknown')
             # 簡單處理狀態，之後可做更細
             status = record.get('狀態', '正取')
             summary_lines.append(f"{idx+1}. {name} (+{c}) - {status}")
             
        summary_lines.append("----------------")
        summary_lines.append(f"總累計人數: {total_count} 人")
        
        return "\n".join(summary_lines)

    def get_all_records_with_row_index(self):
        """輔助函式：取得資料並自行處理 (get_all_records 有時標題對不上會怪怪的)"""
        return self.sheet.get_all_records()
