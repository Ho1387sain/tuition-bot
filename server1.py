from flask import Flask, request
import requests
import pandas as pd
import jdatetime
import os

# ======== تنظیمات ========
TOKEN = os.getenv("TOKEN")  # توکن ربات بله از Env
API_URL = f"https://tapi.bale.ai/bot{TOKEN}"
EXCEL_FILE = "data_fixed.xlsx"

MERCHANT_ID = os.getenv("MERCHANT_ID")  # مرچنت زرین‌پال
BASE_URL = os.getenv("BASE_URL")        # آدرس سرویس روی Render
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "mysecret")  # رمز وبهوک

app = Flask(__name__)

# ======== دریافت پیام از بله (Webhook) ========
@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.json
    if "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "").strip()

    # مرحله شروع
    if text == "/start":
        msg = "سلام! لطفاً کد ملی خود را وارد کنید."
        send_message(chat_id, msg)
        return "ok"

    # بررسی کد ملی
    if text.isdigit() and len(text) >= 8:
        try:
            df = pd.read_excel(EXCEL_FILE, sheet_name="دانشجویان")
            national_id = int(text)
            row = df[df["کد ملی"] == national_id]
            if not row.empty:
                name = row.iloc[0]["نام"]
                tuition = int(row.iloc[0]["شهریه"])
                msg = (f"کد ملی: {national_id}\n"
                       f"نام: {name}\n"
                       f"مبلغ شهریه: {tuition} تومان\n\n"
                       "مبلغ پرداختی خود را (به ریال) وارد کنید:")
                send_message(chat_id, msg)
            else:
                send_message(chat_id, "❌ کد ملی شما یافت نشد.")
        except Exception as e:
            send_message(chat_id, f"خطا در خواندن فایل: {e}")
        return "ok"

    # اگر ورودی عددی باشد → پرداخت
    if text.isdigit():
        amount_rial = int(text)
        amount_toman = amount_rial // 10

        # ساخت لینک پرداخت
        payment_url, _ = create_payment(
            amount_rial,
            f"پرداخت شهریه",
            f"{BASE_URL}/callback?chat_id={chat_id}&amount={amount_rial}"
        )

        if payment_url:
            msg = (f"✅ مبلغ {amount_toman} تومان ثبت شد.\n"
                   f"برای پرداخت روی لینک زیر کلیک کنید:\n{payment_url}\n\n"
                   "🔹 توجه: این لینک آزمایشی (Sandbox) است.")
        else:
            msg = "⚠️ خطا در ایجاد لینک پرداخت!"
        send_message(chat_id, msg)
        return "ok"

    # ورودی غیرمعتبر
    send_message(chat_id, "لطفاً کد ملی یا مبلغ معتبر وارد کنید.")
    return "ok"

# ======== تأیید پرداخت زرین‌پال ========
@app.route("/callback")
def callback():
    chat_id = request.args.get("chat_id")
    amount_rial = int(request.args.get("amount"))
    amount_toman = amount_rial // 10
    authority = request.args.get("Authority")
    status = request.args.get("Status")

    if status == "OK":
        # verify
        url = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
        data = {
            "merchant_id": MERCHANT_ID,
            "amount": amount_rial,  # ریال
            "authority": authority
        }
        res = requests.post(url, json=data).json()
        if res.get("data") and res["data"].get("code") == 100:
            # ثبت در اکسل
            df = pd.read_excel(EXCEL_FILE, sheet_name="دانشجویان")
            payments = pd.read_excel(EXCEL_FILE, sheet_name="پرداخت‌ها")

            shamsi_date = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
            new_row = {
                "تاریخ": shamsi_date,
                "مبلغ (تومان)": amount_toman,
                "وضعیت": "موفق"
            }
            payments = pd.concat([payments, pd.DataFrame([new_row])], ignore_index=True)

            with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl", mode="w") as writer:
                df.to_excel(writer, index=False, sheet_name="دانشجویان")
                payments.to_excel(writer, index=False, sheet_name="پرداخت‌ها")

            send_message(chat_id, f"✅ پرداخت {amount_toman} تومان با موفقیت ثبت شد.")
            return "پرداخت موفق بود ✅"
        else:
            send_message(chat_id, "❌ پرداخت ناموفق بود.")
            return "پرداخت ناموفق ❌"
    else:
        send_message(chat_id, "❌ پرداخت توسط کاربر لغو شد.")
        return "پرداخت لغو شد ❌"

# ======== توابع کمکی ========
def send_message(chat_id, text):
    requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def create_payment(amount, description, callback_url):
    url = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
    data = {
        "merchant_id": MERCHANT_ID,
        "amount": amount,  # ریال
        "description": description,
        "callback_url": callback_url
    }
    try:
        res = requests.post(url, json=data).json()
        if res.get("data") and res["data"].get("authority"):
            authority = res["data"]["authority"]
            return f"https://sandbox.zarinpal.com/pg/StartPay/{authority}", authority
    except Exception as e:
        print("خطا در ایجاد لینک پرداخت:", e)
    return None, None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
