import asyncio
import sqlite3
import uuid
import requests
from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse

app = FastAPI()

# ---------------------------------------------------------
# 🔑 НАСТРОЙКИ
# ---------------------------------------------------------
WEATHER_API_KEY = "2de4b7fbe5dd6de7e15810555d61457f"
TELEGRAM_BOT_TOKEN = "8539880858:AAH-LroXnwOpZq4v8p-qmnhDOkd3thDaWIA"
ADMIN_PIN = "122595"

PHENOMENA = {
    "rain": {"name_ua": "🌧️ Дощ", "desc": "Для затишку та теплих спогадів", "min_id": 200, "max_id": 531},
    "first_snow": {"name_ua": "❄️ Перший сніг", "desc": "Для відчуття чистого дива", "min_id": 600, "max_id": 622},
    "thunderstorm": {"name_ua": "🌩️ Гроза", "desc": "Для пристрасті та яскравих емоцій", "min_id": 200, "max_id": 232},
    "fog": {"name_ua": "🌫️ Туман", "desc": "Для таємничих размов", "min_id": 701, "max_id": 781},
    "clear": {"name_ua": "☀️ Ясне небо / Повня", "desc": "Для тишини та натхнення", "min_id": 800, "max_id": 800},
}

def init_db():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            sender TEXT,
            recipient_chat_id TEXT,
            message TEXT,
            city TEXT,
            phenomenon TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# ГЛАВНАЯ СТРАНИЦА (СВЕТЛЫЙ ПАСТЕЛЬНЫЙ МИНИМАЛИЗМ)
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home_page():
    return f"""
    <!DOCTYPE html>
    <html lang="ua">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Подаруйте явище неба | Personal Sky Registry</title>
        <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,400&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #fcfaf7;
                --card-bg: rgba(255, 255, 255, 0.88);
                --text-main: #2c2a29;
                --text-muted: #78716c;
                --accent-blue: #0284c7;
                --border: #e7e5e4;
            }}

            * {{ box-sizing: border-box; margin: 0; padding: 0; }}

            body {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                background-color: var(--bg);
                color: var(--text-main);
                min-height: 100vh;
                padding: 40px 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
                background-image: 
                    radial-gradient(at 10% 10%, #fef3c7 0px, transparent 50%),
                    radial-gradient(at 90% 20%, #e0f2fe 0px, transparent 50%),
                    radial-gradient(at 50% 90%, #fce7f3 0px, transparent 50%);
                background-attachment: fixed;
            }}

            .header {{
                text-align: center;
                max-width: 620px;
                margin-bottom: 40px;
            }}

            .badge {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 6px 16px;
                background: #ffffff;
                border: 1px solid #f3f4f6;
                border-radius: 100px;
                font-size: 13px;
                color: #78716c;
                box-shadow: 0 4px 12px rgba(0,0,0,0.03);
                margin-bottom: 16px;
            }}

            h1 {{
                font-family: 'Cormorant Garamond', serif;
                font-size: 40px;
                font-weight: 600;
                line-height: 1.2;
                color: #1c1917;
                margin-bottom: 12px;
            }}

            p.subtitle {{
                font-size: 15px;
                color: var(--text-muted);
                line-height: 1.6;
            }}

            .main-layout {{
                display: grid;
                grid-template-columns: 1fr;
                gap: 32px;
                width: 100%;
                max-width: 1020px;
            }}

            @media (min-width: 850px) {{
                .main-layout {{
                    grid-template-columns: 1.15fr 0.85fr;
                    align-items: start;
                }}
            }}

            .card-form {{
                background: var(--card-bg);
                backdrop-filter: blur(20px);
                border: 1px solid #ffffff;
                border-radius: 28px;
                padding: 32px 28px;
                box-shadow: 0 20px 40px -10px rgba(120, 113, 108, 0.08);
            }}

            .section-label {{
                font-size: 12px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1.2px;
                color: #a8a29e;
                margin-bottom: 12px;
                display: block;
            }}

            /* Плитки явлений */
            .phenomenon-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
                gap: 10px;
                margin-bottom: 24px;
            }}

            .phenom-item {{
                background: #ffffff;
                border: 1.5px solid var(--border);
                border-radius: 18px;
                padding: 14px 10px;
                text-align: center;
                cursor: pointer;
                transition: all 0.25s ease;
            }}

            .phenom-item:hover {{
                border-color: #cbd5e1;
                transform: translateY(-2px);
            }}

            .phenom-item.active {{
                border-color: #0284c7;
                background: #f0f9ff;
                box-shadow: 0 4px 14px rgba(2, 132, 199, 0.12);
            }}

            .phenom-icon {{ font-size: 24px; display: block; margin-bottom: 4px; }}
            .phenom-name {{ font-size: 13px; font-weight: 600; color: #1e293b; }}

            /* Поля ввода */
            .input-group {{
                margin-bottom: 20px;
            }}

            .input-group label {{
                display: block;
                font-size: 13px;
                font-weight: 600;
                color: #44403c;
                margin-bottom: 8px;
            }}

            input[type="text"], textarea {{
                width: 100%;
                padding: 14px 16px;
                border: 1.5px solid var(--border);
                border-radius: 14px;
                background: #ffffff;
                font-family: inherit;
                font-size: 14px;
                color: #1c1917;
                transition: border-color 0.2s;
                outline: none;
            }}

            input[type="text"]:focus, textarea:focus {{
                border-color: #0284c7;
                box-shadow: 0 0 0 4px rgba(2, 132, 199, 0.08);
            }}

            .hint-lock {{
                font-size: 12px;
                color: #78716c;
                margin-top: 6px;
                display: flex;
                align-items: center;
                gap: 5px;
            }}

            .btn-submit {{
                width: 100%;
                padding: 16px;
                background: #1c1917;
                color: #ffffff;
                border: none;
                border-radius: 16px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                margin-top: 10px;
                box-shadow: 0 10px 25px -5px rgba(28, 25, 23, 0.2);
            }}

            .btn-submit:hover {{
                background: #292524;
                transform: translateY(-1px);
            }}

            /* Live Preview Card */
            .preview-container {{
                position: sticky;
                top: 40px;
            }}

            .preview-card {{
                background: #ffffff;
                border-radius: 28px;
                padding: 32px 26px;
                border: 1px solid var(--border);
                box-shadow: 0 20px 40px -10px rgba(120, 113, 108, 0.08);
                text-align: center;
            }}

            .preview-badge {{
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                color: #0284c7;
                font-weight: 700;
                margin-bottom: 20px;
                display: inline-block;
                background: #e0f2fe;
                padding: 4px 14px;
                border-radius: 100px;
            }}

            .preview-title {{
                font-family: 'Cormorant Garamond', serif;
                font-size: 30px;
                font-weight: 600;
                margin-bottom: 6px;
                color: #1c1917;
            }}

            .preview-location {{
                font-size: 13px;
                color: #78716c;
                margin-bottom: 24px;
            }}

            .preview-quote {{
                background: #fdfbf7;
                border-left: 3px solid #0284c7;
                padding: 18px 20px;
                border-radius: 0 16px 16px 0;
                font-style: italic;
                font-size: 14px;
                line-height: 1.6;
                color: #44403c;
                text-align: left;
                margin-bottom: 10px;
            }}

            .preview-sender {{
                text-align: right;
                font-style: normal;
                font-weight: 600;
                color: #0284c7;
                margin-top: 8px;
            }}

            .owner-link {{
                display: block;
                text-align: center;
                margin-top: 20px;
                font-size: 12px;
                color: #a8a29e;
                text-decoration: none;
            }}
            .owner-link:hover {{ color: #78716c; }}
        </style>
    </head>
    <body>

        <div class="header">
            <div class="badge">✨ Символічний реєстр природних явищ</div>
            <h1>Подаруйте момент, коли небо заговорить про ваші почуття</h1>
            <p class="subtitle">Забронюйте майбутній дощ, перший сніг або зорепад для близької людини. У момент, коли явище розпочнеться, вона отримає сюрприз.</p>
        </div>

        <div class="main-layout">
            <!-- ФОРМА ЗАКАЗА -->
            <div class="card-form">
                <form action="/create-order" method="post" id="orderForm">
                    <input type="hidden" name="phenomenon" id="selected_phenomenon" value="rain">

                    <span class="section-label">1. Оберіть явище неба</span>
                    <div class="phenomenon-grid">
                        <div class="phenom-item active" onclick="selectPhenomenon('rain', '🌧️ Дощ')">
                            <span class="phenom-icon">🌧️</span>
                            <span class="phenom-name">Дощ</span>
                        </div>
                        <div class="phenom-item" onclick="selectPhenomenon('first_snow', '❄️ Перший сніг')">
                            <span class="phenom-icon">❄️</span>
                            <span class="phenom-name">Перший сніг</span>
                        </div>
                        <div class="phenom-item" onclick="selectPhenomenon('thunderstorm', '🌩️ Гроза')">
                            <span class="phenom-icon">🌩️</span>
                            <span class="phenom-name">Гроза</span>
                        </div>
                        <div class="phenom-item" onclick="selectPhenomenon('fog', '🌫️ Туман')">
                            <span class="phenom-icon">🌫️</span>
                            <span class="phenom-name">Туман</span>
                        </div>
                        <div class="phenom-item" onclick="selectPhenomenon('clear', '☀️ Ясне небо')">
                            <span class="phenom-icon">☀️</span>
                            <span class="phenom-name">Повня / Ясне небо</span>
                        </div>
                    </div>

                    <span class="section-label">2. Деталі сюрпризу</span>

                    <div class="input-group">
                        <label>Як вас назвати в момент підтвердження?</label>
                        <input type="text" name="sender" id="in_sender" placeholder="Олександр" required oninput="updatePreview()">
                    </div>

                    <div class="input-group">
                        <label>Номер або Telegram отримувача:</label>
                        <input type="text" name="recipient_chat_id" placeholder="@username або +380..." required>
                        <div class="hint-lock">
                            <span>🔒</span> Одноразова доставка. Номер видаляється одразу після надсилання.
                        </div>
                    </div>

                    <div class="input-group">
                        <label>Місто, де чекають на явище:</label>
                        <input type="text" name="city" id="in_city" placeholder="Київ, Братислава, Париж..." required oninput="updatePreview()">
                    </div>

                    <div class="input-group">
                        <label>Слова, що прилетять з першою краплею:</label>
                        <textarea name="message" id="in_message" rows="3" placeholder="Нехай цей дощ нагадає, як сильно я про тебе дбаю..." required oninput="updatePreview()"></textarea>
                    </div>

                    <button type="submit" class="btn-submit">Забронювати момент за $3</button>
                </form>
            </div>

            <!-- ИНТЕРАКТИВНЫЙ LIVE PREVIEW -->
            <div class="preview-container">
                <span class="section-label" style="text-align: center;">Так це побачить отримувач:</span>
                <div class="preview-card">
                    <div class="preview-badge">Персональний сертифікат</div>
                    <div class="preview-title" id="prev_phenomenon">🌧️ Дощ</div>
                    <div class="preview-location">Зареєстровано в місті <b id="prev_city" style="color: #1c1917;">Київ</b></div>

                    <div class="preview-quote">
                        «<span id="prev_message">Нехай цей дощ нагадає, як сильно я про тебе дбаю...</span>»
                        <div class="preview-sender">— <span id="prev_sender">Олександр</span></div>
                    </div>
                </div>

                <a href="/admin/test-trigger" class="owner-link">🔐 Вхід для власника (Ручний тест)</a>
            </div>
        </div>

        <script>
            let currentPhenomenonName = "🌧️ Дощ";

            function selectPhenomenon(key, name) {{
                document.getElementById('selected_phenomenon').value = key;
                currentPhenomenonName = name;
                document.getElementById('prev_phenomenon').innerText = name;

                document.querySelectorAll('.phenom-item').forEach(el => el.classList.remove('active'));
                event.currentTarget.classList.add('active');
            }}

            function updatePreview() {{
                const sender = document.getElementById('in_sender').value.trim();
                const city = document.getElementById('in_city').value.trim();
                const message = document.getElementById('in_message').value.trim();

                document.getElementById('prev_sender').innerText = sender ? sender : "Олександр";
                document.getElementById('prev_city').innerText = city ? city : "Київ";
                document.getElementById('prev_message').innerText = message ? message : "Нехай цей дощ нагадає, як сильно я про тебе дбаю...";
            }}
        </script>
    </body>
    </html>
    """

