import asyncio
import sqlite3
import uuid
import requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

app = FastAPI()

# ---------------------------------------------------------
# НАСТРОЙКИ (Укажите свои реальные данные)
# ---------------------------------------------------------
WEATHER_API_KEY = "2de4b7fbe5dd6de7e15810555d61457f"
TELEGRAM_BOT_TOKEN = "8539880858:AAH-LroXnwOpZq4v8p-qmnhDOkd3thDaWIA"
BOT_USERNAME = "WheaterRainAppBot"
ADMIN_PIN = "122595"
RENDER_URL = "https://rain-program.onrender.com"

PHENOMENA = {
    "rain": {"name_ua": "🌧️ Дощ", "name_en": "🌧️ Rain", "min_id": 200, "max_id": 531},
    "first_snow": {"name_ua": "❄️ Перший Сніг (Аукціон)", "name_en": "❄️ First Snow (Auction)", "min_id": 600, "max_id": 622},
    "thunderstorm": {"name_ua": "🌩️ Гроза", "name_en": "🌩️ Thunderstorm", "min_id": 200, "max_id": 232},
    "fog": {"name_ua": "🌫️ Туман", "name_en": "🌫️ Fog", "min_id": 701, "max_id": 781},
    "clear": {"name_ua": "☀️ Ясне небо / Повня", "name_en": "☀️ Clear Sky / Full Moon", "min_id": 800, "max_id": 800},
}


