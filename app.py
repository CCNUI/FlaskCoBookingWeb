import os
import json
import sqlite3
import redis
import io
import csv
import time
import uuid  # 导入 uuid 模块
import requests  # 导入 requests 模块
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response, flash, abort
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, instance_relative_config=True)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)

# --- 功能开关 & 过期提醒设置 ---
# 从 .env 读取配置, 如果未设置则默认为 'false'
ENABLE_EXPORT_CSV = os.getenv('ENABLE_EXPORT_CSV', 'false').lower() == 'true'
ENABLE_ACCESS_LOG = os.getenv('ENABLE_ACCESS_LOG', 'false').lower() == 'true'
EXPIRATION_DATE_STR = os.getenv('EXPIRATION_DATE')
EXPIRATION_DATE = None

print("--- 优智通科技共修室预约系统 ---")
print(f"[*] 导出CSV功能: {'已启用' if ENABLE_EXPORT_CSV else '已禁用'}")
print(f"[*] 访问日志功能: {'已启用' if ENABLE_ACCESS_LOG else '已禁用'}")

if EXPIRATION_DATE_STR:
    try:
        EXPIRATION_DATE = datetime.strptime(EXPIRATION_DATE_STR, '%Y-%m-%d').date()
        print(f"[*] 服务器过期提醒: 已启用 (过期日期: {EXPIRATION_DATE_STR})")
    except ValueError:
        print(f"[错误] EXPIRATION_DATE 格式无效: '{EXPIRATION_DATE_STR}'. 正确格式为 YYYY-MM-DD。提醒功能已禁用。")
else:
    print("[*] 服务器过期提醒: 已禁用 (未设置 EXPIRATION_DATE)")
print("---------------------------------")

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


# --- 上下文处理器, 向所有模板注入变量 ---
@app.context_processor
def inject_global_vars():
    feature_flags = {
        'export_csv': ENABLE_EXPORT_CSV,
        'access_log': ENABLE_ACCESS_LOG
    }

    # 检查服务器是否即将过期
    if EXPIRATION_DATE:
        today = date.today()
        # 提前14天开始提醒
        reminder_start_date = EXPIRATION_DATE - timedelta(days=14)
        if reminder_start_date <= today <= EXPIRATION_DATE:
            days_left = (EXPIRATION_DATE - today).days
            if days_left > 0:
                message = f"重要提醒：服务器将于 {EXPIRATION_DATE.strftime('%Y-%m-%d')} ({days_left}天后) 过期，请及时续费！"
            else:
                message = f"重要提醒：服务器已于 {EXPIRATION_DATE.strftime('%Y-%m-%d')} 过期，请提醒站长 @榕缘 进行续费~"
            flash(message, 'danger')

    return dict(feature_flags=feature_flags)


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
DEFAULT_TIME_SLOTS = ["06:00-06:40", "06:40-07:20", "07:20-08:00", "08:00-08:40", "08:40-09:20", "09:20-10:00",
                      "10:00-10:40", "10:40-11:20", "11:20-12:00", "12:00-12:40", "12:40-13:20", "13:20-14:00",
                      "14:00-14:40", "14:40-15:20", "15:20-16:00", "16:00-16:40", "16:40-17:20", "17:20-18:00",
                      "18:00-18:40", "18:40-19:20", "19:20-20:00", "20:00-20:40", "20:40-21:20", "21:20-22:00"]


def get_setting(key, default_value):
    """获取设置项 (如特殊日期列表或时间段列表)"""
    if redis_conn:
        value = redis_conn.get(f"setting:{key}")
        return json.loads(value) if value else default_value
    else:
        db = get_db()
        row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        db.close()
        return json.loads(row['value']) if row else default_value


def save_setting(key, value):
    """保存设置项"""
    json_value = json.dumps(value)
    if redis_conn:
        redis_conn.set(f"setting:{key}", json_value)
    else:
        db = get_db()
        db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, json_value))
        db.commit()
        db.close()


def get_all_reservations():
    """获取所有预约数据"""
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
    """获取单个预约"""
    if redis_conn:
        user = redis_conn.get(f"reservation:{date_str}:{time_slot}")
        return user.decode('utf-8') if user else None
    else:
        db = get_db()
        row = db.execute('SELECT user_name FROM reservations WHERE date = ? AND time_slot = ?',
                         (date_str, time_slot)).fetchone()
        db.close()
        return row['user_name'] if row else None


def set_reservation(date_str, time_slot, user_name):
    """创建或更新预约"""
    if redis_conn:
        redis_conn.set(f"reservation:{date_str}:{time_slot}", user_name)
    else:
        db = get_db()
        db.execute('INSERT OR REPLACE INTO reservations (date, time_slot, user_name) VALUES (?, ?, ?)',
                   (date_str, time_slot, user_name))
        db.commit()
        db.close()


def delete_reservation(date_str, time_slot):
    """删除预约"""
    if redis_conn:
        redis_conn.delete(f"reservation:{date_str}:{time_slot}")
    else:
        db = get_db()
        db.execute('DELETE FROM reservations WHERE date = ? AND time_slot = ?', (date_str, time_slot))
        db.commit()
        db.close()


