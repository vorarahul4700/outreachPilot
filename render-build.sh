#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

STORAGE_DIR=/opt/render/project/.render

if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "==> Downloading and extracting Google Chrome..."
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x google-chrome-stable_current_amd64.deb $STORAGE_DIR/chrome
  rm google-chrome-stable_current_amd64.deb
  cd -
else
  echo "==> Using Google Chrome from Render build cache"
fi

export PATH="${PATH}:/opt/render/project/.render/chrome/opt/google/chrome"

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Installing matching ChromeDriver..."
sbase install chromedriver

echo "==> Build completed successfully!"