def init_db():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            sender TEXT,
            recipient_chat_id TEXT,
            message TEXT,
            city TEXT,
            phenomenon TEXT,
            price REAL,
            is_auction INTEGER,
            lang TEXT,
            status TEXT
        )
    """
    )
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# TELEGRAM WEBHOOK (Прием сообщений /start)
# ---------------------------------------------------------
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        if "message" in data:
            chat_id = str(data["message"]["chat"]["id"])
            text = data["message"].get("text", "")

            if text.startswith("/start"):
                parts = text.split()
                if len(parts) > 1:
                    order_id = parts[1].strip()

                    conn = sqlite3.connect("orders.db")
                    cursor = conn.cursor()
                    cursor.execute("UPDATE orders SET recipient_chat_id = ? WHERE id = ?", (chat_id, order_id))
                    cursor.execute("SELECT sender, city, phenomenon, lang FROM orders WHERE id = ?", (order_id,))
                    order = cursor.fetchone()
                    conn.commit()
                    conn.close()

                    if order:
                        sender, city, phenomenon_key, lang = order
                        rules = PHENOMENA.get(phenomenon_key, {})
                        phen_name = rules.get("name_en" if lang == "en" else "name_ua", phenomenon_key)

                        reply_text = (
                            f"✨ **Gift Activated!**\n\n"
                            f"{sender} booked **{phen_name}** in **{city.capitalize()}** for you.\n"
                            f"We will notify you instantly when it starts!"
                            if lang == "en"
                            else f"✨ **Подарунок активовано!**\n\n"
                            f"{sender} забронював(ла) для вас **{phen_name}** у м. **{city.capitalize()}**.\n"
                            f"Ми сповістимо вас миттєво, як тільки явище розпочнеться!"
                        )

                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={"chat_id": chat_id, "text": reply_text, "parse_mode": "Markdown"},
                        )
                else:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={"chat_id": chat_id, "text": "Вітаємо! Сервіс емоцій та погодних подарунків вітає вас."},
                    )
    except Exception as e:
        print(f"Webhook error: {e}")

    return {"status": "ok"}


def send_notification(order_id, sender, recipient_chat_id, message, city, phenomenon_name, temp, lang="ua"):
    cert_url = f"{RENDER_URL}/cert/{order_id}"

    if lang == "en":
        text = (
            f"✨ **Right now in {city.capitalize()} weather event started: {phenomenon_name}!**\n\n"
            f"And it was exclusively booked for you.\n"
            f"🌡 Temperature: {temp}°C\n"
            f"💬 Message from {sender}: «{message}»\n\n"
            f"📜 Your personal digital certificate: {cert_url}"
        )
    else:
        text = (
            f"✨ **Прямо зараз у м. {city.capitalize()} почалося явище: {phenomenon_name}!**\n\n"
            f"І його ексклюзивно заброньовано для вас.\n"
            f"🌡 Температура: {temp}°C\n"
            f"💬 Послання від {sender}: «{message}»\n\n"
            f"📜 Ваш персональний цифровий сертифікат: {cert_url}"
        )

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(tg_url, json={"chat_id": recipient_chat_id, "text": text, "parse_mode": "Markdown"})


def check_all_active_cities():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT city FROM orders WHERE status = 'pending' AND recipient_chat_id != ''")
    active_cities = cursor.fetchall()

    for (city,) in active_cities:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
            res = requests.get(url).json()

            if res.get("cod") == 200:
                weather_id = res["weather"][0]["id"]
                temp = res["main"]["temp"]

                cursor.execute(
                    "SELECT id, sender, recipient_chat_id, message, phenomenon, price, is_auction, lang FROM orders WHERE city = ? AND status = 'pending' ORDER BY price DESC",
                    (city,),
                )
                orders = cursor.fetchall()
                processed_auctions = set()

                for order in orders:
                    (order_id, sender, recipient_chat_id, message, phenomenon_key, price, is_auction, lang) = order
                    rules = PHENOMENA.get(phenomenon_key)

                    if is_auction and phenomenon_key in processed_auctions:
                        continue

                    if rules and rules["min_id"] <= weather_id <= rules["max_id"]:
                        phen_name = rules["name_en"] if lang == "en" else rules["name_ua"]
                        send_notification(order_id, sender, recipient_chat_id, message, city, phen_name, temp, lang)
                        cursor.execute("UPDATE orders SET status = 'sent' WHERE id = ?", (order_id,))
                        conn.commit()

                        if is_auction:
                            processed_auctions.add(phenomenon_key)
        except Exception as e:
            print(f"Error checking {city}: {e}")

    conn.close()


async def background_weather_checker():
    while True:
        check_all_active_cities()
        await asyncio.sleep(600)


@app.on_event("startup")
async def startup_event():
    # Регистрация вебхука в Telegram при запуске
    try:
        webhook_url = f"{RENDER_URL}/webhook"
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}")
    except Exception as e:
        print(f"Failed to set webhook: {e}")

    asyncio.create_task(background_weather_checker())


# ---------------------------------------------------------
# ГЛАВНАЯ СТРАНИЦА
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home_page():
    return """
    <!DOCTYPE html>
    <html lang="ua">
    <head>
        <meta charset="UTF-8">
        <title>Забронювати Емоцію / Book Weather Moment</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: -apple-system, sans-serif; background: #0f172a; color: white; padding: 15px; margin: 0; }
            .card { max-width: 480px; margin: 20px auto; background: #1e293b; padding: 25px; border-radius: 20px; border: 1px solid #334155; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            .lang-switch { display: flex; justify-content: flex-end; gap: 10px; margin-bottom: 15px; }
            .lang-btn { background: #334155; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: bold; }
            .lang-btn.active { background: #38bdf8; color: black; }
            h2 { color: #7dd3fc; margin-top: 0; font-size: 22px; }
            label { font-size: 13px; color: #94a3b8; display: block; margin-top: 12px; }
            input, select, textarea { width: 100%; padding: 12px; margin-top: 5px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; font-size: 15px; }
            .price-tag { background: rgba(56, 189, 248, 0.1); border: 1px solid #38bdf8; padding: 12px; border-radius: 8px; margin: 15px 0; text-align: center; color: #38bdf8; font-weight: bold; }
            button.submit-btn { width: 100%; padding: 15px; background: #38bdf8; color: black; border: none; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 16px; margin-top: 15px; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="lang-switch">
                <button class="lang-btn active" onclick="setLang('ua')">UA 🇺🇦</button>
                <button class="lang-btn" onclick="setLang('en')">EN 🇬🇧</button>
            </div>

            <h2 id="t-title">✨ Забронювати природне явище</h2>
            <form action="/create-order" method="post">
                <input type="hidden" name="lang" id="langInput" value="ua">

                <label id="t-sender">Ваше ім'я (відправник):</label>
                <input type="text" name="sender" placeholder="Олександр" required>
                
                <label id="t-city">Місто світу:</label>
                <input type="text" name="city" placeholder="Kyiv, Paris, London, Tokyo" required>
                
                <label id="t-phenomenon">Природне явище:</label>
                <select name="phenomenon" id="phenomenonSelect" onchange="toggleAuction()">
                    <option value="rain" id="opt-rain">🌧️ Дощ ($5 / 250 грн)</option>
                    <option value="thunderstorm" id="opt-thunder">🌩️ Гроза ($5 / 250 грн)</option>
                    <option value="fog" id="opt-fog">🌫️ Туман ($5 / 250 грн)</option>
                    <option value="clear" id="opt-clear">☀️ Ясне небо / Повня ($5 / 250 грн)</option>
                    <option value="first_snow" id="opt-snow">❄️ Перший Сніг Сезону (АУКЦІОН)</option>
                </select>
                
                <div id="priceBox" class="price-tag">Вартість бронювання: $5 (250 грн)</div>

                <div id="auctionBox" style="display:none;">
                    <label id="t-bid">Ваша ставка для аукціону ($ / грн):</label>
                    <input type="number" name="bid_price" value="10" min="5">
                    <p style="font-size: 12px; color: #f59e0b; margin-top: 4px;" id="t-auc-desc">⚠️ Правом на «Перший сніг» заволодіє той, чия ставка буде вищою на момент снігопаду.</p>
                </div>

                <label id="t-msg">Ваше тепле послання:</label>
                <textarea name="message" rows="3" placeholder="Нехай цей момент нагадає тобі про нас..." required></textarea>
                
                <button type="submit" class="submit-btn" id="t-btn">Оформити подарунок ($5 / 250 грн)</button>
            </form>
        </div>

        <script>
            let currentLang = 'ua';

            function setLang(lang) {
                currentLang = lang;
                document.getElementById('langInput').value = lang;
                document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
                event.target.classList.add('active');

                if (lang === 'en') {
                    document.getElementById('t-title').innerText = "✨ Book a Weather Moment";
                    document.getElementById('t-sender').innerText = "Your name (sender):";
                    document.getElementById('t-city').innerText = "City of the world:";
                    document.getElementById('t-phenomenon').innerText = "Weather Phenomenon:";
                    document.getElementById('t-bid').innerText = "Your Auction Bid ($):";
                    document.getElementById('t-auc-desc').innerText = "⚠️ 'First Snow' will be delivered to the highest bidder when snowfall begins.";
                    document.getElementById('t-msg').innerText = "Your personal message:";
                    document.getElementById('t-btn').innerText = "Proceed to Gift Creation ($5)";
                    document.getElementById('priceBox').innerText = "Booking Price: $5 (250 UAH)";
                    
                    document.getElementById('opt-rain').innerText = "🌧️ Rain ($5)";
                    document.getElementById('opt-thunder').innerText = "🌩️ Thunderstorm ($5)";
                    document.getElementById('opt-fog').innerText = "🌫️ Fog ($5)";
                    document.getElementById('opt-clear').innerText = "☀️ Clear Sky / Full Moon ($5)";
                    document.getElementById('opt-snow').innerText = "❄️ First Snow (AUCTION)";
                } else {
                    document.getElementById('t-title').innerText = "✨ Забронювати природне явище";
                    document.getElementById('t-sender').innerText = "Ваше ім'я (відправник):";
                    document.getElementById('t-city').innerText = "Місто світу:";
                    document.getElementById('t-phenomenon').innerText = "Природне явище:";
                    document.getElementById('t-bid').innerText = "Ваша ставка для аукціону ($ / грн):";
                    document.getElementById('t-auc-desc').innerText = "⚠️ Правом на «Перший сніг» заволодіє той, чия ставка буде вищою на момент снігопаду.";
                    document.getElementById('t-msg').innerText = "Ваше тепле послання:";
                    document.getElementById('t-btn').innerText = "Оформити подарунок ($5 / 250 грн)";
                    document.getElementById('priceBox').innerText = "Вартість бронювання: $5 (250 грн)";

                    document.getElementById('opt-rain').innerText = "🌧️ Дощ ($5 / 250 грн)";
                    document.getElementById('opt-thunder').innerText = "🌩️ Гроза ($5 / 250 грн)";
                    document.getElementById('opt-fog').innerText = "🌫️ Туман ($5 / 250 грн)";
                    document.getElementById('opt-clear').innerText = "☀️ Ясне небо / Повня ($5 / 250 грн)";
                    document.getElementById('opt-snow').innerText = "❄️ Перший Сніг Сезону (АУКЦІОН)";
                }
            }

            function toggleAuction() {
                var select = document.getElementById("phenomenonSelect");
                var priceBox = document.getElementById("priceBox");
                var auctionBox = document.getElementById("auctionBox");
                if (select.value === "first_snow") {
                    priceBox.style.display = "none";
                    auctionBox.style.display = "block";
                } else {
                    priceBox.style.display = "block";
                    auctionBox.style.display = "none";
                }
            }
        </script>
    </body>
    </html>
    """


@app.post("/create-order")
def create_order(
    sender: str = Form(...),
    city: str = Form(...),
    phenomenon: str = Form(...),
    message: str = Form(...),
    lang: str = Form("ua"),
    bid_price: float = Form(5.0),
):
    clean_city = city.strip().lower()

    check_url = f"https://api.openweathermap.org/data/2.5/weather?q={clean_city}&appid={WEATHER_API_KEY}"
    res = requests.get(check_url).json()

    if res.get("cod") != 200:
        msg = "❌ City not found." if lang == "en" else "❌ Місто не знайдено."
        return HTMLResponse(f"<h3>{msg}</h3><a href='/'>Back / Назад</a>")

    if res.get("sys", {}).get("country") == "RU":
        msg = "⛔ Region not supported." if lang == "en" else "⛔ Даний регіон недоступний."
        return HTMLResponse(f"<h3>{msg}</h3><a href='/'>Back / Назад</a>")

    is_auction = 1 if phenomenon == "first_snow" else 0
    final_price = bid_price if is_auction else 5.0
    order_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, 'pending')",
        (order_id, sender, message, clean_city, phenomenon, final_price, is_auction, lang),
    )
    conn.commit()
    conn.close()

    tg_gift_link = f"https://t.me/{BOT_USERNAME}?start={order_id}"

    if lang == "en":
        return HTMLResponse(
            f"""
            <body style="background:#0f172a;color:white;font-family:sans-serif;padding:20px;text-align:center;">
                <div style="max-width:450px;margin:auto;background:#1e293b;padding:25px;border-radius:16px;">
                    <h2>✅ Booking Created!</h2>
                    <p>Send this gift link to the recipient so they get notified when the weather starts:</p>
                    <input type="text" value="{tg_gift_link}" style="width:100%;padding:10px;border-radius:6px;background:#0f172a;color:#38bdf8;border:1px solid #38bdf8;" readonly>
                    <br><br>
                    <a href="https://t.me/share/url?url={tg_gift_link}&text=I%20booked%20the%20next%20weather%20moment%20for%20you!" style="display:block;background:#38bdf8;color:black;padding:12px;border-radius:8px;text-decoration:none;font-weight:bold;">Send via Telegram</a>
                </div>
            </body>
            """
        )
    else:
        return HTMLResponse(
            f"""
            <body style="background:#0f172a;color:white;font-family:sans-serif;padding:20px;text-align:center;">
                <div style="max-width:450px;margin:auto;background:#1e293b;padding:25px;border-radius:16px;">
                    <h2>✅ Бронювання створено!</h2>
                    <p>Надішліть це посилання-подарунок одержувачу, щоб бот сповістив його у момент події:</p>
                    <input type="text" value="{tg_gift_link}" style="width:100%;padding:10px;border-radius:6px;background:#0f172a;color:#38bdf8;border:1px solid #38bdf8;" readonly>
                    <br><br>
                    <a href="https://t.me/share/url?url={tg_gift_link}&text=Я%20забронював%20для%20тебе%20найближчу%20погоду!" style="display:block;background:#38bdf8;color:black;padding:12px;border-radius:8px;text-decoration:none;font-weight:bold;">Надіслати в Telegram</a>
                </div>
            </body>
            """
        )


# ---------------------------------------------------------
# ПАНЕЛЬ ВЛАДЕЛЬЦА
# ---------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_panel(pin: str = ""):
    if pin != ADMIN_PIN:
        return """
        <body style="background:#0f172a;color:white;font-family:sans-serif;padding:30px;">
            <form method="get" style="max-width:300px;margin:auto;">
                <h3>🔒 Панель власника</h3>
                <input type="password" name="pin" placeholder="ПИН-код" style="width:100%;padding:10px;margin-bottom:10px;">
                <button style="width:100%;padding:10px;background:#38bdf8;">Увійти</button>
            </form>
        </body>
        """

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, sender, recipient_chat_id, city, phenomenon, price, is_auction, status FROM orders")
    orders = cursor.fetchall()
    conn.close()

    rows = ""
    for o in orders:
        o_id, sender, tg_id, city, phenom, price, is_auc, status = o
        rows += f"""
        <tr style="border-bottom:1px solid #334155;">
            <td style="padding:8px;">#{o_id}</td>
            <td style="padding:8px;">{sender}</td>
            <td style="padding:8px;">{tg_id if tg_id else "⏳ Очікує кліку"}</td>
            <td style="padding:8px;">{city.capitalize()}</td>
            <td style="padding:8px;">{phenom}</td>
            <td style="padding:8px;">${price}</td>
            <td style="padding:8px;">{status}</td>
            <td style="padding:8px;">
                <form action="/admin/test-trigger" method="post" style="margin:0;">
                    <input type="hidden" name="pin" value="{ADMIN_PIN}">
                    <input type="hidden" name="order_id" value="{o_id}">
                    <button style="background:#22c55e;color:black;border:none;padding:6px 12px;border-radius:4px;font-weight:bold;cursor:pointer;">🚀 Тест</button>
                </form>
            </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Admin Panel</title><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>body {{ font-family: sans-serif; background: #0f172a; color: white; padding: 15px; }} table {{ width: 100%; border-collapse: collapse; background: #1e293b; }} th {{ background: #334155; text-align: left; padding: 10px; }}</style>
    </head>
    <body>
        <h2>👑 Панель управління</h2>
        <div style="overflow-x:auto;">
            <table>
                <tr><th>ID</th><th>Відправник</th><th>Telegram Chat ID</th><th>Місто</th><th>Явище</th><th>Ціна</th><th>Статус</th><th>Дій</th></tr>
                {rows}
            </table>
        </div>
    </body>
    </html>
    """


@app.post("/admin/test-trigger")
def test_trigger(pin: str = Form(...), order_id: str = Form(...)):
    if pin != ADMIN_PIN:
        return "Error"

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT sender, recipient_chat_id, message, city, phenomenon, lang FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()

    if order:
        sender, recipient_chat_id, message, city, phenomenon_key, lang = order
        if not recipient_chat_id:
            return HTMLResponse("<h3>⚠️ Одержувач ще не перейшов за посиланням-подарунком!</h3><a href='/admin?pin=122595'>Назад</a>")

        rules = PHENOMENA.get(phenomenon_key, {"name_ua": "🌩️ Тест", "name_en": "🌩️ Test"})
        phen_name = rules["name_en"] if lang == "en" else rules["name_ua"]

        send_notification(order_id, sender, recipient_chat_id, message, city, f"{phen_name} (TEST)", 18.5, lang)
        return HTMLResponse(f"<h3>✅ Надіслано для #{order_id}!</h3><a href='/admin?pin={ADMIN_PIN}'>Назад</a>")

    return "Not found"


@app.get("/cert/{order_id}", response_class=HTMLResponse)
def view_certificate(order_id: str):
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT sender, message, city, phenomenon FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()

    if not order:
        return "Сертифікат не знайдено / Certificate not found"

    sender, message, city, phenomenon = order
    rules = PHENOMENA.get(phenomenon, {})
    phenomenon_title = rules.get("name_ua", phenomenon)

    return f"""
    <!DOCTYPE html>
    <html lang="ua">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{phenomenon_title} | Personal Registry</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;800&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                background: #030712;
                color: #f3f4f6;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                position: relative;
            }}
            canvas {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 1;
            }}
            .container {{
                position: relative;
                z-index: 2;
                width: 90%;
                max-width: 420px;
                padding: 35px 25px;
                background: rgba(17, 24, 39, 0.65);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 28px;
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), inset 0 0 20px rgba(56, 189, 248, 0.1);
                text-align: center;
                animation: fadeIn 1.2s ease-out;
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px) scale(0.95); }}
                to {{ opacity: 1; transform: translateY(0) scale(1); }}
            }}
            .badge {{
                display: inline-block;
                padding: 6px 16px;
                background: rgba(56, 189, 248, 0.15);
                border: 1px solid rgba(56, 189, 248, 0.4);
                color: #38bdf8;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 1px;
                text-transform: uppercase;
                margin-bottom: 20px;
            }}
            h1 {{
                font-size: 26px;
                font-weight: 800;
                color: #ffffff;
                margin-bottom: 8px;
                text-shadow: 0 0 15px rgba(56, 189, 248, 0.3);
            }}
            .location {{
                font-size: 14px;
                color: #9ca3af;
                margin-bottom: 25px;
            }}
            .location b {{ color: #e5e7eb; }}
            .message-box {{
                background: rgba(255, 255, 255, 0.03);
                border-left: 3px solid #38bdf8;
                padding: 16px 20px;
                border-radius: 0 16px 16px 0;
                margin: 20px 0;
                text-align: left;
                font-size: 15px;
                line-height: 1.6;
                color: #f3f4f6;
                font-style: italic;
            }}
            .sender {{
                text-align: right;
                font-size: 14px;
                font-weight: 600;
                color: #38bdf8;
                margin-top: 10px;
            }}
            .cert-id {{
                margin-top: 30px;
                font-size: 11px;
                color: #6b7280;
                letter-spacing: 2px;
                text-transform: uppercase;
            }}
            .audio-btn {{
                margin-top: 20px;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.2);
                color: white;
                padding: 10px 18px;
                border-radius: 50px;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.3s;
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }}
            .audio-btn:hover {{ background: rgba(56, 189, 248, 0.2); border-color: #38bdf8; }}
        </style>
    </head>
    <body>
        <canvas id="canvas"></canvas>

        <div class="container">
            <div class="badge">Сертифікат Події</div>
            <h1>{phenomenon_title}</h1>
            <div class="location">Зареєстровано в місті <b>{city.capitalize()}</b></div>
            
            <div class="message-box">
                «{message}»
                <div class="sender">— {sender}</div>
            </div>

            <button class="audio-btn" onclick="toggleAudio()">
                <span id="audioIcon">🔊</span> <span id="audioText">Увімкнути атмосферу</span>
            </button>

            <div class="cert-id">Офіційний реєстр #{order_id}</div>
        </div>

        <script>
            const PHENOMENON = "{phenomenon}";
            const canvas = document.getElementById('canvas');
            const ctx = canvas.getContext('2d');
            let width = canvas.width = window.innerWidth;
            let height = canvas.height = window.innerHeight;

            window.addEventListener('resize', () => {{
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }});

            let particles = [];
            let flashOpacity = 0;

            if (PHENOMENON === 'first_snow') {{
                particles = Array.from({{ length: 80 }}, () => ({{
                    x: Math.random() * width,
                    y: Math.random() * height,
                    r: Math.random() * 2.5 + 1,
                    speedY: Math.random() * 0.8 + 0.3,
                    speedX: Math.random() * 0.6 - 0.3,
                    opacity: Math.random() * 0.7 + 0.3
                }}));
            }} else if (PHENOMENON === 'thunderstorm') {{
                particles = Array.from({{ length: 140 }}, () => ({{
                    x: Math.random() * width,
                    y: Math.random() * height,
                    length: Math.random() * 25 + 15,
                    speed: Math.random() * 12 + 12,
                    opacity: Math.random() * 0.5 + 0.2
                }}));
            }} else if (PHENOMENON === 'fog') {{
                particles = Array.from({{ length: 25 }}, () => ({{
                    x: Math.random() * width,
                    y: Math.random() * height,
                    r: Math.random() * 100 + 80,
                    speedX: Math.random() * 0.3 - 0.15,
                    opacity: Math.random() * 0.12 + 0.03
                }}));
            }} else if (PHENOMENON === 'clear') {{
                particles = Array.from({{ length: 60 }}, () => ({{
                    x: Math.random() * width,
                    y: Math.random() * height,
                    r: Math.random() * 1.8 + 0.5,
                    pulse: Math.random() * 0.02 + 0.005,
                    opacity: Math.random() * 0.8 + 0.2
                }}));
            }} else {{ // Rain (default)
                particles = Array.from({{ length: 90 }}, () => ({{
                    x: Math.random() * width,
                    y: Math.random() * height,
                    length: Math.random() * 15 + 8,
                    speed: Math.random() * 6 + 5,
                    opacity: Math.random() * 0.35 + 0.1
                }}));
            }}

            function draw() {{
                ctx.clearRect(0, 0, width, height);

                if (PHENOMENON === 'first_snow') {{
                    ctx.fillStyle = '#ffffff';
                    particles.forEach(p => {{
                        ctx.beginPath();
                        ctx.globalAlpha = p.opacity;
                        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                        ctx.fill();
                        p.y += p.speedY;
                        p.x += p.speedX;
                        if (p.y > height) {{ p.y = -5; p.x = Math.random() * width; }}
                    }});
                }} else if (PHENOMENON === 'thunderstorm') {{
                    ctx.strokeStyle = '#a855f7';
                    ctx.lineWidth = 1.2;
                    particles.forEach(p => {{
                        ctx.beginPath();
                        ctx.globalAlpha = p.opacity;
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p.x - 2, p.y + p.length);
                        ctx.stroke();
                        p.y += p.speed;
                        if (p.y > height) {{ p.y = -p.length; p.x = Math.random() * width; }}
                    }});

                    if (Math.random() < 0.008) flashOpacity = 0.35;
                    if (flashOpacity > 0) {{
                        ctx.fillStyle = `rgba(255, 255, 255, ${{flashOpacity}})`;
                        ctx.fillRect(0, 0, width, height);
                        flashOpacity -= 0.02;
                    }}
                }} else if (PHENOMENON === 'fog') {{
                    particles.forEach(p => {{
                        ctx.beginPath();
                        ctx.globalAlpha = p.opacity;
                        let grad = ctx.createRadialGradient(p.x, p.y, 10, p.x, p.y, p.r);
                        grad.addColorStop(0, '#94a3b8');
                        grad.addColorStop(1, 'transparent');
                        ctx.fillStyle = grad;
                        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                        ctx.fill();
                        p.x += p.speedX;
                        if (p.x > width + p.r) p.x = -p.r;
                    }});
                }} else if (PHENOMENON === 'clear') {{
                    ctx.fillStyle = '#fef08a';
                    particles.forEach(p => {{
                        ctx.beginPath();
                        p.opacity += p.pulse;
                        if (p.opacity > 0.9 || p.opacity < 0.1) p.pulse = -p.pulse;
                        ctx.globalAlpha = Math.max(0, Math.min(1, p.opacity));
                        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                        ctx.fill();
                    }});
                }} else {{ // Rain
                    ctx.strokeStyle = '#38bdf8';
                    ctx.lineWidth = 1;
                    particles.forEach(p => {{
                        ctx.beginPath();
                        ctx.globalAlpha = p.opacity;
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p.x, p.y + p.length);
                        ctx.stroke();
                        p.y += p.speed;
                        if (p.y > height) {{ p.y = -p.length; p.x = Math.random() * width; }}
                    }});
                }}
                requestAnimationFrame(draw);
            }}
            draw();

            // Проверенные универсальные MP3-аудиодорожки
            const SOUNDS = {{
                'rain': 'https://cdn.pixabay.com/download/audio/2022/05/16/audio_db6591201e.mp3',
                'first_snow': 'https://cdn.pixabay.com/download/audio/2022/01/18/audio_d0a13f69d2.mp3',
                'thunderstorm': 'https://cdn.pixabay.com/download/audio/2021/08/09/audio_8245582c61.mp3',
                'fog': 'https://cdn.pixabay.com/download/audio/2022/03/24/audio_34b3f3b900.mp3',
                'clear': 'https://cdn.pixabay.com/download/audio/2021/09/06/audio_03d98fb870.mp3'
            }};

            let audio = null;
            let isPlaying = false;

            function toggleAudio() {{
                if (!isPlaying) {{
                    const soundUrl = SOUNDS[PHENOMENON] || SOUNDS['rain'];
                    audio = new Audio(soundUrl);
                    audio.loop = true;
                    audio.volume = 0.5;

                    audio.play().then(() => {{
                        isPlaying = true;
                        document.getElementById('audioText').innerText = 'Вимкнути атмосферу';
                        document.getElementById('audioIcon').innerText = '🔇';
                    }}).catch(e => {{
                        console.log("Audio play error:", e);
                    }});
                }} else {{
                    if (audio) {{
                        audio.pause();
                        audio = null;
                    }}
                    isPlaying = false;
                    document.getElementById('audioText').innerText = 'Увімкнути атмосферу';
                    document.getElementById('audioIcon').innerText = '🔊';
                }}
            }}
        </script>
    </body>
    </html>
    """
