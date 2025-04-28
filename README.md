# Competition Notification Slack Bot

Kaggle과 Dacon의 대회 정보를 수집하여 Slack으로 알림을 보내는 봇입니다.

## 기능

- Kaggle과 Dacon의 새로운 대회 정보 수집
- 1분 간격으로 대회 정보 업데이트
- 새로운 대회 발견 시 Slack으로 알림 전송
- 대회 정보는 JSON 파일로 저장 및 관리

## 설치 방법

1. 프로젝트 클론:
```bash
git clone [repository_url]
cd contest-slack-bot
```

2. 필요한 패키지 설치:
```bash
pip install -r requirements.txt
```

3. Kaggle API 설정:
   - Kaggle 웹사이트에서 API 토큰 다운로드
   - `.kaggle/kaggle.json` 파일에 저장 (이미 포함되어 있음)
   - 파일 권한 설정:
     ```bash
     chmod 700 .kaggle
     chmod 600 .kaggle/kaggle.json
     ```

4. Slack 설정:
   - Slack 워크스페이스에서 봇 생성
   - `.env` 파일에서 다음 설정 수정:
     ```
     SLACK_TOKEN=your_slack_bot_token
     SLACK_CHANNEL=your_slack_channel
     ```

## 실행 방법

```bash
python3 bot/contest_noti_slackbot.py
```

봇은 다음과 같은 일정으로 실행됩니다:
- 1분 간격으로 자동으로 실행
- 프로그램 시작 시 즉시 한 번 실행
- 24시간 연속 모니터링

## 파일 구조

```
contest-slack-bot/
├── bot/
│   └── contest_noti_slackbot.py    # 메인 봇 스크립트
├── .kaggle/
│   └── kaggle.json                 # Kaggle API 인증 파일
├── data/
│   ├── competition_data.json       # 대회 정보 저장 파일
│   └── competition_bot.log         # 로그 파일
├── requirements.txt                # 필요한 패키지 목록
├── .env                           # 환경 변수 설정
├── .gitignore                     # Git 제외 파일 목록
└── README.md                      # 프로젝트 설명
```

## 주의사항

- `.env` 파일과 `.kaggle/kaggle.json` 파일은 절대 GitHub에 업로드하지 마세요.
- 봇을 실행하기 전에 다음 사항을 확인하세요:
  1. Kaggle API 인증 파일이 올바르게 설정되었는지
  2. Slack 봇 토큰이 `.env` 파일에 올바르게 설정되었는지
  3. 필요한 모든 패키지가 설치되었는지

## 로그 확인

로그 파일은 `data/competition_bot.log`에 저장됩니다. 다음 명령어로 실시간 로그를 확인할 수 있습니다:

```bash
tail -f data/competition_bot.log
```
