from linebot.models import TextSendMessage
from sheets_api import SheetManager
import os
import re

# 初始化 SheetManager
# 注意：在生產環境中，建議使用 Singleton 或全域變數避免重複連線
# 在這裡我們會在第一次呼叫時初始化，簡單處理
_sheet_manager = None

def get_sheet_manager():
    global _sheet_manager
    if _sheet_manager is None:
        cred_file = os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE')
        sheet_url = os.getenv('SPREADSHEET_URL')
        if cred_file and sheet_url:
            try:
                _sheet_manager = SheetManager(cred_file, sheet_url)
                print("SheetManager initialized successfully.")
            except Exception as e:
                print(f"Failed to initialize SheetManager: {e}")
    return _sheet_manager

def handle_text_message(event, line_bot_api):
    """
    處理接收到的文字訊息，整合報名邏輯
    """
    text = event.message.text.strip()
    user_id = event.source.user_id
    group_id = getattr(event.source, 'group_id', None)
    
    # 1. 判斷指令格式
    # 支援: +1, +2, +10, -1, -2, ?
    # 忽略一般對話訊息
    
    match_plus = re.match(r'^\+(\d+)$', text)
    match_minus = re.match(r'^\-(\d+)$', text)
    is_query = (text == '?')

    if not (match_plus or match_minus or is_query):
        return # 非指令，直接忽略

    sheet = get_sheet_manager()
    if not sheet:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="系統錯誤：無法連線至報名表，請聯絡管理員。")
        )
        return

    # 2. 取得使用者暱稱 (Display Name)
    user_name = "未知用戶"
    try:
        # 如果是在群組中，嘗試取得該群組內的成員暱稱
        if group_id:
            profile = line_bot_api.get_group_member_profile(group_id, user_id)
        else:
            # 如果是私訊 (開發測試時)，取得個人資料
            profile = line_bot_api.get_profile(user_id)
        user_name = profile.display_name
    except Exception as e:
        print(f"無法取得使用者個資: {e}")
        # 如果無法取得 (例如沒加好友)，可能需請用戶自己輸入，這裡先用預設值

    reply_msg = ""

    # 3. 執行邏輯
    try:
        if match_plus:
            count = int(match_plus.group(1))
            msg = sheet.add_signup(user_id, user_name, count)
            # 成功後附加目前名單
            summary = sheet.get_summary()
            reply_msg = f"{msg}\n\n{summary}"

        elif match_minus:
            count = int(match_minus.group(1))
            msg = sheet.remove_signup(user_id, count)
            summary = sheet.get_summary()
            reply_msg = f"{msg}\n\n{summary}"

        elif is_query:
            summary = sheet.get_summary()
            reply_msg = summary

        # 4. 回覆 Line 訊息
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_msg)
        )

    except Exception as e:
        print(f"處理指令時發生錯誤: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="處理您的請求時發生錯誤，請稍後再試。")
        )
