﻿import os
import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, request, abort
import logging
import traceback
import json

# ★ line-bot-sdk v2 系 ★
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
    CarouselContainer,
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

# ---------------------------------------
# ユーザーの状態管理 (簡易) 実際はDBが望ましい
# ---------------------------------------
user_states = {}

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


#############################
# 価格表のデータ例（簡易版）
#############################
# 実際には添付のExcelをcsv等にして読み込むか、下記のように全行をリスト化してください。
# ここではサンプルとして、ドライTシャツの一部データだけを掲載。
PRICE_TABLE = [
    # product,  minQty, maxQty, discountType, unitPrice, addColor, addPosition, addFullColor
    # e.g. ドライTシャツ (早割 or 通常)
    ("ドライTシャツ", 10, 14, "早割",    1830, 850, 850, 550),
    ("ドライTシャツ", 10, 14, "通常",    2030, 850, 850, 550),
    ("ドライTシャツ", 15, 19, "早割",    1470, 650, 650, 550),
    ("ドライTシャツ", 15, 19, "通常",    1670, 650, 650, 550),
    ("ドライTシャツ", 20, 29, "早割",    1230, 450, 450, 550),
    ("ドライTシャツ", 20, 29, "通常",    1430, 450, 450, 550),
    ("ドライTシャツ", 30, 39, "早割",    1060, 350, 350, 550),
    ("ドライTシャツ", 30, 39, "通常",    1260, 350, 350, 550),
    ("ドライTシャツ", 40, 49, "早割",     980, 350, 350, 550),
    ("ドライTシャツ", 40, 49, "通常",    1180, 350, 350, 550),
    ("ドライTシャツ", 50, 99, "早割",     890, 350, 350, 550),
    ("ドライTシャツ", 50, 99, "通常",    1090, 350, 350, 550),
    ("ドライTシャツ",100,500, "早割",     770, 300, 300, 550),
    ("ドライTシャツ",100,500, "通常",     970, 300, 300, 550),
    # ... ここに他の「ヘビーウェイトTシャツ」「ドライポロシャツ」などの行を追加 ...
]

def calc_total_price(
    product_name: str,
    quantity: int,
    early_discount_str: str,  # "14日前以上" => "早割", それ以外 => "通常"
    print_position: str,      # "前" / "背中" / "前と背中"
    color_option: str         # same_color_add / different_color_add / full_color_add
) -> int:
    """
    商品名・枚数・早割有無・色数オプションなどを元に合計金額を計算する。
    1) PRICE_TABLE から行を検索
    2) UnitPrice * 枚数
    3) オプション費用を追加
    4) プリント位置が背中や前後の場合、追加料金があるなら加算（必要に応じて実装）
    """

    # 早割 or 通常 を判定
    if early_discount_str == "14日前以上":
        discount_type = "早割"
    else:
        discount_type = "通常"

    # PRICE_TABLE から該当の行を探す
    #   - product == product_name
    #   - minQty <= quantity <= maxQty
    #   - discountType == discount_type
    #   結果が1件見つかったと仮定
    row = None
    for item in PRICE_TABLE:
        (p_name, min_q, max_q, d_type, u_price, add_col, add_pos, add_full) = item
        if (
            p_name == product_name
            and d_type == discount_type
            and min_q <= quantity <= max_q
        ):
            row = item
            break

    if not row:
        # 該当なしの場合は仮に 0円 で返す
        return 0

    (p_name, min_q, max_q, d_type, unit_price, color_price, pos_price, full_price) = row

    base = unit_price * quantity
    option_cost = 0

    # color_option によってオプション料金を加算
    if color_option == "same_color_add":
        option_cost += color_price * quantity
    elif color_option == "different_color_add":
        option_cost += pos_price * quantity
    elif color_option == "full_color_add":
        option_cost += full_price * quantity

    # もしプリント位置が "背中" や "前と背中" なら追加料金がある場合、ここで足す
    # 例: "背中" or "front_back" の場合に pos_price を加算するなど
    # 仕様により調整してください。
    if print_position == "背中":
        # 例: 追加で pos_price / 2 …? (仕様が不明)
        pass
    elif print_position == "前と背中":
        # 例: 追加で pos_price
        pass

    total = base + option_cost
    return total