def log_action(action, date_str, time_slot, old_user, new_user):
    """记录操作日志"""
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
        db.execute(
            'INSERT INTO logs (action, date, time_slot, old_user_name, new_user_name, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
            (action, date_str, time_slot, old_user, new_user, log_entry['timestamp']))
        db.commit()
        db.close()


def get_all_logs(limit=200):
    """获取所有日志"""
    if redis_conn:
        log_entries = redis_conn.lrange("logs", 0, limit - 1)
        return [json.loads(entry) for entry in log_entries]
    else:
        db = get_db()
        rows = db.execute(
            'SELECT id, action, date, time_slot, old_user_name, new_user_name, timestamp FROM logs ORDER BY timestamp DESC LIMIT ?',
            (limit,)).fetchall()
        db.close()
        return [dict(row) for row in rows]


# --- Flask CLI 命令 (仅限SQLite) ---
@app.cli.command('init-db')
def init_db_command():
    """为SQLite创建数据库表"""
    if IS_VERCEL:
        print("Database initialization is not needed for Vercel KV.")
        return

    # 创建 schema.sql 文件
    schema_content = """
                     DROP TABLE IF EXISTS reservations;
                     DROP TABLE IF EXISTS logs;
                     DROP TABLE IF EXISTS settings;

                     CREATE TABLE reservations \
                     ( \
                         id        INTEGER PRIMARY KEY AUTOINCREMENT, \
                         date      TEXT NOT NULL, \
                         time_slot TEXT NOT NULL, \
                         user_name TEXT NOT NULL, \
                         UNIQUE (date, time_slot)
                     );

                     CREATE TABLE logs \
                     ( \
                         id            INTEGER PRIMARY KEY AUTOINCREMENT, \
                         action        TEXT NOT NULL, \
                         date          TEXT NOT NULL, \
                         time_slot     TEXT NOT NULL, \
                         old_user_name TEXT, \
                         new_user_name TEXT, \
                         timestamp     TEXT NOT NULL
                     );

                     CREATE TABLE settings \
                     ( \
                         key   TEXT PRIMARY KEY, \
                         value TEXT NOT NULL
                     ); \
                     """
    with open('schema.sql', 'w', encoding='utf-8') as f:
        f.write(schema_content)

    init_db()
    # 初始化默认设置
    save_setting('time_slots', DEFAULT_TIME_SLOTS)
    save_setting('special_dates', {})  # 初始为空
    save_setting('notices', [])  # 初始为空
    os.remove('schema.sql')  # 清理
    print('Initialized the database.')


# --- 新增：IP地址和会话管理辅助函数 ---
def get_ip_info(ip_address):
    """根据IP地址获取地理位置信息"""
    if not ip_address or ip_address == '127.0.0.1':
        return {"country": "本地", "regionName": "局域网", "city": "开发环境"}
    try:
        # 使用免费的ip-api.com服务
        response = requests.get(
            f"http://ip-api.com/json/{ip_address}?lang=zh-CN&fields=status,message,country,regionName,city")
        data = response.json()
        if data.get('status') == 'success':
            return data
    except requests.RequestException as e:
        print(f"获取IP信息时出错: {e}")
    return {"country": "未知", "regionName": "未知", "city": "未知"}


def get_active_admins():
    """获取所有活跃的管理员会话列表"""
    if not redis_conn:
        return [], 0

    active_sessions = []
    active_ips = set()

    # 扫描所有活跃的会话key
    session_keys = redis_conn.keys('admin_session:*')
    if not session_keys:
        return [], 0

    session_data_list = redis_conn.mget(session_keys)

    for data in session_data_list:
        if data:
            session_info = json.loads(data)
            active_sessions.append(session_info)
            active_ips.add(session_info.get('ip'))

    return active_sessions, len(active_ips)


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
    """欢迎入口页面"""
    return render_template('welcome.html')


@app.route('/schedule')
def schedule():
    """主预约日历视图"""
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
    notices = get_setting('notices', [])

    return render_template('index.html',
                           week_days=week_days,
                           time_slots=time_slots,
                           reservations=reservations,
                           date_range=date_range_str,
                           prev_week_start=prev_week_start.strftime('%Y-%m-%d'),
                           next_week_start=next_week_start.strftime('%Y-%m-%d'),
                           today_start=today.strftime('%Y-%m-%d'),
                           special_dates=special_dates,
                           notices=notices)


@app.route('/submit_reservation', methods=['POST'])
def submit_reservation():
    """处理预约创建、更新和删除"""
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
@admin_required
def logs():
    """操作日志页面"""
    if not ENABLE_ACCESS_LOG:
        abort(404)
    all_logs = get_all_logs()
    return render_template('logs.html', logs=all_logs)


