import asyncio
import sqlite3
import uuid
import requests
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI()

# ---------------------------------------------------------
# НАСТРОЙКИ (Вставьте свои данные)
# ---------------------------------------------------------
WEATHER_API_KEY = "ВАШ_OPENWEATHER_API_KEY"
TELEGRAM_BOT_TOKEN = "ВАШ_TELEGRAM_BOT_TOKEN"
ADMIN_PIN = "1234"  # ПИН-код для входа в панель владельца

PHENOMENA = {
    "rain": {"name": "🌧️ Дождь", "min_id": 200, "max_id": 531},
    "first_snow": {"name": "❄️ Первый Снег Сезона (Аукцион)", "min_id": 600, "max_id": 622},
    "thunderstorm": {"name": "🌩️ Гроза", "min_id": 200, "max_id": 232},
    "fog": {"name": "🌫️ Туман", "min_id": 701, "max_id": 781},
    "clear": {"name": "☀️ Ясное небо / Полнолуние", "min_id": 800, "max_id": 800},
}


# ---------------------------------------------------------
# БАЗА ДАННЫХ
# ---------------------------------------------------------
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
            status TEXT
        )
    """
    )
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# ОТПРАВКА УВЕДОМЛЕНИЙ
# ---------------------------------------------------------
def send_notification(order_id, sender, recipient_chat_id, message, city, phenomenon_name, temp):
    cert_url = f"https://kyiv-rain-service.onrender.com/cert/{order_id}"

    text = (
        f"✨ **Прямо сейчас в г. {city.capitalize()} началось событие: {phenomenon_name}!**\n\n"
        f"И его эксклюзивно забронировали для вас.\n"
        f"🌡 Температура: {temp}°C\n"
        f"💬 Послание от {sender}: «{message}»\n\n"
        f"📜 Ваш персональный цифровой сертификат: {cert_url}"
    )

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(
        tg_url,
        json={
            "chat_id": recipient_chat_id,
            "text": text,
            "parse_mode": "Markdown",
        },
    )


# ---------------------------------------------------------
# ФОНОВАЯ ПРОВЕРКА ПОГОДЫ
# ---------------------------------------------------------
def check_all_active_cities():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT city FROM orders WHERE status = 'pending'")
    active_cities = cursor.fetchall()

    for (city,) in active_cities:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
            res = requests.get(url).json()

            if res.get("cod") == 200:
                weather_id = res["weather"][0]["id"]
                temp = res["main"]["temp"]

                # Для аукциона на Первый Снег выбираем ТОЛЬКО самую высокую ставку
                cursor.execute(
                    """
                    SELECT id, sender, recipient_chat_id, message, phenomenon, price, is_auction 
                    FROM orders 
                    WHERE city = ? AND status = 'pending'
                    ORDER BY price DESC
                """,
                    (city,),
                )
                orders = cursor.fetchall()

                processed_auctions = set()

                for order in orders:
                    (order_id, sender, recipient_chat_id, message, phenomenon_key, price, is_auction) = order
                    rules = PHENOMENA.get(phenomenon_key)

                    # Если это аукцион, обрабатываем только 1 победителя с максимальной ставкой
                    if is_auction and phenomenon_key in processed_auctions:
                        continue

                    if rules and rules["min_id"] <= weather_id <= rules["max_id"]:
                        send_notification(
                            order_id, sender, recipient_chat_id, message, city, rules["name"], temp
                        )
                        cursor.execute("UPDATE orders SET status = 'sent' WHERE id = ?", (order_id,))
                        conn.commit()

                        if is_auction:
                            processed_auctions.add(phenomenon_key)
        except Exception as e:
            print(f"Ошибка проверки города {city}: {e}")

    conn.close()


async def background_weather_checker():
    while True:
        check_all_active_cities()
        await asyncio.sleep(600)  # Каждые 10 минут


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_weather_checker())


# ---------------------------------------------------------
# ИНТЕРФЕЙС КЛИЕНТА
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home_page():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Забронировать Эмоцию</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: -apple-system, sans-serif; background: #0f172a; color: white; padding: 15px; margin: 0; }
            .card { max-width: 480px; margin: 20px auto; background: #1e293b; padding: 20px; border-radius: 16px; border: 1px solid #334155; }
            h2 { color: #7dd3fc; margin-top: 0; }
            label { font-size: 14px; color: #94a3b8; display: block; margin-top: 10px; }
            input, select, textarea { width: 100%; padding: 12px; margin-top: 5px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; font-size: 15px; }
            .price-tag { background: rgba(56, 189, 248, 0.1); border: 1px solid #38bdf8; padding: 10px; border-radius: 8px; margin: 15px 0; text-align: center; color: #38bdf8; font-weight: bold; }
            button { width: 100%; padding: 14px; background: #38bdf8; color: black; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; margin-top: 15px; }
            .auction-badge { background: #f59e0b; color: black; font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>✨ Забронировать природное явление</h2>
            <form action="/create-order" method="post">
                <label>Ваше имя (отправитель):</label>
                <input type="text" name="sender" placeholder="Александр" required>
                
                <label>Telegram ID получателя:</label>
                <input type="text" name="recipient_chat_id" placeholder="например: 987654321" required>
                
                <label>Город мира:</label>
                <input type="text" name="city" placeholder="Kyiv, Paris, London, Tokyo" required>
                
                <label>Явление:</label>
                <select name="phenomenon" id="phenomenonSelect" onchange="toggleAuction()">
                    <option value="rain">🌧️ Дождь ($15)</option>
                    <option value="thunderstorm">🌩️ Гроза ($15)</option>
                    <option value="fog">🌫️ Туман ($15)</option>
                    <option value="clear">☀️ Ясное небо / Полнолуние ($15)</option>
                    <option value="first_snow">❄️ Первый Снег Сезона (АУКЦИОН)</option>
                </select>
                
                <div id="priceBox" class="price-tag">Стоимость бронирования: $15</div>

                <div id="auctionBox" style="display:none;">
                    <label>Ваша ставка для аукциона ($):</label>
                    <input type="number" name="bid_price" value="25" min="20">
                    <p style="font-size: 12px; color: #f59e0b; margin-top: 4px;">⚠️ Правом на «Первый снег» в выбранном городе овладеет только тот, чья ставка будет высшей на момент снегопада.</p>
                </div>

                <label>Ваше теплое послание:</label>
                <textarea name="message" rows="3" placeholder="Пусть этот момент напомнит тебе о нас..." required></textarea>
                
                <button type="submit">Оформить подарок</button>
            </form>
        </div>

        <script>
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
    recipient_chat_id: str = Form(...),
    city: str = Form(...),
    phenomenon: str = Form(...),
    message: str = Form(...),
    bid_price: float = Form(15.0),
):
    clean_city = city.strip().lower()

    # Проверка существования города и блокировка РФ
    check_url = f"https://api.openweathermap.org/data/2.5/weather?q={clean_city}&appid={WEATHER_API_KEY}"
    res = requests.get(check_url).json()

    if res.get("cod") != 200:
        return HTMLResponse("<h3>❌ Город не найден. Укажите имя на английском или русском.</h3><a href='/'>Назад</a>")

    if res.get("sys", {}).get("country") == "RU":
        return HTMLResponse("<h3>⛔ Данный регион недоступен для бронирования.</h3><a href='/'>Назад</a>")

    is_auction = 1 if phenomenon == "first_snow" else 0
    final_price = bid_price if is_auction else 15.0
    order_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
        (order_id, sender, recipient_chat_id, message, clean_city, phenomenon, final_price, is_auction),
    )
    conn.commit()
    conn.close()

    type_str = "Ставка на Аукцион" if is_auction else "Бронирование"
    return HTMLResponse(
        f"<h3>✅ {type_str} принята! Сумма: ${final_price} (ID: #{order_id}).</h3><a href='/'>Назад</a>"
    )


# ---------------------------------------------------------
# ПАНЕЛЬ ВЛАДЕЛЬЦА И ТЕСТИРОВАНИЕ
# ---------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_panel(pin: str = ""):
    if pin != ADMIN_PIN:
        return """
        <body style="background:#0f172a;color:white;font-family:sans-serif;padding:30px;">
            <form method="get" style="max-width:300px;margin:auto;">
                <h3>🔒 Вход в панель владельца</h3>
                <input type="password" name="pin" placeholder="Введите PIN-код" style="width:100%;padding:10px;margin-bottom:10px;">
                <button style="width:100%;padding:10px;background:#38bdf8;">Войти</button>
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
        auc_tag = " [АУКЦИОН]" if is_auc else ""
        rows += f"""
        <tr style="border-bottom:1px solid #334155;">
            <td style="padding:8px;">#{o_id}</td>
            <td style="padding:8px;">{sender}</td>
            <td style="padding:8px;">{tg_id}</td>
            <td style="padding:8px;">{city.capitalize()}</td>
            <td style="padding:8px;">{phenom}{auc_tag}</td>
            <td style="padding:8px;">${price}</td>
            <td style="padding:8px;">{status}</td>
            <td style="padding:8px;">
                <form action="/admin/test-trigger" method="post" style="margin:0;">
                    <input type="hidden" name="pin" value="{ADMIN_PIN}">
                    <input type="hidden" name="order_id" value="{o_id}">
                    <button style="background:#22c55e;color:black;border:none;padding:6px 12px;border-radius:4px;font-weight:bold;cursor:pointer;">🚀 Тест отправки</button>
                </form>
            </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Панель управления</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: sans-serif; background: #0f172a; color: white; padding: 15px; }}
            table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
            th {{ background: #334155; text-align: left; padding: 10px; font-size: 14px; }}
        </style>
    </head>
    <body>
        <h2>👑 Панель управления и тестирования</h2>
        <div style="overflow-x:auto;">
            <table>
                <tr>
                    <th>ID</th><th>Отправитель</th><th>Telegram ID</th><th>Город</th><th>Явление</th><th>Цена</th><th>Статус</th><th>Действие</th>
                </tr>
                {rows}
            </table>
        </div>
    </body>
    </html>
    """


