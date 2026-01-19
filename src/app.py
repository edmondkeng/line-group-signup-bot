import os
import sys
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
)

from bot_logic import handle_text_message

# 載入環境變數
load_dotenv()

app = Flask(__name__)

# 從環境變數讀取 Line Bot 設定
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

if CHANNEL_ACCESS_TOKEN is None or CHANNEL_SECRET is None:
    print('Error: 請在 .env 檔案中設定 LINE_CHANNEL_ACCESS_TOKEN 與 LINE_CHANNEL_SECRET')
    sys.exit(1)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 表頭
    signature = request.headers['X-Line-Signature']

    # 取得請求內容
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 驗證簽章並處理事件
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 將邏輯轉交給 bot_logic 處理，保持 app.py 乾淨
    handle_text_message(event, line_bot_api)

if __name__ == "__main__":
    app.run(port=5000, debug=True)
