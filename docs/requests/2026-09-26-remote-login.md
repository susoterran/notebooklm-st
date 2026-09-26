# notebooklm-st 인증 절차 개선
## 1. 개요

notebooklm-st을 사용하기 위한 복잡한 인증 절차를 개선한다.

## 2. 무엇이 불편했나?

1. 로컬이 아닌 환경에서는 notebooklm-py 인증이 불가능하다.
    - notebooklm-py를 사용하기 위해 구글 인증이 필요하고, 구글 인증은 로컬 브라우저에서 진행했다.
    - 로컬에서 `uv run notebooklm login` 명령어를 이용해야 하며, 로컬 브라우저를 통해 구글 인증을 통과한 후 이에 대한 `storage_state.json` 파일을 저장한다.
    - 저장한 `storage_state.json` 파일을 notebooklm-st에서 인증 용도로 사용한다.
    - 이러다 보니 로그인을 실행할 수 없는 환경에서는 notebooklm-py를 사용할 수 없게 된다.

## 3. 요구 기능

1. 로컬이 아닌 notebooklm-st 에서 notebooklm-py의 인증을 수행할 수 있어야 한다.