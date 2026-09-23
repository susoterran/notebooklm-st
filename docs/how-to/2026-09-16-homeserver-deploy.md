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

## 4. Outline 연결하기

요약본과 정리본은 Outline 에 저장된다. 앱에는 문서명과 링크만
남는다.

### 4.1 API 키 만들기

Outline 웹에서 **프로필 → Settings → API Keys → New API Key**.

- **Scopes** 칸에 둘을 **공백으로 구분해 한 줄로** 적는다.

  ```
  documents.create documents.info
  ```

  앱은 요약본을 올릴 때 앞의 것을, 정리본의 재료를 읽을 때 뒤의 것을
  쓴다. 둘뿐이라 키가 새더라도 삭제·사용자 조회는 막힌다.
  **비워 두면 전체 권한**이 되니 비우지 않는다.
- **지금까지 요약본 저장만 하던 키로는 정리본이 돌지 않는다.** 정리를
  시작하면 **401** 이 나고 본문은 `Authentication required` 다(실측).
  권한 오류가 아니라 인증 오류로 오므로 토큰이 죽은 것처럼 보이지만,
  저장이 되고 있다면 토큰은 멀쩡하고 scope 가 문제다. 화면이 scope
  부터 짚는다. 키를 새로 만들어 `NOTEBOOKLM_ST_OUTLINE_TOKEN` 을
  바꾸면 된다.
- 키 값은 만든 직후 한 번만 보인다. 바로 복사한다.

키는 **만든 사용자의 권한을 상속한다.** "이 컬렉션에만" 이라는 범위
지정은 없으므로, 컬렉션 단위로 가두려면 그 컬렉션에만 접근 가능한
사용자를 따로 만들어 그 사용자로 키를 발급해야 한다.

### 4.2 컬렉션 ID 찾기

`collectionId` 는 UUID 다. 화면 주소의 슬러그와 다르므로 API 로
확인한다. 이 조회에만 scope 를 넓힌 임시 키가 필요하고, 확인이 끝나면
지운다.

```bash
read -rs OUTLINE_TOKEN   # 화면에 안 찍히고 히스토리에도 안 남는다
curl -s -X POST http://localhost:3000/api/collections.list \
  -H "Authorization: Bearer $OUTLINE_TOKEN" \
  -H "Content-Type: application/json" -d '{}' \
  | python3 -c 'import json,sys; [print(c["id"], c["name"]) for c in json.load(sys.stdin)["data"]]'
```

### 4.3 값 넣기

1 절에서 만든 compose 환경 파일에 세 줄을 더한다. 이 파일은
`.gitignore` 와 `.dockerignore` 에 이미 들어 있어 저장소나 이미지로
새지 않는다.

```bash
cat >> .env <<'EOF'
NOTEBOOKLM_ST_OUTLINE_URL=http://192.168.0.10:3000
NOTEBOOKLM_ST_OUTLINE_TOKEN=<복사한 키>
NOTEBOOKLM_ST_OUTLINE_COLLECTION=<위에서 찾은 UUID>
EOF
docker compose up -d
```

셋 중 하나라도 비면 앱은 그대로 뜨고 이력 화면의 저장 버튼 자리에
안내만 나온다.

**주소는 컨테이너 안에서 닿는 것이어야 한다.** `localhost` 는 쓸 수
없다 — 컨테이너 안의 `localhost` 는 호스트가 아니라 그 컨테이너
자신이다. Outline 이 같은 호스트에 있어도 마찬가지다. 호스트 주소나
Outline 컨테이너 이름을 쓴다.

의심스러우면 컨테이너 안에서 직접 확인한다. 이미지에 `curl` 이 없으므로
앱이 쓰는 것과 같은 httpx 로 본다.

```bash
docker exec notebooklm-st python -c "
import os, httpx
u = os.environ['NOTEBOOKLM_ST_OUTLINE_URL']
print(httpx.get(u, timeout=10).status_code)"
```

### 4.4 링크가 열리지 않으면 (선택)

저장은 되는데 이력의 링크를 눌러 Outline 로그인 화면만 나온다면,
**앱이 붙은 주소와 사용자의 세션이 있는 주소가 다르기 때문이다.**

Outline 은 문서 URL 을 `/doc/…` 같은 상대 경로로 돌려주므로, 앱이 붙은
주소가 그대로 링크 앞에 붙는다. 세션 쿠키는 Outline 의 정식 도메인에
묶여 있어 다른 주소로 열면 인증이 안 된 상태가 된다.

이때 링크에 적을 주소를 따로 준다.

```bash
cat >> .env <<'EOF'
NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL=https://outline.example.com
EOF
docker compose up -d
```

이 변수는 **링크를 만들 때만** 쓰인다. API 호출은 계속
`NOTEBOOKLM_ST_OUTLINE_URL` 로 나간다. 두 주소가 같아도 되고, 비워 두면
연결 주소를 그대로 쓴다.

**이미 저장된 문서의 링크는 소급되지 않는다.** DB 에 문자열로 박혀 있다.
그 이력을 지우고 다시 저장하면 새 주소로 남는다(Outline 쪽 문서는 남으니
거기서 따로 지운다).

### 4.5 옛 DB 지우기

R4 는 `runs` 테이블에 컬럼을 넷 더한다. 이 프로젝트는 마이그레이션을
두지 않으므로 **R4 이전 `questions.db` 는 열리지 않는다.** 앱이 연결
시점에 안내와 함께 멈춘다.

```bash
docker compose down
rm data/questions.db
docker compose up -d
```

질문 템플릿도 함께 사라진다. 질문 관리 화면에서 다시 등록한다.

## 5. 검증

배포 뒤 한 번 돈다. 1~4 번은 이미지를 굽는 워크플로
(`.github/workflows/build.yml`)가 게시 전에 자동으로 하지만, 5~8 번은
실제 홈서버와 계정이 있어야 해서 사람이 한다.

| # | 확인 | 통과 기준 |
|---|---|---|
| 1 | `docker compose build` | 성공 |
| 2 | `docker compose run --rm app python -c "import playwright"` | **실패해야 정상** |
| 3 | `docker compose run --rm app python -c "import datetime; print(datetime.datetime.now().astimezone())"` | `+09:00` |
| 4 | `docker compose ps` | `healthy` |
| 5 | 다른 기기에서 `http://<홈서버IP>:9004` | 화면이 뜬다 |
| 6 | `ls -l data/` | `questions.db`·`notebooklm/` 이 내 UID 소유 |
| 7 | 업로드 UI 로 자격증명 반입 | 배너가 사라진다 |
| 8 | `docker compose down && docker compose up -d` | 질문·문서 링크·인증이 보존된다 |
| 9 | 이력에서 실행 하나를 Outline 에 저장 | 문서가 컬렉션에 생기고, 이력이 링크 한 줄로 바뀐다 |

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
