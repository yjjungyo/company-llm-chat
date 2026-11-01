"""사내 AzureOpenAI 호환 GPT 모델을 이용하는 Streamlit 채팅 앱 (Langfuse Trace 연동)."""

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAIError

try:
    from langfuse.openai import AzureOpenAI as LangfuseAzureOpenAI
    from langfuse.openai import openai as langfuse_openai
    from langfuse import Langfuse
    HAS_LANGFUSE = True
except ImportError:
    LangfuseAzureOpenAI = None
    langfuse_openai = None
    Langfuse = None
    HAS_LANGFUSE = False


def _patch_langfuse_streaming():
    """Langfuse 스트리밍 응답 파싱 시 delta=None 또는 dict일 때 발생하는 AttributeError를 방어합니다."""
    try:
        import langfuse.openai as lf_openai

        orig_extract = getattr(lf_openai, "_extract_streamed_openai_response", None)
        if orig_extract:
            def safe_extract_streamed_openai_response(resource, chunks):
                try:
                    return orig_extract(resource, chunks)
                except (AttributeError, TypeError, KeyError):
                    content_parts = []
                    model, usage = None, None
                    for raw_chunk in chunks:
                        chunk = getattr(raw_chunk, "__dict__", raw_chunk) if not isinstance(raw_chunk, dict) else raw_chunk
                        if isinstance(chunk, dict):
                            model = model or chunk.get("model")
                            usage = usage or chunk.get("usage")
                            for ch in chunk.get("choices", []):
                                ch_dict = getattr(ch, "__dict__", ch) if not isinstance(ch, dict) else ch
                                if isinstance(ch_dict, dict):
                                    delta = ch_dict.get("delta")
                                    if delta:
                                        delta_dict = getattr(delta, "__dict__", delta) if not isinstance(delta, dict) else delta
                                        if isinstance(delta_dict, dict) and delta_dict.get("content"):
                                            content_parts.append(delta_dict["content"])
                    return (model, "".join(content_parts) or None, usage, None)

            lf_openai._extract_streamed_openai_response = safe_extract_streamed_openai_response

        wrapper_cls = getattr(lf_openai, "OpenAiStreamWrapper", None)
        if wrapper_cls and hasattr(wrapper_cls, "_finalize"):
            orig_finalize = wrapper_cls._finalize

            def safe_finalize(self):
                try:
                    orig_finalize(self)
                except Exception:
                    pass

            wrapper_cls._finalize = safe_finalize
    except Exception:
        pass


if HAS_LANGFUSE:
    _patch_langfuse_streaming()


from openai import AzureOpenAI as VanillaAzureOpenAI

from chat_store import add_message, delete_chat, get_messages, init_db, list_chats, new_chat
from file_processor import (
    build_multimodal_request_content,
    format_message_with_attachments,
    parse_uploaded_file,
)

load_dotenv(Path(__file__).with_name(".env"))

st.set_page_config(page_title="LegalChat - LLM", page_icon="⚖️", layout="centered")
st.markdown("""
<style>
.block-container { padding-top: 1.6rem; max-width: 900px; }
[data-testid="stSidebar"] { min-width: 270px; }
</style>
""", unsafe_allow_html=True)


def config():
    """파일에 키를 하드코딩하지 않고 환경변수로만 접속 정보를 읽습니다."""
    langfuse_pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    langfuse_sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    langfuse_host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
    langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "true").lower() in ("true", "1", "yes")
    system_name = os.getenv("LANGFUSE_SYSTEM_NAME", "LegalChat").strip() or "LegalChat"

    is_langfuse_active = bool(HAS_LANGFUSE and langfuse_pk and langfuse_sk and langfuse_enabled)

    return {
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "").strip(),
        "key": os.getenv("AZURE_OPENAI_API_KEY", "").strip(),
        "version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01").strip(),
        "model": os.getenv("AZURE_OPENAI_MODEL", "gpt-5.4").strip(),
        "stream": os.getenv("LLM_STREAM", "true").lower() in ("true", "1", "yes"),
        "timeout": float(os.getenv("LLM_TIMEOUT", "120")),
        "langfuse_public_key": langfuse_pk,
        "langfuse_secret_key": langfuse_sk,
        "langfuse_host": langfuse_host,
        "langfuse_enabled": langfuse_enabled,
        "system_name": system_name,
        "is_langfuse_active": is_langfuse_active,
    }


