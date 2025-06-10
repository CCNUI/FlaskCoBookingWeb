import os


def create_project_structure_and_files():
    """
    一键创建 Flask-SmartBooking-System 项目的目录结构和文件，
    并写入所有提供的代码内容。
    """

    project_name = "Flask-SmartBooking-System"
    base_dir = os.path.join(os.getcwd(), project_name)

    # 定义文件内容，其中包含中文
    file_contents = {
        "readme.md": """
# 优智通科技共修室预约系统 (Flask-SmartBooking-System)

这是一个功能完善、可立即部署的共修室预约系统，采用 Flask 和原生前端技术 (HTML/CSS/JS) 构建。系统界面简洁、响应式，支持手机和桌面端访问，并提供了完整的预约、日志、管理等功能。

A full-featured, deployable booking system for group study rooms, built with Flask and native frontend technologies. Supports both Vercel Serverless (with Redis) and traditional server deployments (with SQLite).

## 核心功能

* **周视图日历**: 以周为单位，清晰展示每日各时段的预约情况。
* **便捷预约**: 点击单元格即可快速预约、修改或取消。
* **操作日志**: 记录每一次预约变动，方便追溯。
* **后台管理**:
    * 密码保护的管理员后台。
    * 管理“斋日”等特殊日期，并在日历上高亮显示。
    * 自定义预约时间段列表。
    * 一键导出所有预约和日志数据为 CSV 文件。
* **响应式设计**: 完美适配桌面和移动设备。
* **双数据库支持**:
    * 可无缝部署到 **Vercel Serverless** 环境，使用 Vercel KV (Redis) 作为数据库。
    * 可在 **传统服务器** 上使用 Gunicorn + Gevent + Nginx 部署，使用 SQLite 作为本地数据库。

## 技术栈

* **后端**: Python 3, Flask
* **前端**: HTML5, CSS3, 原生 JavaScript
* **数据库**: Vercel KV (Redis) 或 SQLite
* **部署**: Vercel / Gunicorn

## 安装与部署

### 1. 准备工作

克隆本仓库并进入项目目录：

```bash
git clone <your-repo-url>
cd Flask-SmartBooking-System
创建并激活虚拟环境：

Bash

python -m venv venv
source venv/bin/activate  # on Windows use `venv\\Scripts\\activate`
安装依赖：

Bash

pip install -r requirements.txt
2. 配置
创建一个 .env 文件，并设置管理员密码：

ADMIN_PASSWORD=your_strong_password_here
对于 Vercel 部署:

你还需要在 Vercel 的环境变量中设置 KV_URL, KV_REST_API_URL, KV_REST_API_TOKEN, 和 KV_REST_API_READ_ONLY_TOKEN。这些值在你创建 Vercel KV 数据库后会自动提供。同时，也需要在 Vercel 中设置 ADMIN_PASSWORD。

3. 本地运行 (使用 SQLite)
首先，初始化数据库：

Bash

flask init-db
然后，启动开发服务器：

Bash

flask run
访问 [http://127.0.0.1:5000](http://127.0.0.1:5000)。

4. 部署到 Vercel
将你的代码推送到 GitHub/GitLab/Bitbucket，然后在 Vercel 上导入该项目。Vercel 会自动识别 Flask 应用并进行部署。请确保已在 Vercel 项目设置中配置了所有必要的环境变量。

界面预览
欢迎页: 简洁的入口。
预约日历: 网格化展示，支持周导航。
操作日志: 追踪所有变更。
管理员后台: 强大的管理功能。
技术支持: yudas | 宇达司飞机工业
© 2017-2025 优智通科技. All rights reserved.
""",
        ".gitignore": """
pycache/
*.py[cod]
*$py.class

venv/
.env
instance/
*.sqlite

.vscode/
.idea/
""",
        "requirements.txt": """
Flask
python-dotenv
redis
gunicorn
gevent
""",
        "wsgi.py": """
# wsgi.py
# Gunicorn/Nginx 等生产环境的 WSGI 入口文件

from app import app

# Vercel 平台会自动寻找名为 'app' 的 Flask 实例
# 对于传统部署，WSGI 服务器（如Gunicorn）会使用这个文件
# gunicorn --worker-class gevent --bind 0.0.0.0:5000 wsgi:app

if __name__ == "__main__":
    # 此部分主要用于某些特定的本地测试场景
    # 生产环境通常不会直接运行此文件
    app.run()
""",
        "app.py": """
import os
import json
import sqlite3
import redis
import io
import csv
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, instance_relative_config=True)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# --- 数据库抽象层 ---
# 根据环境变量判断使用 Vercel KV (Redis) 还是 SQLite
IS_VERCEL = os.getenv('VERCEL') == '1'
redis_conn = None

if IS_VERCEL:
    try:
        url = os.getenv("KV_URL")
        if not url:
            raise ValueError("Vercel KV_URL not found in environment variables.")
        redis_conn = redis.from_url(url)
    except Exception as e:
        print(f"Error connecting to Vercel KV (Redis): {e}")
else:
    # 对于本地或传统服务器，使用 instance 文件夹下的 SQLite
    if not os.path.exists(app.instance_path):
        os.makedirs(app.instance_path)
    app.config['DATABASE'] = os.path.join(app.instance_path, 'reservations.sqlite')

# --- SQLite 辅助函数 ---
def get_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()

# --- 数据操作通用函数 (兼容 Redis 和 SQLite) ---

# 系统设置 (特殊日期、时间段)
DEFAULT_TIME_SLOTS = [f"{h:02d}:{m:02d}-{(h if m==20 else h+1) if (h*60+m+40)<22*60 else h}:{ (m+40)%60 if m==20 else (m+40-60) if m==40 else 20 :02d}" for h in range(6, 22) for m in [0, 40, 20] if h*60+m < 22*60-19]
DEFAULT_TIME_SLOTS = ["06:00-06:40", "06:40-07:20", "07:20-08:00", "08:00-08:40", "08:40-09:20", "09:20-10:00", "10:00-10:40", "10:40-11:20", "11:20-12:00", "12:00-12:40", "12:40-13:20", "13:20-14:00", "14:00-14:40", "14:40-15:20", "15:20-16:00", "16:00-16:40", "16:40-17:20", "17:20-18:00", "18:00-18:40", "18:40-19:20", "19:20-20:00", "20:00-20:40", "20:40-21:20", "21:20-22:00"]


def get_setting(key, default_value):
    \"\"\"获取设置项 (如特殊日期列表或时间段列表)\"\"\"
    if redis_conn:
        value = redis_conn.get(f"setting:{key}")
        return json.loads(value) if value else default_value
    else:
        db = get_db()
        row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        db.close()
        return json.loads(row['value']) if row else default_value

def save_setting(key, value):
    \"\"\"保存设置项\"\"\"
    json_value = json.dumps(value)
    if redis_conn:
        redis_conn.set(f"setting:{key}", json_value)
    else:
        db = get_db()
        db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, json_value))
        db.commit()
        db.close()

def get_all_reservations():
    \"\"\"获取所有预约数据\"\"\"
    reservations = {}
    if redis_conn:
        keys = redis_conn.keys('reservation:*')
        if not keys: return {}
        values = redis_conn.mget(keys)
        for key, value in zip(keys, values):
            _, date_str, time_slot = key.decode('utf-8').split(':', 2)
            if date_str not in reservations:
                reservations[date_str] = {}
            reservations[date_str][time_slot] = value.decode('utf-8')
    else:
        db = get_db()
        rows = db.execute('SELECT date, time_slot, user_name FROM reservations').fetchall()
        db.close()
        for row in rows:
            if row['date'] not in reservations:
                reservations[row['date']] = {}
            reservations[row['date']][row['time_slot']] = row['user_name']
    return reservations

def get_reservation(date_str, time_slot):
    \"\"\"获取单个预约\"\"\"
    if redis_conn:
        user = redis_conn.get(f"reservation:{date_str}:{time_slot}")
        return user.decode('utf-8') if user else None
    else:
        db = get_db()
        row = db.execute('SELECT user_name FROM reservations WHERE date = ? AND time_slot = ?', (date_str, time_slot)).fetchone()
        db.close()
        return row['user_name'] if row else None

def set_reservation(date_str, time_slot, user_name):
    \"\"\"创建或更新预约\"\"\"
    if redis_conn:
        redis_conn.set(f"reservation:{date_str}:{time_slot}", user_name)
    else:
        db = get_db()
        db.execute('INSERT OR REPLACE INTO reservations (date, time_slot, user_name) VALUES (?, ?, ?)', (date_str, time_slot, user_name))
        db.commit()
        db.close()

def delete_reservation(date_str, time_slot):
    \"\"\"删除预约\"\"\"
    if redis_conn:
        redis_conn.delete(f"reservation:{date_str}:{time_slot}")
    else:
        db = get_db()
        db.execute('DELETE FROM reservations WHERE date = ? AND time_slot = ?', (date_str, time_slot))
        db.commit()
        db.close()

def log_action(action, date_str, time_slot, old_user, new_user):
    \"\"\"记录操作日志\"\"\"
    log_entry = {
        "action": action,
        "date": date_str,
        "time_slot": time_slot,
        "old_user": old_user,
        "new_user": new_user,
        "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    }
    if redis_conn:
        redis_conn.lpush("logs", json.dumps(log_entry))
    else:
        db = get_db()
        db.execute('INSERT INTO logs (action, date, time_slot, old_user_name, new_user_name, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
                   (action, date_str, time_slot, old_user, new_user, log_entry['timestamp']))
        db.commit()
        db.close()

def get_all_logs(limit=200):
    \"\"\"获取所有日志\"\"\"
    if redis_conn:
        log_entries = redis_conn.lrange("logs", 0, limit - 1)
        return [json.loads(entry) for entry in log_entries]
    else:
        db = get_db()
        rows = db.execute('SELECT id, action, date, time_slot, old_user_name, new_user_name, timestamp FROM logs ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
        db.close()
        return [dict(row) for row in rows]

# --- Flask CLI 命令 (仅限SQLite) ---
@app.cli.command('init-db')
def init_db_command():
    \"\"\"为SQLite创建数据库表\"\"\"
    if IS_VERCEL:
        print("Database initialization is not needed for Vercel KV.")
        return

    # 创建 schema.sql 文件
    schema_content = \"\"\"
    DROP TABLE IF EXISTS reservations;
    DROP TABLE IF EXISTS logs;
    DROP TABLE IF EXISTS settings;

    CREATE TABLE reservations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT NOT NULL,
      time_slot TEXT NOT NULL,
      user_name TEXT NOT NULL,
      UNIQUE(date, time_slot)
    );

    CREATE TABLE logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      action TEXT NOT NULL,
      date TEXT NOT NULL,
      time_slot TEXT NOT NULL,
      old_user_name TEXT,
      new_user_name TEXT,
      timestamp TEXT NOT NULL
    );

    CREATE TABLE settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
    \"\"\"
    with open('schema.sql', 'w', encoding='utf-8') as f:
        f.write(schema_content)

    init_db()
    # 初始化默认设置
    save_setting('time_slots', DEFAULT_TIME_SLOTS)
    save_setting('special_dates', {}) # 初始为空
    os.remove('schema.sql') # 清理
    print('Initialized the database.')


# --- 管理员认证 ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 路由 ---

@app.route('/')
def welcome():
    \"\"\"欢迎入口页面\"\"\"
    return render_template('welcome.html')

@app.route('/schedule')
def schedule():
    \"\"\"主预约日历视图\"\"\"
    start_date_str = request.args.get('start_date')
    today = date.today()

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today
    else:
        start_date = today

    # 将开始日期调整为本周的周一
    start_of_week = start_date - timedelta(days=start_date.weekday())

    # 计算上一周和下一周的开始日期
    prev_week_start = start_of_week - timedelta(days=7)
    next_week_start = start_of_week + timedelta(days=7)

    # 生成本周的日期信息
    week_days = []
    week_day_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    for i in range(7):
        current_day = start_of_week + timedelta(days=i)
        week_days.append({
            "date_obj": current_day,
            "date_str": current_day.strftime('%Y-%m-%d'),
            "display": current_day.strftime('%m月%d日'),
            "weekday": week_day_names[i]
        })

    date_range_str = f"{week_days[0]['display']} ({week_days[0]['weekday']}) - {week_days[-1]['display']} ({week_days[-1]['weekday']})"

    reservations = get_all_reservations()
    time_slots = get_setting('time_slots', DEFAULT_TIME_SLOTS)
    special_dates = get_setting('special_dates', {})

    return render_template('index.html', 
                            week_days=week_days,
                            time_slots=time_slots,
                            reservations=reservations,
                            date_range=date_range_str,
                            prev_week_start=prev_week_start.strftime('%Y-%m-%d'),
                            next_week_start=next_week_start.strftime('%Y-%m-%d'),
                            today_start=today.strftime('%Y-%m-%d'),
                            special_dates=special_dates)


@app.route('/submit_reservation', methods=['POST'])
def submit_reservation():
    \"\"\"处理预约创建、更新和删除\"\"\"
    data = request.json
    date_str = data.get('date')
    time_slot = data.get('time_slot')
    new_user_name = data.get('name', '').strip()

    if not date_str or not time_slot:
        return jsonify({"status": "error", "message": "无效的日期或时间段。"}), 400

    old_user_name = get_reservation(date_str, time_slot)

    if new_user_name:
        # 创建或更新
        set_reservation(date_str, time_slot, new_user_name)
        action = "update" if old_user_name else "create"
        message = f"预约成功！ {time_slot} 已由 {new_user_name} 预约。" if action == "create" else f"预约已更新为 {new_user_name}。"
        log_action(action, date_str, time_slot, old_user_name, new_user_name)
        return jsonify({"status": "success", "message": message, "action": action, "new_user": new_user_name})
    else:
        # 删除
        if old_user_name:
            delete_reservation(date_str, time_slot)
            log_action("delete", date_str, time_slot, old_user_name, "")
            return jsonify({"status": "success", "message": "预约已删除。", "action": "delete", "new_user": ""})
        else:
            # 用户尝试删除一个空的预约，无需操作
            return jsonify({"status": "info", "message": "该时段无预约。", "action": "none"})

@app.route('/logs')
def logs():
    \"\"\"操作日志页面\"\"\"
    all_logs = get_all_logs()
    return render_template('logs.html', logs=all_logs)


@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    \"\"\"管理员登录页面\"\"\"
    admin_password = os.getenv('ADMIN_PASSWORD')
    if not admin_password:
        return "错误：管理员密码未在环境变量中设置。", 500

    if request.method == 'POST':
        password = request.form.get('password')
        if password == admin_password:
            session['admin_logged_in'] = True
            session.permanent = True # 使用永久会话
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin.html', error="密码错误", logged_in=False)

    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))

    return render_template('admin.html', logged_in=False)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    \"\"\"管理员后台主面板\"\"\"
    special_dates = get_setting('special_dates', {})
    sorted_special_dates = sorted(special_dates.items())
    time_slots = get_setting('time_slots', DEFAULT_TIME_SLOTS)
    return render_template('admin.html', 
                             logged_in=True, 
                             special_dates=sorted_special_dates,
                             time_slots=time_slots)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/special_dates', methods=['POST'])
@admin_required
def manage_special_dates():
    \"\"\"管理特殊日期\"\"\"
    form_data = request.form
    special_dates = get_setting('special_dates', {})

    if 'add_date' in form_data:
        date_to_add = form_data.get('date')
        name_to_add = form_data.get('name', '斋日').strip()
        if date_to_add and name_to_add:
            special_dates[date_to_add] = name_to_add

    if 'delete_date' in form_data:
        date_to_delete = form_data.get('delete_date')
        if date_to_delete in special_dates:
            del special_dates[date_to_delete]

    save_setting('special_dates', special_dates)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/time_slots', methods=['POST'])
@admin_required
def manage_time_slots():
    \"\"\"管理时间段\"\"\"
    new_time_slots = request.form.getlist('time_slot')
    # 过滤掉空值
    new_time_slots = [slot.strip() for slot in new_time_slots if slot.strip()]
    if new_time_slots:
        save_setting('time_slots', new_time_slots)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export/csv')
@admin_required
def export_data():
    \"\"\"导出所有预约和日志数据为 CSV\"\"\"
    # 1. 获取数据
    reservations = get_all_reservations()
    logs = get_all_logs(limit=10000) # 导出时获取更多日志

    # 2. 创建内存中的 CSV 文件
    si = io.StringIO()
    cw = csv.writer(si)

    # 写入预约数据
    cw.writerow(['--- Reservations ---'])
    cw.writerow(['Date', 'Time Slot', 'User Name'])
    # 排序以获得一致的输出
    sorted_dates = sorted(reservations.keys())
    for date_str in sorted_dates:
        sorted_slots = sorted(reservations[date_str].keys())
        for slot in sorted_slots:
            cw.writerow([date_str, slot, reservations[date_str][slot]])

    cw.writerow([]) # 空行分隔

    # 写入日志数据
    cw.writerow(['--- Logs ---'])
    cw.writerow(['Timestamp (UTC)', 'Action', 'Date', 'Time Slot', 'Old User', 'New User'])
    for log in logs:
        cw.writerow([
            log.get('timestamp'), log.get('action'), log.get('date'), 
            log.get('time_slot'), log.get('old_user', log.get('old_user_name')), # 兼容两种 key
            log.get('new_user', log.get('new_user_name'))
        ])

    output = si.getvalue()

    # 3. 返回 CSV 文件
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition":
                 f"attachment; filename=youtong_booking_export_{datetime.utcnow().strftime('%Y%m%d')}.csv"})


if __name__ == '__main__':
    app.run(debug=True)
""",
        "templates/base.html": """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes, minimum-scale=1.0, maximum-scale=3.0">
    <meta name="description" content="优智通科技共修室在线预约系统，提供便捷的共修室使用时间段预约、查询和管理功能。">
    <meta name="keywords" content="共修室预约, 优智通科技, 在线预约, 场地预定, Flask">
    <meta name="author" content="优智通科技">
    <title>{% block title %}优智通科技共修室预约系统{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22[http://www.w3.org/2000/svg%22](http://www.w3.org/2000/svg%22) viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📚</text></svg>">
</head>
<body>
    <header class="main-header">
        <nav class="container">
            <a href="{{ url_for('welcome') }}" class="logo">📚 优智通科技</a>
            <div class="nav-links">
                <a href="{{ url_for('schedule') }}">预约首页</a>
                <a href="{{ url_for('logs') }}">操作日志</a>
                <a href="{{ url_for('admin_login') }}">管理员后台</a>
            </div>
        </nav>
    </header>

    <main class="container">
        {% block content %}{% endblock %}
    </main>

    <footer class="main-footer">
        <div class="container">
            <p>技术支持：yudas | 宇达司飞机工业</p>
            <p>&copy; 2017-2025 优智通科技. All rights reserved.</p>
            <p><a href="[https://beian.miit.gov.cn/](https://beian.miit.gov.cn/)" target="_blank">闽ICP备2024052968号-1</a></p>
        </div>
    </footer>

    {% block scripts %}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    {% endblock %}
</body>
</html>
""",
        "templates/welcome.html": """
{% extends "base.html" %}

{% block title %}欢迎 - {{ super() }}{% endblock %}

{% block content %}
<div class="welcome-container">
    <div class="icon-large">📚</div>
    <h1>优智通科技共修室预约系统</h1>
    <p class="welcome-text">
        欢迎使用本系统。在这里，您可以方便快捷地查看共修室的可用时间并进行预约。
    </p>
    <a href="{{ url_for('schedule') }}" class="button-primary">进入预约日历</a>
</div>
{% endblock %}
""",
        "templates/index.html": """
{% extends "base.html" %}

{% block title %}预约日历 - {{ super() }}{% endblock %}

{% block content %}
<div class="schedule-header">
    <h2>共修室预约日历</h2>
    <div class="date-navigation">
        <a href="{{ url_for('schedule', start_date=prev_week_start) }}">&laquo; 上一周</a>
        <a href="{{ url_for('schedule') }}">返回本周</a>
        <a href="{{ url_for('schedule', start_date=next_week_start) }}">下一周 &raquo;</a>
    </div>
    <p class="date-range">{{ date_range }}</p>
</div>

<div class="table-container">
    <table class="schedule-table">
        <thead>
            <tr>
                <th>时间段</th>
                {% for day in week_days %}
                <th class="{% if day.date_str in special_dates %}special-day{% endif %}">
                    {{ day.display }}<br>{{ day.weekday }}
                    {% if day.date_str in special_dates %}
                    <span class="special-day-name">{{ special_dates[day.date_str] }}</span>
                    {% endif %}
                </th>
                {% endfor %}
            </tr>
        </thead>
        <tbody>
            {% for slot in time_slots %}
            <tr>
                <td>{{ slot }}</td>
                {% for day in week_days %}
                <td data-date="{{ day.date_str }}" data-time-slot="{{ slot }}">
                    {{ reservations.get(day.date_str, {}).get(slot, '') }}
                </td>
                {% endfor %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div id="bookingModal" class="modal" style="display: none;">
    <div class="modal-content">
        <span class="close-button">&times;</span>
        <h3>共修室预约</h3>
        <p><strong>日期:</strong> <span id="modalDate"></span></p>
        <p><strong>时间:</strong> <span id="modalTimeSlot"></span></p>
        <p><strong>当前预约人:</strong> <span id="modalCurrentUser">无</span></p>
        <form id="bookingForm">
            <input type="hidden" id="modalDateInput" name="date">
            <input type="hidden" id="modalTimeSlotInput" name="time_slot">
            <div class="form-group">
                <label for="nameInput">您的名字:</label>
                <input type="text" id="nameInput" name="name" placeholder="输入名字以预约或修改" required>
            </div>
            <div class="form-actions">
                <button type="submit" class="button-primary">提交</button>
                <button type="button" id="deleteButton" class="button-danger">删除此预约</button>
            </div>
        </form>
        <div id="modalMessage" class="modal-message"></div>
    </div>
</div>
{% endblock %}
""",
        "templates/logs.html": """
{% extends "base.html" %}

{% block title %}操作日志 - {{ super() }}{% endblock %}

{% block content %}
<h2>操作日志</h2>
<p>这里记录了最近的 200 条预约变更历史。</p>
<div class="table-container">
    <table class="logs-table">
        <thead>
            <tr>
                <th>时间戳 (UTC)</th>
                <th>操作</th>
                <th>日期</th>
                <th>时间段</th>
                <th>原预约人</th>
                <th>新预约人</th>
            </tr>
        </thead>
        <tbody>
            {% for log in logs %}
            <tr class="log-{{ log.action }}">
                <td>{{ log.timestamp }}</td>
                <td>
                    {% if log.action == 'create' %}创建
                    {% elif log.action == 'update' %}更新
                    {% elif log.action == 'delete' %}删除
                    {% else %}{{ log.action }}
                    {% endif %}
                </td>
                <td>{{ log.date }}</td>
                <td>{{ log.time_slot }}</td>
                <td>{{ log.old_user_name or '无' }}</td>
                <td>{{ log.new_user_name or '无' }}</td>
            </tr>
            {% else %}
            <tr>
                <td colspan="6">暂无任何日志记录。</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
""",
        "templates/admin.html": """
{% extends "base.html" %}

{% block title %}管理员后台 - {{ super() }}{% endblock %}

{% block content %}
<h2>管理员后台</h2>

{% if not logged_in %}
    <form action="{{ url_for('admin_login') }}" method="post" class="admin-form">
        <h3>管理员登录</h3>
        {% if error %}
            <p class="error-message">{{ error }}</p>
        {% endif %}
        <div class="form-group">
            <label for="password">密码:</label>
            <input type="password" id="password" name="password" required>
        </div>
        <button type="submit" class="button-primary">登录</button>
    </form>
{% else %}
    <p>欢迎, 管理员! <a href="{{ url_for('admin_logout') }}">退出登录</a></p>
    <div class="admin-panel">
        <div class="admin-section">
            <h3 class="collapsible">特殊日期管理 (斋日等)
                <span class="toggle-icon">-</span>
            </h3>
            <div class="collapsible-content">
                <div class="info-box">
                    <strong>提示:</strong> 添加或删除特殊日期会立即生效，并影响预约日历的显示。
                </div>
                <h4>添加新特殊日期</h4>
                <form action="{{ url_for('manage_special_dates') }}" method="post" class="inline-form">
                    <input type="date" name="date" required>
                    <input type="text" name="name" placeholder="名称 (如: 斋日)" value="斋日" required>
                    <button type="submit" name="add_date" class="button-primary">添加</button>
                </form>

                <h4>现有特殊日期</h4>
                {% if special_dates %}
                <ul class="item-list">
                    {% for date, name in special_dates %}
                    <li>
                        <span>{{ date }} ({{ name }})</span>
                        <form action="{{ url_for('manage_special_dates') }}" method="post" class="delete-form">
                             <input type="hidden" name="delete_date" value="{{ date }}">
                             <button type="submit" class="button-danger">删除</button>
                        </form>
                    </li>
                    {% endfor %}
                </ul>
                {% else %}
                <p>当前没有设置特殊日期。</p>
                {% endif %}
            </div>
        </div>

        <div class="admin-section">
             <h3 class="collapsible">预约时间段管理
                <span class="toggle-icon">-</span>
            </h3>
            <div class="collapsible-content">
                <div class="info-box">
                    <strong>提示:</strong> 修改时间段列表将立即改变预约日历的行结构。请确保格式为 "HH:MM-HH:MM"。
                </div>
                <form action="{{ url_for('manage_time_slots') }}" method="post" id="timeSlotsForm">
                    <div id="timeSlotsContainer">
                        {% for slot in time_slots %}
                        <div class="time-slot-item">
                            <input type="text" name="time_slot" value="{{ slot }}" placeholder="HH:MM-HH:MM" required>
                            <button type="button" class="button-danger remove-slot-btn">删除</button>
                        </div>
                        {% endfor %}
                    </div>
                    <button type="button" id="addSlotBtn" class="button-secondary">添加一个时间段</button>
                    <button type="submit" class="button-primary">保存所有时间段</button>
                </form>
            </div>
        </div>

        <div class="admin-section">
            <h3 class="collapsible">数据管理
                <span class="toggle-icon">-</span>
            </h3>
            <div class="collapsible-content">
                <p>将当前所有的预约数据和操作日志导出为 CSV 文件。</p>
                <a href="{{ url_for('export_data') }}" class="button-primary">导出为 .CSV 文件</a>
            </div>
        </div>
    </div>

{% endif %}
{% endblock %}
""",
        "static/css/style.css": """
/* --- 全局与变量 --- */
:root {
    --primary-color: #007bff;
    --secondary-color: #6c757d;
    --success-color: #28a745;
    --danger-color: #dc3545;
    --warning-color: #ffc107;
    --info-color: #17a2b8;
    --light-color: #f8f9fa;
    --dark-color: #343a40;
    --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    --gradient-blue: linear-gradient(90deg, #007bff 0%, #0056b3 100%);
}

body {
    font-family: var(--font-family);
    margin: 0;
    background-color: #f4f7f6;
    color: var(--dark-color);
    line-height: 1.6;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
}

.container {
    width: 95%;
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 15px;
}

main {
    flex-grow: 1;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

a {
    color: var(--primary-color);
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
}

/* --- 页眉 --- */
.main-header {
    background: var(--gradient-blue);
    color: white;
    padding: 1rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.main-header nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.main-header .logo {
    font-size: 1.5rem;
    font-weight: bold;
    color: white;
}
.main-header .nav-links a {
    color: white;
    margin-left: 20px;
    font-size: 1rem;
    transition: opacity 0.2s;
}
.main-header .nav-links a:hover {
    opacity: 0.8;
    text-decoration: none;
}

/* --- 页脚 --- */
.main-footer {
    background-color: var(--dark-color);
    color: #ccc;
    padding: 1.5rem 0;
    text-align: center;
    font-size: 0.9rem;
}
.main-footer p {
    margin: 0.5rem 0;
}
.main-footer a {
    color: white;
}

/* --- 按钮 --- */
.button-primary, .button-secondary, .button-danger {
    display: inline-block;
    padding: 10px 20px;
    border: none;
    border-radius: 5px;
    color: white;
    font-size: 1rem;
    cursor: pointer;
    text-align: center;
    transition: background-color 0.2s;
}
.button-primary { background-color: var(--primary-color); }
.button-primary:hover { background-color: #0056b3; }
.button-secondary { background-color: var(--secondary-color); }
.button-secondary:hover { background-color: #5a6268; }
.button-danger { background-color: var(--danger-color); }
.button-danger:hover { background-color: #c82333; }


/* --- 欢迎页 --- */
.welcome-container {
    text-align: center;
    padding: 4rem 1rem;
}
.welcome-container .icon-large {
    font-size: 5rem;
    margin-bottom: 1rem;
}
.welcome-container h1 {
    font-size: 2.5rem;
    margin-bottom: 1rem;
}
.welcome-container .welcome-text {
    font-size: 1.2rem;
    color: #555;
    max-width: 600px;
    margin: 0 auto 2rem auto;
}

/* --- 预约日历页 --- */
.schedule-header {
    text-align: center;
    margin-bottom: 2rem;
}
.schedule-header h2 { font-size: 2rem; }
.date-navigation a {
    margin: 0 15px;
}
.date-range {
    font-size: 1.1rem;
    color: var(--secondary-color);
    margin-top: 0.5rem;
}

.table-container {
    overflow-x: auto; /* 关键：在小屏幕上启用水平滚动 */
    -webkit-overflow-scrolling: touch; /* 改善在iOS上的滚动体验 */
}

.schedule-table {
    width: 100%;
    border-collapse: collapse;
    min-width: 900px; /* 确保表格不会被过度压缩 */
}

.schedule-table th, .schedule-table td {
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: center;
    vertical-align: middle;
    font-size: 0.95rem;
    min-width: 120px;
}

.schedule-table th {
    background-color: var(--light-color);
    font-weight: normal;
}

.schedule-table td {
    height: 40px;
    cursor: pointer;
    transition: background-color 0.2s;
    word-break: break-all;
}

.schedule-table td:hover {
    background-color: #e9ecef;
}
.schedule-table td:empty::after {
    content: "+";
    color: #ccc;
    font-size: 1.2rem;
}

.special-day {
    background-color: var(--warning-color) !important;
    color: var(--dark-color);
}
.special-day-name {
    display: block;
    font-size: 0.8rem;
    font-weight: bold;
    margin-top: 4px;
}

/* --- 模态框 --- */
.modal {
    position: fixed;
    z-index: 1000;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
}
.modal-content {
    background-color: white;
    padding: 2rem;
    border-radius: 8px;
    width: 90%;
    max-width: 400px;
    position: relative;
    box-shadow: 0 5px 15px rgba(0,0,0,0.3);
}
.close-button {
    position: absolute;
    top: 10px;
    right: 20px;
    font-size: 2rem;
    font-weight: bold;
    cursor: pointer;
    color: #aaa;
}
.close-button:hover { color: #333; }

.form-group { margin-bottom: 1rem; }
.form-group label { display: block; margin-bottom: 0.5rem; }
.form-group input {
    width: 100%;
    padding: 8px;
    box-sizing: border-box;
    border: 1px solid #ccc;
    border-radius: 4px;
}
.form-actions { display: flex; justify-content: space-between; }
.modal-message { margin-top: 1rem; text-align: center; }

/* --- 日志页 --- */
.logs-table {
    width: 100%;
    border-collapse: collapse;
}
.logs-table th, .logs-table td {
    border: 1px solid #ddd;
    padding: 10px;
    text-align: left;
}
.logs-table th { background-color: var(--light-color); }
.log-create { background-color: #eaf7ed; }
.log-update { background-color: #fff8e1; }
.log-delete { background-color: #fbe9e7; }

/* --- 管理员页 --- */
.admin-form, .admin-panel {
    max-width: 800px;
    margin: 0 auto;
    background: white;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}
.admin-section {
    border: 1px solid #e0e0e0;
    border-radius: 5px;
    margin-bottom: 1.5rem;
}
.collapsible {
    background-color: var(--light-color);
    color: var(--dark-color);
    cursor: pointer;
    padding: 15px;
    width: 100%;
    border: none;
    text-align: left;
    outline: none;
    font-size: 1.1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.collapsible:hover { background-color: #e2e6ea; }
.collapsible-content {
    padding: 15px;
    display: block; /* Default to open */
    overflow: hidden;
}
.info-box {
    background-color: #e7f3fe;
    border-left: 4px solid var(--primary-color);
    padding: 10px 15px;
    margin-bottom: 1rem;
    font-size: 0.9rem;
}
.inline-form, .delete-form {
    display: inline-flex;
    gap: 10px;
    align-items: center;
}
.item-list { list-style: none; padding-left: 0; }
.item-list li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px;
    border-bottom: 1px solid #eee;
}
.time-slot-item {
    display: flex;
    gap: 10px;
    margin-bottom: 10px;
}
.time-slot-item input { flex-grow: 1; }

/* --- 响应式设计 --- */
@media (max-width: 768px) {
    .main-header nav {
        flex-direction: column;
        gap: 10px;
    }
    .main-header .nav-links {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 15px;
    }
    .main-header .nav-links a { margin-left: 0; }

    .schedule-table th, .schedule-table td {
        padding: 6px 8px;
        font-size: 0.85rem;
        min-width: 100px;
    }

    h1 { font-size: 2rem; }
    h2 { font-size: 1.6rem; }
}
""",
        "static/js/main.js": """
document.addEventListener('DOMContentLoaded', function() {

    // --- 预约日历交互 ---
    const bookingModal = document.getElementById('bookingModal');
    if (bookingModal) {
        const scheduleTable = document.querySelector('.schedule-table');
        const closeModalButton = document.querySelector('.close-button');
        const bookingForm = document.getElementById('bookingForm');
        const deleteButton = document.getElementById('deleteButton');
        let activeCell = null;

        // 打开模态框
        const openModal = (cell) => {
            activeCell = cell;
            const date = cell.dataset.date;
            const timeSlot = cell.dataset.timeSlot;
            const currentUser = cell.textContent.trim();

            document.getElementById('modalDate').textContent = date;
            document.getElementById('modalTimeSlot').textContent = timeSlot;
            document.getElementById('modalCurrentUser').textContent = currentUser || '无';
            document.getElementById('nameInput').value = currentUser;
            document.getElementById('modalDateInput').value = date;
            document.getElementById('modalTimeSlotInput').value = timeSlot;

            // 如果没有预约人，禁用删除按钮
            deleteButton.disabled = !currentUser;
            document.getElementById('modalMessage').textContent = '';

            bookingModal.style.display = 'flex';
            document.getElementById('nameInput').focus();
        };

        // 关闭模态框
        const closeModal = () => {
            bookingModal.style.display = 'none';
            activeCell = null;
        };

        // 表格单元格点击事件 (事件委托)
        if (scheduleTable) {
            scheduleTable.addEventListener('click', (event) => {
                if (event.target.tagName === 'TD' && event.target.dataset.date) {
                    openModal(event.target);
                }
            });
        }

        // 关闭按钮
        if (closeModalButton) {
            closeModalButton.addEventListener('click', closeModal);
        }

        // 点击模态框外部关闭
        window.addEventListener('click', (event) => {
            if (event.target === bookingModal) {
                closeModal();
            }
        });

        // 表单提交 (创建/更新)
        if (bookingForm) {
            bookingForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                await submitReservation();
            });
        }

        // 删除按钮
        if (deleteButton) {
            deleteButton.addEventListener('click', async () => {
                // 清空输入框并提交，等同于删除
                document.getElementById('nameInput').value = '';
                await submitReservation();
            });
        }

        // 提交逻辑
        const submitReservation = async () => {
            const formData = new FormData(bookingForm);
            const data = {
                date: formData.get('date'),
                time_slot: formData.get('time_slot'),
                name: formData.get('name').trim()
            };

            try {
                const response = await fetch('/submit_reservation', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                const modalMessage = document.getElementById('modalMessage');
                modalMessage.textContent = result.message;
                modalMessage.className = `modal-message ${result.status}`;

                if (result.status === 'success') {
                    activeCell.textContent = result.new_user;
                    setTimeout(closeModal, 1000); // 成功后延迟1秒关闭
                } else if (result.status === 'info') {
                     setTimeout(closeModal, 1000);
                }

            } catch (error) {
                console.error('Error submitting reservation:', error);
                document.getElementById('modalMessage').textContent = '发生网络错误，请稍后重试。';
            }
        };
    }

    // --- 管理员后台交互 ---

    // 折叠面板
    const collapsibles = document.querySelectorAll('.collapsible');
    collapsibles.forEach(button => {
        button.addEventListener('click', function() {
            this.classList.toggle('active');
            const content = this.nextElementSibling;
            const icon = this.querySelector('.toggle-icon');
            if (content.style.display === 'block' || content.style.display === '') {
                content.style.display = 'none';
                icon.textContent = '+';
            } else {
                content.style.display = 'block';
                icon.textContent = '-';
            }
        });
    });

    // 删除特殊日期二次确认
    const deleteForms = document.querySelectorAll('.delete-form');
    deleteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!confirm('您确定要删除此项吗？此操作不可撤销。')) {
                event.preventDefault();
            }
        });
    });

    // 动态添加/删除时间段
    const timeSlotsContainer = document.getElementById('timeSlotsContainer');
    if (timeSlotsContainer) {
        document.getElementById('addSlotBtn').addEventListener('click', () => {
            const newItem = document.createElement('div');
            newItem.className = 'time-slot-item';
            newItem.innerHTML = `
                <input type="text" name="time_slot" placeholder="HH:MM-HH:MM" required>
                <button type="button" class="button-danger remove-slot-btn">删除</button>
            `;
            timeSlotsContainer.appendChild(newItem);
        });

        timeSlotsContainer.addEventListener('click', (event) => {
            if (event.target.classList.contains('remove-slot-btn')) {
                event.target.parentElement.remove();
            }
        });
    }

});
"""
    }

    # 创建项目根目录
    try:
        os.makedirs(base_dir, exist_ok=True)
        print(f"创建目录: {base_dir}")
    except Exception as e:
        print(f"无法创建项目根目录 {base_dir}: {e}")
        return

    # 定义目录结构
    dirs = [
        "static/css",
        "static/js",
        "templates"
    ]

    # 创建所有子目录
    for d in dirs:
        path = os.path.join(base_dir, d)
        try:
            os.makedirs(path, exist_ok=True)
            print(f"创建目录: {path}")
        except Exception as e:
            print(f"无法创建子目录 {path}: {e}")
            return

    # 写入文件内容
    for file_path, content in file_contents.items():
        full_path = os.path.join(base_dir, file_path)
        try:
            # 使用 'w' 模式打开文件，如果文件不存在则创建，如果存在则覆盖
            # 指定 encoding='utf-8' 来正确处理中文字符
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content.strip())  # .strip() 移除多余的空行
            print(f"写入文件: {full_path}")
        except Exception as e:
            print(f"无法写入文件 {full_path}: {e}")
            return

    print("\n项目结构和文件已成功创建！")
    print(f"请进入项目目录: cd {project_name}")
    print("然后安装依赖: pip install -r requirements.txt")
    print("创建 .env 文件并设置 ADMIN_PASSWORD")
    print("运行 flask init-db 初始化数据库 (仅限SQLite)")
    print("最后运行 flask run 启动应用。")


if __name__ == "__main__":
    create_project_structure_and_files()