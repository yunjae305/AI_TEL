#!/usr/bin/env bash
# AIField 파수인 봇 — Ubuntu 서버 초기 세팅
#
# 사용법 (서버에서):
#   git clone https://github.com/yunjae305/AI_TEL.git ~/aifield
#   cd ~/aifield && bash deploy/setup.sh
#
# 이 스크립트는 .env를 만들지 않는다. 토큰이 들어가는 파일이라 직접 작성해야 한다.
# 아무것도 지우거나 덮어쓰지 않는다.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "== 1. 시간대를 KST로 =="
sudo timedatectl set-timezone Asia/Seoul
date

echo
echo "== 2. 패키지 설치 =="
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip

echo
echo "== 3. 가상환경 + 의존성 =="
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt

echo
echo "== 4. .env 확인 =="
if [ -f .env ]; then
    chmod 600 .env
    echo ".env 있음 (권한 600으로 조정)"
else
    cp .env.example .env
    chmod 600 .env
    echo ".env를 .env.example에서 만들었다. 값을 채워야 봇이 뜬다:"
    echo "    nano $APP_DIR/.env"
fi

echo
echo "== 5. systemd 등록 =="
# WorkingDirectory/ExecStart 경로를 실제 설치 경로와 사용자에 맞춰 치환
sudo sed -e "s|/home/ubuntu/aifield|$APP_DIR|g" \
         -e "s|^User=ubuntu$|User=$USER|" \
         deploy/aifield.service | sudo tee /etc/systemd/system/aifield.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable aifield

echo
echo "== 완료 =="
echo "다음 순서로 진행:"
echo "  1) .env 채우기            : nano $APP_DIR/.env"
echo "  2) 더미 데이터로 테스트   : ./venv/bin/python main.py"
echo "  3) 실운영 시작            : sudo systemctl start aifield"
echo "  4) 로그 보기              : journalctl -u aifield -f"
