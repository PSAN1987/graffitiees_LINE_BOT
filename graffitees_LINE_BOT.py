﻿import os
import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, request, abort
import logging
import traceback
import json

# ★★★ line-bot-sdk v2 系 ★★★
from linebot import (
    LineBotApi,
    WebhookHandler
)
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    PostbackEvent,
    TextMessage,
    TextSendMessage,
    PostbackAction,
    FlexSendMessage,
    BubbleContainer,
    BoxComponent,
    TextComponent,
    ButtonComponent
)

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ------------------------------------------
# ◆ ユーザーの状態管理: 簡易的に辞書で保持
# ------------------------------------------
user_states = {}  
# 例: {
#   "<user_id>": {
#       "state": "await_school_name",
#       "school_name": None,
#       "prefecture": None,
#       "early_discount": None,
#       "budget": None,
#       "product": None,
#       "quantity": None,
#       "print_position": None,
#       "color_options": None
#   }
# }

@app.route("/", methods=["GET"])
def health_check():
    return "OK", 200

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        abort(400)

    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        logger.error(f"InvalidSignatureError: {e}")
        abort(400)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        traceback.print_exc()
        abort(500)

    return "OK", 200

# -------- モード選択用 Flex --------
def create_mode_selection_flex():
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='モードを選択してください!',
                    weight='bold',
                    size='lg'
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='簡易見積', data='quick_estimate')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='WEBフォームから注文', data='web_order')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='注文用紙から注文', data='paper_order')
                )
            ]
        )
    )
    return FlexSendMessage(
        alt_text='モードを選択してください',
        contents=bubble
    )

# -------- 簡易見積導入 Flex --------
def create_quick_estimate_intro_flex():
    """
    簡易見積モードに入った時に最初に表示するFlex。
    8項目を案内し、「入力を開始する」ボタンを表示。
    """
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='簡易見積に必要な項目を順番に確認します。\n'
                         '1. 学校/団体名\n'
                         '2. お届け先(都道府県)\n'
                         '3. 早割確認\n'
                         '4. 1枚当たりの予算\n'
                         '5. 商品名\n'
                         '6. 枚数\n'
                         '7. プリント位置\n'
                         '8. 使用する色数',
                    wrap=True
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='入力を開始する', data='start_quick_estimate_input')
                )
            ]
        )
    )
    return FlexSendMessage(
        alt_text='簡易見積モードへようこそ',
        contents=bubble
    )

# -------- 早割確認用 Flex (3) --------
def create_early_discount_flex():
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='使用日から14日前以上か14日前以内か選択してください。',
                    wrap=True
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='14日前以上', data='14days_plus')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='14日前以内', data='14days_minus')
                )
            ]
        )
    )
    return FlexSendMessage(
        alt_text='早割確認',
        contents=bubble
    )

# -------- 商品選択用 Flex (5) --------
def create_product_selection_flex():
    """
    商品名の候補が14種あるが、ここでは例として4種だけボタンで表示。
    実際にはCarouselContainerなどで複数バブルに分割を推奨
    """
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='商品を選択してください',
                    weight='bold',
                    size='md',
                    wrap=True
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='ドライTシャツ', data='ドライTシャツ')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='ヘビーウェイトTシャツ', data='ヘビーウェイトTシャツ')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='ドライポロシャツ', data='ドライポロシャツ')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='ドライメッシュビブス', data='ドライメッシュビブス')
                )
            ]
        )
    )
    return FlexSendMessage(
        alt_text='商品を選択してください',
        contents=bubble
    )

# -------- プリント位置選択用 Flex (7) --------
def create_print_position_flex():
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='プリントする位置を選択してください',
                    weight='bold',
                    size='md',
                    wrap=True
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='前', data='front')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='背中', data='back')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='前と背中', data='front_back')
                )
            ]
        )
    )
    return FlexSendMessage(
        alt_text='プリント位置選択',
        contents=bubble
    )

# -------- 使用する色数選択用 Flex (8) --------
def create_color_options_flex():
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='使用する色数(前・背中)を選択してください',
                    weight='bold',
                    size='md',
                    wrap=True
                ),
                TextComponent(
                    text='(複数選択が必要な場合は追加の実装が必要)',
                    size='sm',
                    wrap=True
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='同じ位置にプリントカラー追加', data='same_color_add')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='別の場所にプリント位置追加', data='different_color_add')
                ),
                ButtonComponent(
                    style='primary',
                    action=PostbackAction(label='フルカラーに追加', data='full_color_add')
                )
            ]
        )
    )
    return FlexSendMessage(
        alt_text='使用する色数を選択',
        contents=bubble
    )

