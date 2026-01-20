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
    
    # 1. 判斷指令格式
    # 支援: 
    #   報名: +N, -N, Name+N, Name-N
    #   查詢: ?, $, Name$, $$
    
    # 報名 Regex
    match_plus = re.match(r'^((?P<name>[^+-]+))?\+(?P<num>\d+)$', text)
    match_minus = re.match(r'^((?P<name>[^+-]+))?\-(?P<num>\d+)$', text)
    is_query_signup = (text == '?')

    # 資料查詢 Regex
    match_query_self = (text == '$')
    match_query_all = (text == '$$')
    match_query_other = re.match(r'^([^$]+)\$$', text)

    sheet = get_sheet_manager()
    if not sheet:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="系統錯誤：無法連線至報名表，請聯絡管理員。")
        )
        return

    reply_msg = ""
    
    try:
        # --- 處理報名相關指令 ---
        if match_plus or match_minus or is_query_signup:
            # 檢查報名功能開關
            if not sheet.is_signup_enabled():
                if is_query_signup:
                     # 允許看名單，但提示已關閉? 或者都不允許? 
                     # 依照需求: 報名開關如關閉, +, -, ? 功能無效
                     # line_bot_api.reply_message(event.reply_token, TextSendMessage(text="報名系統目前已關閉。"))
                     return # 直接忽略
                return
        
            if match_plus:
                count = int(match_plus.group('num'))
                name_prefix = match_plus.group('name')
                
                target_id = user_id
                target_name = "未知用戶"
                
                if name_prefix:
                    # 代理報名
                    target_id = f"PROXY_{name_prefix}"
                    target_name = name_prefix
                else:
                    # 本人報名 -> 取得 Profile
                    try:
                        if group_id:
                            profile = line_bot_api.get_group_member_profile(group_id, user_id)
                        else:
                            profile = line_bot_api.get_profile(user_id)
                        target_name = profile.display_name
                    except:
                        pass
                
                msg = sheet.add_signup(target_id, target_name, count)
                summary = sheet.get_summary()
                reply_msg = f"{msg}\n\n{summary}"

            elif match_minus:
                count = int(match_minus.group('num'))
                name_prefix = match_minus.group('name')
                
                target_id = user_id
                
                if name_prefix:
                     # 代理取消
                     target_id = f"PROXY_{name_prefix}"
                
                msg = sheet.remove_signup(target_id, count)
                summary = sheet.get_summary()
                reply_msg = f"{msg}\n\n{summary}"
            
            elif is_query_signup:
                summary = sheet.get_summary()
                reply_msg = summary

        # --- 處理資料查詢指令 ---
        elif match_query_self or match_query_all or match_query_other:
            # 檢查查詢功能開關
            if not sheet.is_query_enabled():
                # line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查詢功能目前已關閉。"))
                return # 直接忽略

            if match_query_all:
                reply_msg = sheet.get_all_stats()
            
            elif match_query_self:
                # 查自己 (利用 user_id)
                results = sheet.query_stats(user_id=user_id)
                if results:
                    reply_msg = "\n".join(results)
                else:
                    reply_msg = "查無您的相關資料。"
            
            elif match_query_other:
                target_name = match_query_other.group(1)
                results = sheet.query_stats(name=target_name)
                if results:
                    reply_msg = "\n".join(results)
                else:
                    reply_msg = f"查無 {target_name} 的相關資料。"

        # 4. 回覆 Line 訊息 (如果有產生物件)
        if reply_msg:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_msg)
            )

    except Exception as e:
        print(f"處理指令時發生錯誤: {e}")
        # line_bot_api.reply_message(
        #     event.reply_token,
        #     TextSendMessage(text="處理您的請求時發生錯誤，請稍後再試。")
        # )
