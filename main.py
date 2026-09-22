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
WEATHER_API_KEY = "ВАШ_OPENWEATHER_API_KEY"
TELEGRAM_BOT_TOKEN = "ВАШ_TELEGRAM_BOT_TOKEN"
ADMIN_PIN = "1234"

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
# ГЛАВНАЯ СТРАНИЦА С ИНТЕРАКТИВНЫМ АНИМИРОВАННЫМ ПРЕВЬЮ
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

            /* ИНТЕРАКТИВНОЕ ПРЕВЬЮ С АНИМАЦИЕЙ И ЗВУКОМ */
            .preview-container {{
                position: sticky;
                top: 40px;
            }}

            .preview-card {{
                position: relative;
                overflow: hidden;
                background: #0f172a;
                border-radius: 28px;
                padding: 32px 26px;
                border: 1px solid rgba(255, 255, 255, 0.15);
                box-shadow: 0 20px 40px -10px rgba(15, 23, 42, 0.3);
                text-align: center;
                color: #ffffff;
                transition: background 0.5s ease;
            }}

            .preview-canvas {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 1;
                pointer-events: none;
            }}

            .preview-content {{
                position: relative;
                z-index: 2;
            }}

            .preview-badge {{
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                color: #38bdf8;
                font-weight: 700;
                margin-bottom: 20px;
                display: inline-block;
                background: rgba(56, 189, 248, 0.15);
                border: 1px solid rgba(56, 189, 248, 0.3);
                padding: 4px 14px;
                border-radius: 100px;
            }}

            .preview-title {{
                font-family: 'Cormorant Garamond', serif;
                font-size: 32px;
                font-weight: 600;
                margin-bottom: 6px;
                color: #ffffff;
            }}

            .preview-location {{
                font-size: 13px;
                color: #94a3b8;
                margin-bottom: 24px;
            }}

            .preview-quote {{
                background: rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(8px);
                border-left: 3px solid #38bdf8;
                padding: 18px 20px;
                border-radius: 0 16px 16px 0;
                font-style: italic;
                font-size: 14px;
                line-height: 1.6;
                color: #f1f5f9;
                text-align: left;
                margin-bottom: 20px;
            }}

            .preview-sender {{
                text-align: right;
                font-style: normal;
                font-weight: 600;
                color: #38bdf8;
                margin-top: 8px;
            }}

            .audio-btn {{
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                color: #ffffff;
                padding: 8px 18px;
                border-radius: 50px;
                font-size: 12px;
                cursor: pointer;
                transition: all 0.3s;
                display: inline-flex;
                align-items: center;
                gap: 6px;
            }}

            .audio-btn:hover {{
                background: rgba(56, 189, 248, 0.25);
                border-color: #38bdf8;
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

            <!-- ИНТЕРАКТИВНОЕ LIVE PREVIEW С АНИМАЦИЕЙ И ЗВУКОМ -->
            <div class="preview-container">
                <span class="section-label" style="text-align: center;">Так це побачить отримувач:</span>
                <div class="preview-card" id="prev_card">
                    <canvas class="preview-canvas" id="previewCanvas"></canvas>
                    
                    <div class="preview-content">
                        <div class="preview-badge">Персональний сертифікат</div>
                        <div class="preview-title" id="prev_phenomenon">🌧️ Дощ</div>
                        <div class="preview-location">Зареєстровано в місті <b id="prev_city" style="color: #ffffff;">Київ</b></div>

                        <div class="preview-quote">
                            «<span id="prev_message">Нехай цей дощ нагадає, як сильно я про тебе дбаю...</span>»
                            <div class="preview-sender">— <span id="prev_sender">Олександр</span></div>
                        </div>

                        <button type="button" class="audio-btn" onclick="toggleAtmosphere()">
                            <span id="audioIcon">🔊</span> <span id="audioText">Послухати атмосферу</span>
                        </button>
                    </div>
                </div>

                <a href="/admin/test-trigger" class="owner-link">🔐 Вхід для власника (Ручний тест)</a>
            </div>
        </div>

        <script>
            let currentPhenomenonKey = "rain";
            const canvas = document.getElementById('previewCanvas');
            const ctx = canvas.getContext('2d');
            let width = canvas.width = canvas.offsetWidth;
            let height = canvas.height = canvas.offsetHeight;

            window.addEventListener('resize', () => {{
                width = canvas.width = canvas.offsetWidth;
                height = canvas.height = canvas.offsetHeight;
            }});

            let particles = [];
            let flashOpacity = 0;

            const BACKGROUNDS = {{
                'rain': '#0b1329',
                'first_snow': '#1e293b',
                'thunderstorm': '#2e1065',
                'fog': '#1c1917',
                'clear': '#022c22'
            }};

            function initParticles(key) {{
                particles = [];
                const pCount = key === 'thunderstorm' ? 100 : (key === 'fog' ? 20 : 60);

                for (let i = 0; i < pCount; i++) {{
                    particles.push({{
                        x: Math.random() * width,
                        y: Math.random() * height,
                        r: Math.random() * 2 + 1,
                        length: Math.random() * 15 + 8,
                        speed: Math.random() * 6 + 4,
                        speedX: Math.random() * 0.6 - 0.3,
                        opacity: Math.random() * 0.6 + 0.2
                    }});
                }}
            }}
            initParticles('rain');

            function draw() {{
                ctx.clearRect(0, 0, width, height);

                if (currentPhenomenonKey === 'first_snow') {{
                    ctx.fillStyle = '#ffffff';
                    particles.forEach(p => {{
                        ctx.beginPath();
                        ctx.globalAlpha = p.opacity;
                        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                        ctx.fill();
                        p.y += p.speed * 0.2;
                        p.x += p.speedX;
                        if (p.y > height) {{ p.y = -5; p.x = Math.random() * width; }}
                    }});
                }} else if (currentPhenomenonKey === 'thunderstorm') {{
                    ctx.strokeStyle = '#c084fc';
                    ctx.lineWidth = 1.2;
                    particles.forEach(p => {{
                        ctx.beginPath();
                        ctx.globalAlpha = p.opacity;
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p.x - 2, p.y + p.length);
                        ctx.stroke();
                        p.y += p.speed * 1.5;
                        if (p.y > height) {{ p.y = -p.length; p.x = Math.random() * width; }}
                    }});

                    if (Math.random() < 0.01) flashOpacity = 0.4;
                    if (flashOpacity > 0) {{
                        ctx.fillStyle = `rgba(255, 255, 255, ${{flashOpacity}})`;
                        ctx.fillRect(0, 0, width, height);
                        flashOpacity -= 0.03;
                    }}
                }} else if (currentPhenomenonKey === 'fog') {{
                    particles.forEach(p => {{
                        ctx.beginPath();
                        ctx.globalAlpha = p.opacity * 0.15;
                        let grad = ctx.createRadialGradient(p.x, p.y, 5, p.x, p.y, p.r * 25);
                        grad.addColorStop(0, '#e2e8f0');
                        grad.addColorStop(1, 'transparent');
                        ctx.fillStyle = grad;
                        ctx.arc(p.x, p.y, p.r * 25, 0, Math.PI * 2);
                        ctx.fill();
                        p.x += p.speedX * 0.3;
                        if (p.x > width + 50) p.x = -50;
                    }});
                }} else if (currentPhenomenonKey === 'clear') {{
                    ctx.fillStyle = '#fef08a';
                    particles.forEach(p => {{
                        ctx.beginPath();
                        p.opacity += (Math.random() * 0.02 - 0.01);
                        if (p.opacity > 0.9) p.opacity = 0.9;
                        if (p.opacity < 0.1) p.opacity = 0.1;
                        ctx.globalAlpha = p.opacity;
                        ctx.arc(p.x, p.y, p.r * 0.8, 0, Math.PI * 2);
                        ctx.fill();
                    }});
                }} else {{ // Rain (default)
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

            function selectPhenomenon(key, name) {{
                document.getElementById('selected_phenomenon').value = key;
                currentPhenomenonKey = key;
                document.getElementById('prev_phenomenon').innerText = name;
                document.getElementById('prev_card').style.background = BACKGROUNDS[key] || '#0b1329';

                document.querySelectorAll('.phenom-item').forEach(el => el.classList.remove('active'));
                event.currentTarget.classList.add('active');

                initParticles(key);
                if (isPlaying) restartAudio();
            }}

            function updatePreview() {{
                const sender = document.getElementById('in_sender').value.strip ? document.getElementById('in_sender').value.strip() : document.getElementById('in_sender').value.trim();
                const city = document.getElementById('in_city').value.trim();
                const message = document.getElementById('in_message').value.trim();

                document.getElementById('prev_sender').innerText = sender ? sender : "Олександр";
                document.getElementById('prev_city').innerText = city ? city : "Київ";
                document.getElementById('prev_message').innerText = message ? message : "Нехай цей дощ нагадає, як сильно я про тебе дбаю...";
            }}

            // ЗВУКОВА АТМОСФЕРА (Web Audio API)
            let audioCtx = null, noiseNode = null, gainNode = null, isPlaying = false;

            function toggleAtmosphere() {{
                if (!isPlaying) {{
                    startAudio();
                }} else {{
                    stopAudio();
                }}
            }}

            function startAudio() {{
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
                filter.frequency.value = currentPhenomenonKey === 'thunderstorm' ? 800 : (currentPhenomenonKey === 'first_snow' ? 250 : 450);

                gainNode = audioCtx.createGain();
                gainNode.gain.setValueAtTime(0.12, audioCtx.currentTime);

                noiseNode.connect(filter);
                filter.connect(gainNode);
                gainNode.connect(audioCtx.destination);

                noiseNode.start();
                isPlaying = true;
                document.getElementById('audioText').innerText = 'Вимкнути атмосферу';
                document.getElementById('audioIcon').innerText = '🔇';
            }}

            function stopAudio() {{
                if (gainNode && audioCtx) {{
                    gainNode.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + 0.2);
                    setTimeout(() => {{ if(noiseNode) noiseNode.stop(); if(audioCtx) audioCtx.close(); }}, 200);
                }}
                isPlaying = false;
                document.getElementById('audioText').innerText = 'Послухати атмосферу';
                document.getElementById('audioIcon').innerText = '🔊';
            }}

            function restartAudio() {{
                stopAudio();
                setTimeout(() => startAudio(), 250);
            }}
        </script>
    </body>
    </html>
    """

# ---------------------------------------------------------
# БЭКЕНД И МАРШРУТЫ
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
