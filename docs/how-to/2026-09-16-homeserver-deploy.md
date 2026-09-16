# 홈서버에 배포하기

앱을 홈서버의 도커 컨테이너로 띄우는 절차다. 설계 근거는
`docs/superpowers/specs/2026-09-16-container-deploy-design.md` 에 있다.

## 준비물

- 홈서버에 Docker Engine 과 Compose v2
- 데스크톱에 이 저장소와 `uv` (자격증명을 만들 때 쓴다)
- NotebookLM 에 접근 가능한 구글 계정

## 1. 저장소와 데이터 디렉터리

홈서버에서.

```bash
git clone <저장소 URL> notebooklm-st
cd notebooklm-st
printf 'PUID=%s\nPGID=%s\n' "$(id -u)" "$(id -g)" > .env
mkdir -p data
sudo chown "$(id -u):$(id -g)" data
```

`.env` 는 컨테이너가 어느 사용자로 돌지 정한다. compose 가 자동으로
읽으므로 **이후 모든 명령에 접두사를 붙이지 않아도 된다.** 이 파일은
`.gitignore` 와 `.dockerignore` 에 이미 들어 있어 저장소나 이미지로
새지 않는다.

`chown` 을 빼먹으면 컨테이너가 `/data` 에 쓰지 못해 기동이 실패한다.

## 2. 띄우기

```bash
docker compose up -d --build
```

상태 확인.

```bash
docker compose ps        # STATUS 가 healthy 가 될 때까지 기다린다
docker compose logs -f   # 기동 로그
```

접속 주소는 **http://<홈서버IP>:9004** 다. 컨테이너 안에서는 8611 에서
돌고 `docker-compose.yml` 이 호스트 9004 에 붙인다.

## 3. 자격증명 넣기

앱은 브라우저를 띄우지 않는다. 최초 로그인은 사람이 데스크톱에서 한다.

데스크톱에서.

```bash
cd notebooklm-st
uv sync
uv run notebooklm login
```

크로미움이 열린다. 구글 로그인을 마치면 CLI 가
`~/.notebooklm/profiles/default/storage_state.json` 에 저장한다
(윈도우는 `C:\Users\<사용자>\.notebooklm\profiles\default\`).

홈서버 대시보드에서.

1. 만료 배너 아래 **자격증명 올리기** 를 편다.
2. 그 `storage_state.json` 을 고른다.
3. **반입** 을 누른다.

반입에 성공하면 앱이 곧바로 다시 확인까지 하고 화면을 새로 그린다.
업로드가 안 될 때의 대체 경로와 자격증명 취급 수칙은
[인증이 만료됐을 때 되살리기](2026-09-16-auth-reseed.md) 에 있다.

## 4. 기존 데이터 옮기기 (선택)

데스크톱에서 쓰던 질문 템플릿과 이력을 가져오려면 앱을 내린 뒤
`questions.db` 를 복사한다.

```bash
docker compose down
scp <사용자>@<데스크톱>:notebooklm-st/questions.db ./data/questions.db
sudo chown "$(id -u):$(id -g)" data/questions.db
docker compose up -d
```

스키마가 다르면 앱이 연결 시점에 안내와 함께 멈춘다. 이 프로젝트는
마이그레이션을 지원하지 않으므로, 그때는 파일을 지우고 새로 시작한다.

## 5. 검증

배포 뒤 한 번 돈다. 1~4 번은 CI 가 매 push 마다 자동으로 하지만,
5~8 번은 실제 홈서버와 계정이 있어야 해서 사람이 한다.

| # | 확인 | 통과 기준 |
|---|---|---|
| 1 | `docker compose build` | 성공 |
| 2 | `docker compose run --rm app python -c "import playwright"` | **실패해야 정상** |
| 3 | `docker compose run --rm app python -c "import datetime; print(datetime.datetime.now().astimezone())"` | `+09:00` |
| 4 | `docker compose ps` | `healthy` |
| 5 | 다른 기기에서 `http://<홈서버IP>:9004` | 화면이 뜬다 |
| 6 | `ls -l data/` | `questions.db`·`notebooklm/` 이 내 UID 소유 |
| 7 | 업로드 UI 로 자격증명 반입 | 배너가 사라진다 |
| 8 | `docker compose down && docker compose up -d` | 질문·이력·인증이 보존된다 |

## 운영 규칙

- **인터넷에 내놓지 않는다.** 대시보드의 자격증명 업로드 폼은 앱이
  외부에 노출되지 않는다는 전제 위에 있다. 포트포워딩·리버스
  프록시·터널로 9004 를 인터넷에 열려면 먼저 업로드 폼을 제거해야
  한다. 홈 LAN 안에서도 구간은 평문 HTTP 다 — 같은 Wi-Fi 의 다른
  기기에는 보인다. **방화벽으로 막았다고 안심하지 않는다** — 도커는
  iptables 에 직접 규칙을 넣어 `ufw` 같은 호스트 방화벽을 우회한다.
  라우터에서 9004 를 포워딩하지 않는 것이 유일한 방어선이다.
- **볼륨에 `:ro` 를 걸지 않는다.** 앱이 회전된 쿠키를 되쓴다. 읽기
  전용으로 마운트하면 재시작마다 옛 쿠키로 돌아가고 결국 죽는다.
- **실행 중일 때 재시작하지 않는다.** 질의는 백그라운드 스레드에서
  돌고 이력은 끝난 뒤에 저장된다. 진행 중에 내리면 그 실행은 결과를
  남기지 못한다. **실행 현황** 화면이 비었을 때 내린다.
- **UID 가 1000 이 아니면 `PUID`/`PGID` 로 덮는다.** 재빌드는 필요
  없다.

## 인증이 만료되면

인증 판정은 **앱이 뜰 때 한 번만** 한다. 떠 있는 도중에 세션이 죽으면
배너는 다시 그려지지 않는다.

```bash
docker restart notebooklm-st
```

배너가 다시 뜨면 3단계의 반입 절차를 따른다.

## 로그 보기

화면이 "자세한 사유는 앱 로그에 남습니다" 라고 안내할 때 볼 곳이다.

```bash
docker logs notebooklm-st
docker compose logs -f app
```

로그는 10MB 씩 3개까지만 보관한다(`docker-compose.yml`).
