#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# ================== CONFIGURATION ==================
# IMPORTANT: Fill in these variables with your actual paths and credentials.

# 1. Full path to your Flask project directory (the one containing the 'instance' folder)
PROJECT_PATH="/path/to/your/FlaskCoBookingWeb-not_finished_But_succeed_run"

# 2. Full path to the local clone of your PRIVATE backup repository
BACKUP_REPO_PATH="/home/your_user/my-booking-backup"

# 3. Your GitLab Personal Access Token
GITLAB_TOKEN="g****Xsz" # Replace with your full, unredacted token

# 4. Your GitLab username
GITLAB_USERNAME="your_gitlab_username"

# 5. The name of your private backup project on GitLab
GITLAB_PROJECT_NAME="my-booking-backup"

# ================== DO NOT EDIT BELOW THIS LINE ==================

# Define source database file and the name for the backup file
DB_SOURCE_FILE="$PROJECT_PATH/instance/reservations.sqlite"
BACKUP_FILENAME="reservations.sqlite" # Using a consistent filename to track changes
COMMIT_MESSAGE="Automated backup: $(date +'%Y-%m-%d %H:%M:%S')"

# --- SCRIPT LOGIC ---

echo "Starting database backup process..."

# 1. Navigate to the backup repository directory
cd "$BACKUP_REPO_PATH"

# 2. Copy the latest database file into the backup repository
echo "Copying database file from $DB_SOURCE_FILE..."
cp -f "$DB_SOURCE_FILE" "$BACKUP_REPO_PATH/$BACKUP_FILENAME"

# 3. Perform Git operations
echo "Performing Git operations..."

# Check if there are any changes to the database file
if [[ `git status --porcelain` ]]; then
    echo "Database has changed. Committing and pushing to GitLab..."

    # Configure Git user for this commit
    git config user.name "Automated Backup"
    git config user.email "backup@your-server.com"

    # Add the new backup file, commit, and push
    git add "$BACKUP_FILENAME"
    git commit -m "$COMMIT_MESSAGE"

    # Push to the remote repository using the token for authentication
    git push "https://oauth2:$GITLAB_TOKEN@gitlab.com/$GITLAB_USERNAME/$GITLAB_PROJECT_NAME.git"

    echo "Backup successfully pushed to GitLab."
else
    echo "No changes detected in the database. Skipping backup."
fi

echo "Backup script finished."