# ---------------------------------------------------------
# ОСТАЛЬНЫЕ ФУНКЦИИ (БЭКЕНД И СЕРТИФИКАТЫ)
# ---------------------------------------------------------
@app.post("/create-order")
def create_order(
    sender: str = Form(...),
    recipient_chat_id: str = Form(...),
    city: str = Form(...),
    phenomenon: str = Form(...),
    message: str = Form(...),
):
    clean_city = city.strip().lower()
    clean_recipient = recipient_chat_id.strip()

    check_url = f"https://api.openweathermap.org/data/2.5/weather?q={clean_city}&appid={WEATHER_API_KEY}"
    res = requests.get(check_url).json()

    if res.get("cod") != 200:
        return HTMLResponse("<h3>❌ Помилка: Місто не знайдено. Перевірте назву.</h3><a href='/'>Назад</a>")

    order_id = str(uuid.uuid4())[:8]
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (order_id, sender, clean_recipient, message, clean_city, phenomenon),
    )
    conn.commit()
    conn.close()

    return HTMLResponse(f"<div style='font-family: sans-serif; padding: 40px; text-align: center;'><h3>✅ Забронювано за $3! Очікуємо явлення в м. {clean_city.capitalize()} (#{order_id}).</h3><a href='/'>На головну</a></div>")