# -------- ユーザーがテキストを送ったときのハンドラ --------
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_input = event.message.text.strip()
    logger.info(f"user_input: {user_input}")

    # 「モード選択」と入力された → 3 つのモードボタンを返信
    if user_input == "モード選択":
        flex_msg = create_mode_selection_flex()
        line_bot_api.reply_message(event.reply_token, flex_msg)
        return

    # 簡易見積モード中かどうか
    if user_id in user_states:
        state_data = user_states[user_id]
        current_state = state_data.get("state")

        # 1. 学校名 待ち
        if current_state == "await_school_name":
            state_data["school_name"] = user_input
            # 次は 2. お届け先(都道府県)
            state_data["state"] = "await_prefecture"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="学校名を保存しました。\n次にお届け先(都道府県)を入力してください。")
            )
            return

        # 2. 都道府県 待ち
        if current_state == "await_prefecture":
            state_data["prefecture"] = user_input
            # 次は 3. 早割確認 → Flex
            state_data["state"] = "await_early_discount"
            flex = create_early_discount_flex()
            line_bot_api.reply_message(event.reply_token, flex)
            return

        # 4. 1枚当たりの予算 待ち
        if current_state == "await_budget":
            state_data["budget"] = user_input
            # 次は 5. 商品選択 → Flex
            state_data["state"] = "await_product"
            product_flex = create_product_selection_flex()
            line_bot_api.reply_message(event.reply_token, product_flex)
            return

        # 6. 枚数 待ち
        if current_state == "await_quantity":
            state_data["quantity"] = user_input
            # 次は 7. プリント位置 → Flex
            state_data["state"] = "await_print_position"
            position_flex = create_print_position_flex()
            line_bot_api.reply_message(event.reply_token, position_flex)
            return

        # 上記以外の状態でテキストが来た場合
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"現在の状態({current_state})ではテキスト入力は想定外です。")
        )
        return

    # ここまで来たら通常のテキストリプライ
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"あなたのメッセージ: {user_input}")
    )


# -------- ユーザーがボタンを押したときのハンドラ --------
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    logger.info(f"Postback data: {data}")

    if data == "quick_estimate":
        # 簡易見積モードの導入Flexを送る
        flex_msg = create_quick_estimate_intro_flex()
        line_bot_api.reply_message(event.reply_token, flex_msg)
        return

    if data == "start_quick_estimate_input":
        # 簡易見積のステート初期化
        user_states[user_id] = {
            "state": "await_school_name",
            "school_name": None,
            "prefecture": None,
            "early_discount": None,
            "budget": None,
            "product": None,
            "quantity": None,
            "print_position": None,
            "color_options": None
        }
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="まずは学校または団体名を入力してください。")
        )
        return

    if user_id not in user_states:
        # 簡易見積モードでない
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="簡易見積モードではありません。")
        )
        return

    state_data = user_states[user_id]
    current_state = state_data.get("state")

    # 3. 早割確認 (Postback)
    if current_state == "await_early_discount":
        if data == "14days_plus":
            state_data["early_discount"] = "14日前以上"
        elif data == "14days_minus":
            state_data["early_discount"] = "14日前以内"
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="早割の選択が不明です。")
            )
            return

        # 次は 4. 予算 → テキスト入力
        state_data["state"] = "await_budget"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="早割を保存しました。\n1枚あたりの予算を入力してください。")
        )
        return

    # 5. 商品名 (Postback)
    if current_state == "await_product":
        # ボタンが複数ある想定。ここでは4種のみ例
        state_data["product"] = data
        # 次は 6. 枚数 → テキスト入力
        state_data["state"] = "await_quantity"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"{data} を選択しました。\n枚数を入力してください。")
        )
        return

    # 7. プリント位置 (Postback)
    if current_state == "await_print_position":
        if data == "front":
            state_data["print_position"] = "前"
        elif data == "back":
            state_data["print_position"] = "背中"
        elif data == "front_back":
            state_data["print_position"] = "前と背中"
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="プリント位置の指定が不明です。")
            )
            return

        # 次は 8. 使用する色数 → Flex
        state_data["state"] = "await_color_options"
        flex = create_color_options_flex()
        line_bot_api.reply_message(event.reply_token, flex)
        return

    # 8. 使用する色数 (Postback)
    if current_state == "await_color_options":
        if data == "same_color_add":
            state_data["color_options"] = "同じ位置にプリントカラー追加"
        elif data == "different_color_add":
            state_data["color_options"] = "別の場所にプリント位置追加"
        elif data == "full_color_add":
            state_data["color_options"] = "フルカラーに追加"
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="色数の選択が不明です。")
            )
            return

        # 全項目完了
        summary = (
            f"学校/団体名: {state_data['school_name']}\n"
            f"都道府県: {state_data['prefecture']}\n"
            f"早割確認: {state_data['early_discount']}\n"
            f"予算: {state_data['budget']}\n"
            f"商品名: {state_data['product']}\n"
            f"枚数: {state_data['quantity']}\n"
            f"プリント位置: {state_data['print_position']}\n"
            f"使用する色数: {state_data['color_options']}"
        )
        # 状態をリセット or 破棄
        del user_states[user_id]

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="全項目の入力が完了しました。\n\n" + summary + "\n\n後ほど見積計算を行います。"
            )
        )
        return

    # ここまで来たら想定外のデータ
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"不明なアクション: {data}")
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