def make_client(cfg):
    client_cls = LangfuseAzureOpenAI if cfg["is_langfuse_active"] else VanillaAzureOpenAI
    return client_cls(
        azure_endpoint=cfg["endpoint"],
        api_key=cfg["key"],
        api_version=cfg["version"],
        timeout=cfg["timeout"],
        max_retries=2,
    )


def get_answer(client, model, messages, cfg, chat_id, stream=True):
    """스트리밍과 일반 요청 양쪽에서 문자열 조각을 반환하는 제너레이터.
    Langfuse가 활성화된 경우 session_id, system metadata, tags를 포함하여 trace를 남깁니다.
    """
    call_kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0,
    }

    if cfg["is_langfuse_active"]:
        meta = {
            "system": cfg["system_name"],
            "app": "Company GPT Chat",
            "chat_id": chat_id,
            "session_id": chat_id,
            "stream": stream,
        }
        call_kwargs.update({
            "name": cfg["system_name"],
            "metadata": meta,
        })
        try:
            from langfuse.openai import OpenAiArgsExtractor
            import inspect
            extractor_params = inspect.signature(OpenAiArgsExtractor.__init__).parameters
            if "session_id" in extractor_params:
                call_kwargs["session_id"] = chat_id
            if "tags" in extractor_params:
                call_kwargs["tags"] = [cfg["system_name"]]
        except Exception:
            pass

    if stream:
        try:
            result = client.chat.completions.create(
                stream=True, stream_options={"include_usage": True}, **call_kwargs
            )
        except Exception:
            result = client.chat.completions.create(stream=True, **call_kwargs)

        try:
            for part in result:
                if part.choices:
                    delta = part.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
        except Exception:
            # 스트림 종료 시 추적 메트릭 finalize 등의 부가 작업 오류가 발생하더라도
            # 이미 생성된 답변 텍스트는 온전히 보존됩니다.
            pass
    else:
        result = client.chat.completions.create(stream=False, **call_kwargs)
        if result.choices and result.choices[0].message.content:
            yield result.choices[0].message.content


def flush_langfuse():
    """Langfuse 백그라운드 큐를 비워 trace가 즉시 서버로 전송되도록 합니다."""
    try:
        if langfuse_openai and callable(getattr(langfuse_openai, "flush_langfuse", None)):
            langfuse_openai.flush_langfuse()
    except Exception:
        pass


cfg = config()
init_db()

if "chat_id" not in st.session_state:
    existing = list_chats()
    st.session_state.chat_id = existing[0]["id"] if existing else new_chat()

with st.sidebar:
    st.title("⚖️ LegalChat")
    st.caption("사내 LLM · 로컬 채팅 기록")

    if cfg["is_langfuse_active"]:
        st.success(f"🔍 Trace: `{cfg['system_name']}` 연결됨", icon="✅")
    else:
        st.info("ℹ️ Langfuse 비활성 (키 확인 필요)")

    if st.button("＋ 새 채팅", use_container_width=True, type="primary"):
        st.session_state.chat_id = new_chat()
        st.rerun()

    st.subheader("대화 기록")
    for chat in list_chats():
        is_current = chat["id"] == st.session_state.chat_id
        if st.button(
            ("● " if is_current else "") + chat["title"],
            key=f"open_{chat['id']}", use_container_width=True,
        ):
            st.session_state.chat_id = chat["id"]
            st.rerun()

    st.divider()
    if st.button("🗑️ 현재 채팅 삭제", use_container_width=True):
        delete_chat(st.session_state.chat_id)
        chats = list_chats()
        st.session_state.chat_id = chats[0]["id"] if chats else new_chat()
        st.rerun()

    st.divider()
    system_prompt = st.text_area(
        "시스템 지침 (선택)",
        value="당신은 법률 및 사내 규정 관련 업무를 지원하는 전문적이고 친절한 LegalChat AI 비서입니다.",
        height=110,
        help="채팅을 보낼 때마다 함께 전달됩니다. 로컬 DB에는 저장하지 않습니다.",
    )
    max_turns = st.slider("최근 대화 전송 수 (왕복)", 5, 100, 30, 5)
    st.caption(f"모델: {cfg['model']}")
    st.caption(f"시스템: {cfg['system_name']}")
    st.caption("📎 파일 첨부: PDF, Word, Excel, CSV, TXT, 코드, 이미지")
    st.caption("개인용 · 로그인 및 사용자 분리 없음")