@app.get("/cron-check")
def cron_trigger():
    return {"status": "success"}

@app.get("/admin/test-trigger", response_class=HTMLResponse)
def manual_test(pin: str = Query(None)):
    if pin != ADMIN_PIN:
        return HTMLResponse("""
            <div style='font-family: sans-serif; padding: 40px; text-align: center;'>
                <h3>🔒 Доступ обмежено (Захист владельца)</h3>
                <form action='/admin/test-trigger' method='get'>
                    <input type='password' name='pin' placeholder='Введіть PIN' style='padding: 10px; border-radius: 6px;'>
                    <button type='submit' style='padding: 10px 15px; background: #0284c7; color: white; border: none; border-radius: 6px;'>Увійти</button>
                </form>
                <br><a href='/'>На головну</a>
            </div>
        """)
    return HTMLResponse("<h3>🔐 Авторизовано для тестування</h3><a href='/'>Назад</a>")

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
            }}
            .container {{
                width: 90%;
                max-width: 420px;
                padding: 35px 25px;
                background: rgba(17, 24, 39, 0.75);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 28px;
                text-align: center;
            }}
            .badge {{ display: inline-block; padding: 6px 16px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8; border-radius: 20px; font-size: 12px; margin-bottom: 20px; }}
            h1 {{ font-size: 26px; font-weight: 800; color: #ffffff; margin-bottom: 8px; }}
            .message-box {{ background: rgba(255, 255, 255, 0.03); border-left: 3px solid #38bdf8; padding: 16px 20px; border-radius: 0 16px 16px 0; margin: 20px 0; text-align: left; font-size: 15px; font-style: italic; }}
            .sender {{ text-align: right; font-size: 14px; font-weight: 600; color: #38bdf8; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="badge">Сертифікат Події</div>
            <h1>{phenomenon_title}</h1>
            <div style="color: #9ca3af; font-size: 14px;">Зареєстровано в місті <b>{city.capitalize()}</b></div>
            <div class="message-box">«{message}»<div class="sender">— {sender}</div></div>
        </div>
    </body>
    </html>
    """