@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    """管理员登录页面 - 实现多管理员会话管理"""
    admin_password = os.getenv('ADMIN_PASSWORD')
    if not admin_password:
        flash("错误：管理员密码未在环境变量中设置。", "danger")
        return render_template('admin.html', logged_in=False)

    if request.method == 'POST':
        password = request.form.get('password')
        if password == admin_password:
            session.permanent = True  # 使 session 永久（受 PERMANENT_SESSION_LIFETIME 控制）
            session['admin_logged_in'] = True

            # 为 Redis 会话生成一个唯一ID
            if 'session_id' not in session:
                session['session_id'] = str(uuid.uuid4())

            # 仅在 Redis 环境下执行高级会话管理
            if redis_conn:
                ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
                ip_info = get_ip_info(ip_address)
                region = f"{ip_info.get('country', '')} {ip_info.get('regionName', '')} {ip_info.get('city', '')}".strip()

                session_details = {
                    "ip": ip_address,
                    "region": region,
                    "login_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                }
                # 存储当前会话信息到 Redis，有效期60分钟
                redis_conn.setex(f"admin_session:{session['session_id']}", 3600, json.dumps(session_details))

            return redirect(url_for('admin_dashboard'))
        else:
            flash("密码错误", "error")
            return render_template('admin.html', error="密码错误", logged_in=False)

    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))

    return render_template('admin.html', logged_in=False)


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """管理员后台主面板 - 显示活跃管理员信息"""
    active_sessions, unique_admin_count = get_active_admins()

    # 将活跃管理员信息传递给模板
    flash({"count": unique_admin_count, "sessions": active_sessions}, "admin_info")

    special_dates = get_setting('special_dates', {})
    sorted_special_dates = sorted(special_dates.items())
    time_slots = get_setting('time_slots', DEFAULT_TIME_SLOTS)
    notices = get_setting('notices', [])
    return render_template('admin.html',
                           logged_in=True,
                           special_dates=sorted_special_dates,
                           time_slots=time_slots,
                           notices=notices)


@app.route('/admin/logout')
def admin_logout():
    # 仅在 Redis 环境下，清理会话信息
    if redis_conn and 'session_id' in session:
        redis_conn.delete(f"admin_session:{session['session_id']}")

    session.clear()  # 清除所有 session 数据
    flash("您已成功退出登录。", "info")
    return redirect(url_for('admin_login'))


@app.route('/admin/special_dates', methods=['POST'])
@admin_required
def manage_special_dates():
    """管理特殊日期"""
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
    """管理时间段"""
    new_time_slots = request.form.getlist('time_slot')
    # 过滤掉空值
    new_time_slots = [slot.strip() for slot in new_time_slots if slot.strip()]
    if new_time_slots:
        save_setting('time_slots', new_time_slots)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/notices', methods=['POST'])
@admin_required
def manage_notices():
    """管理公告 (添加/删除)"""
    form_data = request.form
    notices = get_setting('notices', [])

    if 'add_notice' in form_data:
        text = form_data.get('text', '').strip()
        color = form_data.get('color', '#fff8e1').strip()
        if text:
            notice_id = int(time.time() * 1000)
            notices.append({"id": notice_id, "text": text, "color": color})

    if 'delete_notice' in form_data:
        notice_id_to_delete = form_data.get('delete_notice_id')
        if notice_id_to_delete:
            notices = [n for n in notices if str(n.get('id')) != notice_id_to_delete]

    save_setting('notices', notices)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/edit_notice/<int:notice_id>', methods=['GET', 'POST'])
@admin_required
def edit_notice(notice_id):
    """编辑指定的公告"""
    notices = get_setting('notices', [])
    notice_to_edit = None
    for n in notices:
        if n.get('id') == notice_id:
            notice_to_edit = n
            break

    if not notice_to_edit:
        abort(404)

    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        color = request.form.get('color', '#fff8e1').strip()
        if text:
            notice_to_edit['text'] = text
            notice_to_edit['color'] = color
            save_setting('notices', notices)
            flash('公告已成功更新。', 'info')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('公告内容不能为空。', 'error')

    return render_template('edit_notice.html', notice=notice_to_edit, logged_in=True)


@app.route('/admin/export/csv')
@admin_required
def export_data():
    """导出所有预约和日志数据为 CSV"""
    if not ENABLE_EXPORT_CSV:
        abort(404)

    # 1. 获取数据
    reservations = get_all_reservations()
    logs = get_all_logs(limit=10000)  # 导出时获取更多日志

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

    cw.writerow([])  # 空行分隔

    # 写入日志数据
    cw.writerow(['--- Logs ---'])
    cw.writerow(['Timestamp (UTC)', 'Action', 'Date', 'Time Slot', 'Old User', 'New User'])
    for log in logs:
        cw.writerow([
            log.get('timestamp'), log.get('action'), log.get('date'),
            log.get('time_slot'), log.get('old_user', log.get('old_user_name')),  # 兼容两种 key
            log.get('new_user', log.get('new_user_name'))
        ])

    output = si.getvalue()

    # 3. 返回 CSV 文件
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition":
                     f"attachment; filename=youtong_booking_export_{datetime.utcnow().strftime('%Y%m%d')}.csv"})


# --- 错误处理 ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404, error_message='您访问的页面不存在'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_code=500, error_message='服务器发生内部错误'), 500


if __name__ == '__main__':
    app.run(debug=True)