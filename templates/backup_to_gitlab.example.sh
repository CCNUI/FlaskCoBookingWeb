#!/bin/bash
set -e # 如果任何命令执行失败，立即退出脚本

# ================== 数据库备份配置 ==================
# 1. 您的 Flask 项目的完整路径
PROJECT_PATH="/home/ecs-user/FlaskCoBookingWeb"

# 2. 【数据库备份专用】的本地克隆仓库的完整路径
BACKUP_REPO_PATH="/home/ecs-user/databasebackup_flaskcobookingweb"

# 3. 您在 GitLab 上创建的【数据库备份专用】的项目名称
GITLAB_PROJECT_NAME="databasebackup_flaskcobookingweb" # 注意：这是存放数据库的仓库名

# 建立databasebackup_flaskcobookingweb仓库并执行：
#git init
#git remote add origin "https://oauth2:[你的令牌]@gitlab.eduxiji.net/ccnui/databasebackup_flaskcobookingweb.git"
#git add -A .
#git commit -m "first commit"
#git branch -m master main
#git branch --set-upstream-to=origin/main main

# ================== 请勿修改以下内容 ==================
DB_SOURCE_FILE="$PROJECT_PATH/instance/reservations.sqlite"
BACKUP_FILENAME="reservations.sqlite"
COMMIT_MESSAGE="自动化数据库备份: $(date +'%Y-%m-%d %H:%M:%S')"

echo "开始执行数据库备份..."
cd "$BACKUP_REPO_PATH"
echo "正在从 $DB_SOURCE_FILE 复制数据库文件..."
cp -f "$DB_SOURCE_FILE" "$BACKUP_REPO_PATH/$BACKUP_FILENAME"
echo "正在执行 Git 操作..."
if [[ `git status --porcelain` ]]; then
    echo "检测到数据库变更，正在提交并推送到 GitLab..."
    git config user.name "Automated Backup"
    git config user.email "backup@your-server.com"
    git add "$BACKUP_FILENAME"
    git commit -m "$COMMIT_MESSAGE"
    git push
    echo "数据库备份已成功推送到 GitLab。"
else
    echo "数据库无变化，本次无需备份。"
fi
echo "数据库备份脚本执行完毕。"