import asyncio
import sqlite3
import uuid
import requests
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI()

# ---------------------------------------------------------
# 🔑 ВСТАВЬТЕ ВАШИ КЛЮЧИ СЮДА (Строки 14 и 15)
# ---------------------------------------------------------
WEATHER_API_KEY = "2de4b7fbe5dd6de7e15810555d61457f"
TELEGRAM_BOT_TOKEN = "8539880858:AAH-LroXnwOpZq4v8p-qmnhDOkd3thDaWIA"

PHENOMENA = {
    "rain": {"name_ua": "🌧️ Дощ", "min_id": 200, "max_id": 531},
    "first_snow": {"name_ua": "❄️ Перший сніг", "min_id": 600, "max_id": 622},
    "thunderstorm": {"name_ua": "🌩️ Гроза", "min_id": 200, "max_id": 232},
    "fog": {"name_ua": "🌫️ Туман", "min_id": 701, "max_id": 781},
    "clear": {"name_ua": "☀️ Ясне небо / Повня", "min_id": 800, "max_id": 800},
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
            status TEXT
        )
    """
    )
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# ОТПРАВКА В TELEGRAMИ ПРОВЕРКА ПОГОДЫ
# ---------------------------------------------------------
def send_notification(
    order_id, sender, recipient_chat_id, message, city, phenomenon_name, temp
):
    cert_url = f"https://rain-program.onrender.com/cert/{order_id}"

    text = (
        f"✨ **Прямо зараз у м. {city.capitalize()} розпочалося явище: {phenomenon_name}!**\n\n"
        f"І його заброньовано спеціально для вас.\n"
        f"🌡 Температура: {temp}°C\n"
        f"💬 Послання від {sender}: «{message}»\n\n"
        f"📜 Ваш персональний цифровий сертифікат: {cert_url}"
    )

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    res = requests.post(
        tg_url,
        json={
            "chat_id": recipient_chat_id,
            "text": text,
            "parse_mode": "Markdown",
        },
    )
    print(f"Ответ Telegram: {res.status_code} - {res.text}")


def check_all_active_cities():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT city FROM orders WHERE status = 'pending'")
    active_cities = cursor.fetchall()

    checked_count = 0
    for (city,) in active_cities:
        checked_count += 1
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
            res = requests.get(url, timeout=10).json()

            if res.get("cod") == 200:
                weather_id = res["weather"][0]["id"]
                temp = res["main"]["temp"]

                cursor.execute(
                    "SELECT id, sender, recipient_chat_id, message, phenomenon FROM orders WHERE city = ? AND status = 'pending'",
                    (city,),
                )
                orders = cursor.fetchall()

                for order in orders:
                    (
                        order_id,
                        sender,
                        recipient_chat_id,
                        message,
                        phenomenon_key,
                    ) = order
                    rules = PHENOMENA.get(phenomenon_key)

                    if (
                        rules
                        and rules["min_id"] <= weather_id <= rules["max_id"]
                    ):
                        send_notification(
                            order_id,
                            sender,
                            recipient_chat_id,
                            message,
                            city,
                            rules["name_ua"],
                            temp,
                        )
                        cursor.execute(
                            "UPDATE orders SET status = 'sent' WHERE id = ?",
                            (order_id,),
                        )
                        conn.commit()
        except Exception as e:
            print(f"Ошибка проверки города {city}: {e}")

    conn.close()
    return checked_count


# Эндпоинт для авто-будильника (Cron-job)
@app.get("/cron-check")
def cron_trigger():
    count = check_all_active_cities()
    return {"status": "success", "checked_cities": count}


# Ручной тест отправки прямо из админки
@app.get("/admin/test-trigger")
def manual_test():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, sender, recipient_chat_id, message, city, phenomenon FROM orders WHERE status = 'pending' ORDER BY rowid DESC LIMIT 1"
    )
    order = cursor.fetchone()
    conn.close()

    if not order:
        return HTMLResponse(
            "<h3>⚠️ Нет активных заказов со статусом 'pending'</h3><a href='/'>Назад</a>"
        )

    order_id, sender, recipient_chat_id, message, city, phenomenon = order
    rules = PHENOMENA.get(phenomenon, {"name_ua": phenomenon})

    send_notification(
        order_id,
        sender,
        recipient_chat_id,
        message,
        city,
        rules.get("name_ua", phenomenon),
        "+18",
    )
    return HTMLResponse(
        f"<h3>🚀 Тестовое сообщение отправлено в Telegram для #{order_id}!</h3><a href='/'>Назад</a>"
    )


# ---------------------------------------------------------
# СТРАНИЦЫ И ФОРМЫ
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def admin_page():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, sender, city, phenomenon, status FROM orders ORDER BY rowid DESC LIMIT 5"
    )
    recent_orders = cursor.fetchall()
    conn.close()

    orders_html = "".join(
        [
            f"<li><b>#{o[0]}</b> | {o[1]} ➔ {o[2].capitalize()} ({o[3]}) - <i>{o[4]}</i> [<a href='/cert/{o[0]}' target='_blank'>Смотреть</a>]</li>"
            for o in recent_orders
        ]
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Забронювати емоцію</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: sans-serif; background: #0f172a; color: white; padding: 20px; }}
            .form-box {{ max-width: 450px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 16px; }}
            input, select, textarea {{ width: 100%; padding: 12px; margin: 8px 0 16px 0; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; }}
            button {{ width: 100%; padding: 14px; background: #38bdf8; color: black; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; margin-bottom: 10px; }}
            .btn-test {{ background: #a855f7; color: white; }}
            ul {{ font-size: 13px; color: #cbd5e1; padding-left: 20px; }}
            a {{ color: #38bdf8; }}
        </style>
    </head>
    <body>
        <div class="form-box">
            <h2>✨ Забронювати явище</h2>
            <form action="/create-order" method="post">
                <label>Ім'я відправника:</label>
                <input type="text" name="sender" placeholder="Олександр" required>
                
                <label>Telegram ID отримувача (цифры):</label>
                <input type="text" name="recipient_chat_id" placeholder="Например: 582910482" required>
                
                <label>Місто світу:</label>
                <input type="text" name="city" placeholder="Bratislava, Kyiv, Paris" required>
                
                <label>Природне явище:</label>
                <select name="phenomenon">
                    <option value="rain">🌧️ Дощ</option>
                    <option value="first_snow">❄️ Перший сніг</option>
                    <option value="thunderstorm">🌩️ Гроза</option>
                    <option value="fog">🌫️ Туман</option>
                    <option value="clear">☀️ Ясне небо / Повня</option>
                </select>
                
                <label>Ваше послання:</label>
                <textarea name="message" rows="3" placeholder="Пусть этот дождь напомнит о нас..." required></textarea>
                
                <button type="submit">Забронювати за $50</button>
            </form>

            <a href="/admin/test-trigger"><button class="btn-test">🚀 Ручной тест отправки последнего заказа</button></a>

            <h3>Последние бронирования:</h3>
            <ul>{orders_html if orders_html else "<li>Нет заказов</li>"}</ul>
        </div>
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
):
    clean_city = city.strip().lower()

    check_url = f"https://api.openweathermap.org/data/2.5/weather?q={clean_city}&appid={WEATHER_API_KEY}"
    res = requests.get(check_url).json()

    if res.get("cod") != 200:
        return HTMLResponse(
            "<h3>❌ Помилка: Місто не знайдено. Перевірте назву.</h3><a href='/'>Назад</a>"
        )

    order_id = str(uuid.uuid4())[:8]
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (
            order_id,
            sender,
            recipient_chat_id,
            message,
            clean_city,
            phenomenon,
        ),
    )
    conn.commit()
    conn.close()

    return HTMLResponse(
        f"<h3>✅ Забронювано! Очікуємо явлення в м. {clean_city.capitalize()} (#{order_id}).</h3><a href='/'>Назад</a>"
    )


@app.get("/cert/{order_id}", response_class=HTMLResponse)
def view_certificate(order_id: str):
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sender, message, city, phenomenon FROM orders WHERE id = ?",
        (order_id,),
    )
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
            canvas {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; }}
            .container {{
                position: relative;
                z-index: 2;
                width: 90%;
                max-width: 420px;
                padding: 35px 25px;
                background: rgba(17, 24, 39, 0.65);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 28px;
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
                text-align: center;
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
                text-transform: uppercase;
                margin-bottom: 20px;
            }}
            h1 {{ font-size: 26px; font-weight: 800; color: #ffffff; margin-bottom: 8px; }}
            .location {{ font-size: 14px; color: #9ca3af; margin-bottom: 25px; }}
            .message-box {{
                background: rgba(255, 255, 255, 0.03);
                border-left: 3px solid #38bdf8;
                padding: 16px 20px;
                border-radius: 0 16px 16px 0;
                margin: 20px 0;
                text-align: left;
                font-size: 15px;
                color: #f3f4f6;
                font-style: italic;
            }}
            .sender {{ text-align: right; font-size: 14px; font-weight: 600; color: #38bdf8; margin-top: 10px; }}
            .audio-btn {{
                margin-top: 20px;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.2);
                color: white;
                padding: 12px 22px;
                border-radius: 50px;
                font-size: 14px;
                cursor: pointer;
            }}
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

            <button class="audio-btn" onclick="toggleAtmosphere()">
                <span id="audioIcon">🔊</span> <span id="audioText">Увімкнути атмосферу</span>
            </button>
        </div>

        <script>
            const PHENOMENON = "{phenomenon}";
            const canvas = document.getElementById('canvas');
            const ctx = canvas.getContext('2d');
            let width = canvas.width = window.innerWidth;
            let height = canvas.height = window.innerHeight;

            let particles = Array.from({{ length: 90 }}, () => ({{
                x: Math.random() * width,
                y: Math.random() * height,
                length: Math.random() * 18 + 10,
                speed: Math.random() * 8 + 6,
                opacity: Math.random() * 0.4 + 0.2
            }}));

            function draw() {{
                ctx.clearRect(0, 0, width, height);
                ctx.strokeStyle = PHENOMENON === 'thunderstorm' ? '#a855f7' : '#38bdf8';
                ctx.lineWidth = 1.2;

                particles.forEach(p => {{
                    ctx.beginPath();
                    ctx.globalAlpha = p.opacity;
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(p.x, p.y + p.length);
                    ctx.stroke();
                    p.y += p.speed;
                    if (p.y > height) {{ p.y = -p.length; p.x = Math.random() * width; }}
                }});
                requestAnimationFrame(draw);
            }}
            draw();

            // Автономный WebAudio синтезатор (работает везде 100%)
            let audioCtx = null, noiseNode = null, gainNode = null, isPlaying = false;

            function toggleAtmosphere() {{
                const btnText = document.getElementById('audioText');
                const btnIcon = document.getElementById('audioIcon');

                if (!isPlaying) {{
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    const bufferSize = audioCtx.sampleRate * 2;
                    const noiseBuffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
                    const output = noiseBuffer.getChannelData(0);

                    let lastOut = 0.0;
                    for (let i = 0; i < bufferSize; i++) {{
                        let white = Math.random() * 2 - 1;
                        output[i] = (lastOut + (0.02 * white)) / 1.02;
                        lastOut = output[i];
                        output[i] *= 3.5;
                    }}

                    noiseNode = audioCtx.createBufferSource();
                    noiseNode.buffer = noiseBuffer;
                    noiseNode.loop = true;

                    const filter = audioCtx.createBiquadFilter();
                    filter.type = 'lowpass';
                    filter.frequency.value = PHENOMENON === 'thunderstorm' ? 800 : 400;

                    gainNode = audioCtx.createGain();
                    gainNode.gain.setValueAtTime(0.12, audioCtx.currentTime);

                    noiseNode.connect(filter);
                    filter.connect(gainNode);
                    gainNode.connect(audioCtx.destination);

                    noiseNode.start();
                    isPlaying = true;
                    btnText.innerText = 'Вимкнути атмосферу';
                    btnIcon.innerText = '🔇';
                }} else {{
                    if (gainNode) {{
                        gainNode.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + 0.3);
                        setTimeout(() => {{ if(noiseNode) noiseNode.stop(); if(audioCtx) audioCtx.close(); }}, 300);
                    }}
                    isPlaying = false;
                    btnText.innerText = 'Увімкнути атмосферу';
                    btnIcon.innerText = '🔊';
                }}
            }}
        </script>
    </body>
    </html>
    """