# ------------------------------
# 以下、前回の簡易見積コード
# 商品名選択は Carousel
# ------------------------------

def create_product_selection_carousel():
    # 例: ドライTシャツ ~ ジップアップライトパーカー まで
    # Bubble1
    bubble1 = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='商品を選択してください(1/2)',
                    weight='bold',
                    size='md'
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(style='primary', action=PostbackAction(label='ドライTシャツ', data='ドライTシャツ')),
                ButtonComponent(style='primary', action=PostbackAction(label='ヘビーウェイトTシャツ', data='ヘビーウェイトTシャツ')),
                ButtonComponent(style='primary', action=PostbackAction(label='ドライポロシャツ', data='ドライポロシャツ')),
                ButtonComponent(style='primary', action=PostbackAction(label='ドライメッシュビブス', data='ドライメッシュビブス')),
                ButtonComponent(style='primary', action=PostbackAction(label='ドライベースボールシャツ', data='ドライベースボールシャツ')),
                ButtonComponent(style='primary', action=PostbackAction(label='ドライロングスリープTシャツ', data='ドライロングスリープTシャツ')),
                ButtonComponent(style='primary', action=PostbackAction(label='ドライハーフパンツ', data='ドライハーフパンツ'))
            ]
        )
    )
    # Bubble2
    bubble2 = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='商品を選択してください(2/2)',
                    weight='bold',
                    size='md'
                )
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(style='primary', action=PostbackAction(label='ヘビーウェイトロングスリープTシャツ', data='ヘビーウェイトロングスリープTシャツ')),
                ButtonComponent(style='primary', action=PostbackAction(label='クルーネックライトトレーナー', data='クルーネックライトトレーナー')),
                ButtonComponent(style='primary', action=PostbackAction(label='フーデッドライトパーカー', data='フーデッドライトパーカー')),
                ButtonComponent(style='primary', action=PostbackAction(label='スタンダードトレーナー', data='スタンダードトレーナー')),
                ButtonComponent(style='primary', action=PostbackAction(label='スタンダードWフードパーカー', data='スタンダードWフードパーカー')),
                ButtonComponent(style='primary', action=PostbackAction(label='ジップアップライトパーカー', data='ジップアップライトパーカー'))
            ]
        )
    )

    carousel = CarouselContainer(contents=[bubble1, bubble2])
    return FlexSendMessage(
        alt_text='商品を選択してください',
        contents=carousel
    )

def create_print_position_flex():
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[TextComponent(text='プリントする位置を選択してください', weight='bold')]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(style='primary', action=PostbackAction(label='前', data='front')),
                ButtonComponent(style='primary', action=PostbackAction(label='背中', data='back')),
                ButtonComponent(style='primary', action=PostbackAction(label='前と背中', data='front_back'))
            ]
        )
    )
    return FlexSendMessage(alt_text='プリント位置選択', contents=bubble)

def create_color_options_flex():
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(text='使用する色数(前・背中)を選択してください', weight='bold'),
                TextComponent(text='(複数選択の実装は省略)', size='sm')
            ]
        ),
        footer=BoxComponent(
            layout='vertical',
            contents=[
                ButtonComponent(style='primary', action=PostbackAction(label='同じ位置にプリントカラー追加', data='same_color_add')),
                ButtonComponent(style='primary', action=PostbackAction(label='別の場所にプリント位置追加', data='different_color_add')),
                ButtonComponent(style='primary', action=PostbackAction(label='フルカラーに追加', data='full_color_add'))
            ]
        )
    )
    return FlexSendMessage(alt_text='使用する色数を選択', contents=bubble)

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

def create_quick_estimate_intro_flex():
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

def create_early_discount_flex():
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text='使用日から14日前以上 or 14日前以内を選択してください。',
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
    return FlexSendMessage(alt_text='早割確認', contents=bubble)


