from sheets_api import SheetManager
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

def test_google_sheets():
    print("開始測試 Google Sheets 連線...")
    
    cred_file = os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE')
    sheet_url = os.getenv('SPREADSHEET_URL')
    
    if not cred_file or not sheet_url:
        print("錯誤：找不到環境變數設定")
        return

    try:
        manager = SheetManager(cred_file, sheet_url)
        print("連線成功！")
        
        print("\n[測試 1] 新增報名: UserA + 2")
        res = manager.add_signup("UserA_ID", "測試人員A", 2)
        print(f"結果: {res}")
        
        print("\n[測試 2] 查看目前名單")
        print(manager.get_summary())

        print("\n[測試 3] 再新增報名: UserA + 1 (累積變3)")
        res = manager.add_signup("UserA_ID", "測試人員A", 1)
        print(f"結果: {res}")
        
        print("\n[測試 4] 新增另一人: UserB + 5")
        res = manager.add_signup("UserB_ID", "測試人員B", 5)
        print(f"結果: {res}")

        print("\n[測試 5] 取消報名: UserA - 2")
        res = manager.remove_signup("UserA_ID", 2)
        print(f"結果: {res}")
        
        print("\n最終名單:")
        print(manager.get_summary())
        
        print("\n測試完成！請去 Google Sheet 查看實際資料。")

    except Exception as e:
        print(f"發生錯誤: {e}")

if __name__ == "__main__":
    test_google_sheets()
