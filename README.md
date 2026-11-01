# Company GPT Chat

회사 Azure OpenAI 호환 API(GPT-5.4)를 연결하는 **간단한 Streamlit 채팅 앱**입니다.

## 기능
- ChatGPT 스타일 채팅 화면, Markdown/코드 블록 표시, 답변 스트리밍
- 여러 대화 생성/전환/삭제, 첫 질문으로 제목 자동 지정
- SQLite로 채팅 기록 로컬 보관(`data/chats.sqlite3`)
- 이전 메시지 문맥 전송, 시스템 지침 설정, 문맥 길이 조절
- 📎 **채팅 창 파일 첨부 및 LLM 전달 지원**: PDF, Word(.docx), Excel(.xlsx/.xls), CSV, 텍스트/코드, 이미지(멀티모달) 파일 첨부 및 자동 파싱/분석
- 스트리밍을 지원하지 않는 사내 API를 위한 설정
- Langfuse Observability(Trace/Generation 로깅, `LegalChat` 시스템 메타데이터 및 대화 세션 자동 추적)
- LLM temperature `0` 고정, Langfuse trace/generation 이름과 태그는 기본 `LegalChat`

## Windows에서 실행

1. Python 3.10 이상 설치 (설치 시 **Add python.exe to PATH** 권장).
2. ZIP 압축 해제.
3. `.env.example` 파일을 복사해 `.env`로 이름을 바꾸고 **실제 회사 접속 정보** 및 **Langfuse 설정** 입력:
   ```ini
   AZURE_OPENAI_ENDPOINT=https://실제-회사-엔드포인트
   AZURE_OPENAI_API_KEY=실제-회사-발급-키
   AZURE_OPENAI_API_VERSION=2024-12-01
   AZURE_OPENAI_MODEL=gpt-5.4
   LLM_STREAM=true

   # Langfuse 설정
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=http://localhost:3001
   LANGFUSE_SYSTEM_NAME=LegalChat
   ```
4. `run_windows.bat` 더블클릭.
5. 표시되는 브라우저 주소(`http://localhost:8502`) 접속.

### 명령어로 실행 (Windows PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# .env 수정 후
streamlit run app.py
```
PowerShell 정책으로 가상환경 활성화가 차단되면 `.venv\Scripts\python.exe -m streamlit run app.py`로 실행할 수 있습니다.

### Mac/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env 수정 후
streamlit run app.py
```

## API 관련 주의사항
- 회사가 제공한 예제와 같은 `AzureOpenAI(...).chat.completions.create(model=..., messages=...)` 호출을 사용합니다.
- 사내 API에서 **모델명 대신 배포명**을 요구하면 `AZURE_OPENAI_MODEL`에 배포명을 입력하세요.
- 회사의 프록시/네트워크/SSL 인증서 조건은 회사 안내를 따르세요.
- 일부 사내 게이트웨이는 `stream=True` 미지원입니다. 응답 오류가 발생하면 `LLM_STREAM=false`로 바꾸고 재시작하세요.
- 사용 가능한 기능은 회사에서 제공하는 모델과 서버 설정에 달려 있습니다. 실제 연결은 회사 네트워크/키 없이는 검증할 수 없습니다.

### Langfuse 토큰 사용량 및 비용
- 스트리밍 요청에 `stream_options={"include_usage": true}`를 전달해 마지막 청크의 실제 토큰 사용량을 수집합니다. 사내 API도 이 옵션과 `usage` 반환을 지원해야 합니다.
- 토큰 사용량이 있어도 비용이 비어 있거나 `0`이면 Langfuse **Project Settings → Models**에서 응답의 실제 모델명(예: `gpt-5.4-2026-03-05`)에 맞는 모델 정의와 입력/출력 토큰 단가가 있는지 확인하세요. 단가는 실제 제공업체의 과금 기준으로 설정합니다.
- API가 사용량을 보내지 않으면 입력·출력 텍스트만으로 정확한 사용량(추론 토큰 포함)을 알 수 없습니다. 기존 trace의 누락된 사용량/비용은 이 변경으로 소급 복구되지 않습니다.

## 보안 및 데이터
- `.env` 파일과 `data/`는 `.gitignore`로 제외됩니다. **키나 대화 기록을 Git/공유 폴더에 올리지 마세요.**
- 대화 내용은 모델 요청 시 회사 API로 전송되며, 로컬 PC의 SQLite DB에도 저장됩니다.
- **로그인/계정별 접근제어, 저장 데이터 암호화가 없는 개인용 프로토타입**입니다. 회사 외부에 공개하거나 여러 사용자가 공유하는 서버에 배포하지 마세요.
- 오류 세부정보에는 게이트웨이 메시지가 포함될 수 있으니 외부 공유 전에 확인하세요.

## 구조
```text
company-llm-chat/
  app.py              Streamlit UI 및 LLM 연결
  chat_store.py       SQLite 대화 관리
  requirements.txt
  .env.example        설정 템플릿 (실제 비밀키 없음)
  run_windows.bat     Windows 실행
  tests/test_store.py DB 유닛 테스트
  README.md
```

## 테스트
```bash
python -m unittest discover -s tests -v
```