#############################
# handle_message
#############################
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_input = event.message.text.strip()
    logger.info(f"user_input: {user_input}")

    # (A) 「モード選択」と入力された場合
    if user_input == "モード選択":
        flex_msg = create_mode_selection_flex()
        line_bot_api.reply_message(event.reply_token, flex_msg)
        return

    if user_id in user_states:
        state_data = user_states[user_id]
        st = state_data.get("state")

        # 1. 学校名
        if st == "await_school_name":
            state_data["school_name"] = user_input
            state_data["state"] = "await_prefecture"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="学校名を保存しました。\n次にお届け先(都道府県)を入力してください。")
            )
            return

        # 2. 都道府県
        if st == "await_prefecture":
            state_data["prefecture"] = user_input
            # 次は早割確認
            state_data["state"] = "await_early_discount"
            discount_flex = create_early_discount_flex()
            line_bot_api.reply_message(event.reply_token, discount_flex)
            return

        # 4. 予算
        if st == "await_budget":
            state_data["budget"] = user_input
            # 次は商品選択
            state_data["state"] = "await_product"
            product_carousel = create_product_selection_carousel()
            line_bot_api.reply_message(event.reply_token, product_carousel)
            return

        # 6. 枚数
        if st == "await_quantity":
            state_data["quantity"] = user_input
            state_data["state"] = "await_print_position"
            pos_flex = create_print_position_flex()
            line_bot_api.reply_message(event.reply_token, pos_flex)
            return

        # 想定外
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"現在の状態({st})でテキスト入力は想定外です。")
        )
        return

    # 通常メッセージ
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"あなたのメッセージ: {user_input}")
    )


#############################
# handle_postback
#############################
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    logger.info(f"Postback data: {data}")

    # 簡易見積モードへ
    if data == "quick_estimate":
        intro_flex = create_quick_estimate_intro_flex()
        line_bot_api.reply_message(event.reply_token, intro_flex)
        return

    if data == "start_quick_estimate_input":
        user_states[user_id] = {
            "state": "await_school_name",
            "school_name": None,
            "prefecture": None,
            "early_discount": None,  # 14日前以上 => 早割, 14日前以内 => 通常
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
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="簡易見積モードではありません。")
        )
        return

    state_data = user_states[user_id]
    st = state_data["state"]

    # 3. 早割確認
    if st == "await_early_discount":
        if data == "14days_plus":
            state_data["early_discount"] = "14日前以上"  # => 早割
        elif data == "14days_minus":
            state_data["early_discount"] = "14日前以内"  # => 通常
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="早割選択が不明です。"))
            return
        state_data["state"] = "await_budget"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="早割を保存しました。\n1枚あたりの予算を入力してください。")
        )
        return

    # 5. 商品名
    if st == "await_product":
        state_data["product"] = data
        state_data["state"] = "await_quantity"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"{data} を選択しました。\n枚数を入力してください。")
        )
        return

    # 7. プリント位置
    if st == "await_print_position":
        if data == "front":
            state_data["print_position"] = "前"
        elif data == "back":
            state_data["print_position"] = "背中"
        elif data == "front_back":
            state_data["print_position"] = "前と背中"
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="プリント位置の指定が不明です。"))
            return
        state_data["state"] = "await_color_options"
        color_flex = create_color_options_flex()
        line_bot_api.reply_message(event.reply_token, color_flex)
        return

    # 8. color options
    if st == "await_color_options":
        if data == "same_color_add":
            state_data["color_options"] = "same_color_add"
        elif data == "different_color_add":
            state_data["color_options"] = "different_color_add"
        elif data == "full_color_add":
            state_data["color_options"] = "full_color_add"
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="色数の選択が不明です。"))
            return

        # すべて完了 → 結果をまとめ
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

        # ★ 見積計算を行う ★
        product = state_data['product']
        qty = int(state_data['quantity'])
        early_disc = state_data['early_discount']  # "14日前以上" => 早割, else 通常
        pos = state_data['print_position']
        color_opt = state_data['color_options']

        total_price = calc_total_price(
            product_name=product,
            quantity=qty,
            early_discount_str=early_disc,
            print_position=pos,
            color_option=color_opt
        )

        # 状態を破棄
        del user_states[user_id]

        reply_text = (
            "全項目の入力が完了しました。\n\n"
            + summary
            + "\n\n--- 見積計算結果 ---\n"
            + f"合計金額: ¥{total_price:,}\n"
            + "（概算です。詳細は別途ご相談ください）"
        )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    # 想定外
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"不明なアクション: {data}")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
