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
source venv/bin/activate  # on Windows use `venv\Scripts\activate`
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