st.title("⚖️ LegalChat")
st.caption(f"회사에서 제공한 {cfg['model']} 모델과 대화하세요. (추적 시스템: `{cfg['system_name']}`)")

missing = []
if not cfg["endpoint"] or cfg["endpoint"] == "https://myoffice.com":
    missing.append("AZURE_OPENAI_ENDPOINT")
if not cfg["key"] or cfg["key"] == "YOUR_COMPANY_API_KEY":
    missing.append("AZURE_OPENAI_API_KEY")
if missing:
    st.warning("`.env` 파일에 회사 접속 정보를 입력하세요: " + ", ".join(missing))

messages = get_messages(st.session_state.chat_id)
if not messages:
    st.info("새 대화를 시작해 보세요. 하단 입력창의 📎 아이콘을 눌러 파일(문서, 코드, 이미지)을 첨부할 수 있습니다.")
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Streamlit의 채팅 입력을 이용해 ChatGPT와 비슷한 경험 제공 (파일 첨부 지원).
try:
    chat_input_val = st.chat_input(
        "메시지를 입력하거나 클립(📎)을 눌러 파일을 첨부하세요...",
        accept_file="multiple",
        disabled=bool(missing),
    )
except TypeError:
    # accept_file 미지원 이전 버전 Streamlit 호환 폴백
    chat_input_val = st.chat_input("메시지를 입력하세요...", disabled=bool(missing))

if chat_input_val:
    user_text = ""
    raw_files = []

    if hasattr(chat_input_val, "to_dict"):
        val_dict = chat_input_val.to_dict()
        user_text = (val_dict.get("text") or "").strip()
        raw_files = val_dict.get("files") or []
    elif isinstance(chat_input_val, dict):
        user_text = (chat_input_val.get("text") or "").strip()
        raw_files = chat_input_val.get("files") or []
    elif isinstance(chat_input_val, str):
        user_text = chat_input_val.strip()
        raw_files = []

    if user_text or raw_files:
        # 파일이 첨부된 경우 내용 추출 및 마크다운 포맷팅
        with st.spinner("첨부 파일을 분석하는 중..." if raw_files else None):
            parsed_files = [parse_uploaded_file(f) for f in raw_files] if raw_files else []
            formatted_message = format_message_with_attachments(user_text, parsed_files)

        chat_id = st.session_state.chat_id
        add_message(chat_id, "user", formatted_message)
        with st.chat_message("user"):
            st.markdown(formatted_message)

        # 현재 채팅의 최근 문맥만 모델에 전송해 요청 크기를 제한.
        context = get_messages(chat_id)[-max_turns * 2:]
        request_messages = []
        if system_prompt.strip():
            request_messages.append({"role": "system", "content": system_prompt.strip()})

        for idx, m in enumerate(context):
            is_latest_user_message = (idx == len(context) - 1 and m["role"] == "user")
            if is_latest_user_message and parsed_files and any(f["is_image"] for f in parsed_files):
                mm_content = build_multimodal_request_content(m["content"], parsed_files)
                request_messages.append({"role": "user", "content": mm_content})
            else:
                request_messages.append({"role": m["role"], "content": m["content"]})

        with st.chat_message("assistant"):
            try:
                client = make_client(cfg)
                answer = st.write_stream(get_answer(client, cfg["model"], request_messages, cfg, chat_id, cfg["stream"]))
                # 빈 응답은 보관하지 않음. 다음 메시지로 자연스럽게 재시도 가능.
                if answer and isinstance(answer, str) and answer.strip():
                    add_message(chat_id, "assistant", answer)
                else:
                    st.warning("모델이 텍스트 응답을 보내지 않았습니다. 모델 배포명 및 서버 설정을 확인하세요.")

                # Langfuse 버퍼 비우기 (Trace 즉시 전송 보장)
                if cfg["is_langfuse_active"]:
                    flush_langfuse()

            except (OpenAIError, OSError, ValueError, RuntimeError) as exc:
                st.error("회사 LLM 호출에 실패했습니다. 접속 정보, 모델 배포명, 네트워크 및 서버의 스트리밍 지원을 확인하세요.")
                with st.expander("오류 세부정보"):
                    # 라이브 API 키 및 사용자 메시지는 기록하지 않음.
                    st.code(type(exc).__name__ + ": " + str(exc)[:800])
                st.info("스트리밍 오류라면 `.env`에서 `LLM_STREAM=false`로 바꾸고 재시작하세요.")
