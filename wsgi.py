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