@app.post("/admin/test-trigger")
def test_trigger(pin: str = Form(...), order_id: str = Form(...)):
    if pin != ADMIN_PIN:
        return "Ошибка доступа"

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT sender, recipient_chat_id, message, city, phenomenon FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()

    if order:
        sender, recipient_chat_id, message, city, phenomenon_key = order
        rules = PHENOMENA.get(phenomenon_key, {"name": "🌩️ Тестовое Явление"})

        # Принудительная отправка тестового сообщения прямо сейчас
        send_notification(order_id, sender, recipient_chat_id, message, city, f"{rules['name']} (ТЕСТ)", 18.5)
        return HTMLResponse(f"<h3>✅ Тестовое сообщение отправлено для #{order_id}! Проверьте Telegram.</h3><a href='/admin?pin={ADMIN_PIN}'>Назад в админку</a>")

    return "Заказ не найден"


# ---------------------------------------------------------
# ИНТЕРАКТИВНЫЙ СЕРТИФИКАТ ПОЛУЧАТЕЛЯ
# ---------------------------------------------------------
@app.get("/cert/{order_id}", response_class=HTMLResponse)
def view_certificate(order_id: str):
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT sender, message, city, phenomenon FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()

    if not order:
        return "Сертификат не найден"

    sender, message, city, phenomenon = order
    phenomenon_title = PHENOMENA.get(phenomenon, {}).get("name", phenomenon)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{phenomenon_title}</title>
        <style>
            body {{ margin: 0; background: #0b131f; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; text-align: center; }}
            .card {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); padding: 30px; border-radius: 20px; max-width: 85%; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
            h1 {{ color: #7dd3fc; font-size: 22px; }}
            .msg {{ font-style: italic; margin: 20px 0; color: #e2e8f0; border-left: 3px solid #38bdf8; padding-left: 12px; text-align: left; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>{phenomenon_title}</h1>
            <p style="color: #94a3b8;">Зарегистрировано в городе <b>{city.capitalize()}</b> специально для вас.</p>
            <div class="msg">«{message}»</div>
            <p style="text-align: right; color: #7dd3fc;">— {sender}</p>
        </div>
    </body>
    </html>
    """
