# Web Multi Chat Demo

FastAPI, WebSocket, SQLite3로 만든 멀티 채팅방 예제입니다.

## 기능

- 채팅방 생성
- 비밀번호가 있는 비공개 방 생성
- 채팅방 목록 조회
- 채팅방 입장
- 방별 닉네임 중복 방지
- 채팅방 삭제
- 방별 실시간 WebSocket 채팅
- SQLite3 기반 방/메시지 저장

## 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 으로 접속하면 됩니다.

## 저장소 구조

```text
web-multi-chat-demo/
  app/
    main.py
    db.py
    room_manager.py
    templates/
      index.html
    static/
      app.css
      app.js
```
