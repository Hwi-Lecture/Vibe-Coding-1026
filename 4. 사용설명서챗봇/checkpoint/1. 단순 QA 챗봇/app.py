"""A simple Streamlit chatbot with an editable system prompt."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SYSTEM_PROMPT = "당신은 사용자의 질문에 친절하고 이해하기 쉽게 답변하는 챗봇입니다."


def load_dotenv() -> None:
    """Load simple KEY=VALUE entries from the local .env file."""
    project_root = BASE_DIR.parent.parent if BASE_DIR.parent.name == "checkpoint" else BASE_DIR
    values = {}
    for env_path in dict.fromkeys([project_root / ".env", BASE_DIR / ".env"]):
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip(chr(34)).strip(chr(39))
    for name, value in values.items():
        os.environ.setdefault(name, value)


load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("openai_model", "gpt-4o-mini")


def get_api_key() -> str | None:
    try:
        return (
            st.secrets.get("openai_api_key")
            or st.secrets.get("OPENAI_API_KEY")
            or os.getenv("openai_api_key")
            or os.getenv("OPENAI_API_KEY")
        )
    except (FileNotFoundError, AttributeError):
        return os.getenv("openai_api_key") or os.getenv("OPENAI_API_KEY")


def get_assistant_reply(messages: list[dict[str, str]], system_prompt: str) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("프로젝트 폴더의 .env 파일에서 openai_api_key 설정을 확인해 주세요.")

    from openai import OpenAI

    response = OpenAI(api_key=api_key).chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system_prompt}, *messages],
    )
    return response.choices[0].message.content or "답변을 생성하지 못했습니다. 다시 질문해 주세요."


st.set_page_config(page_title="AI 챗봇 실습", page_icon="💬", layout="centered")
st.markdown("""
<style>
    .block-container {max-width: 860px; padding-top: 2rem; padding-bottom: 3rem;}
    [data-testid="stChatMessage"] {border-radius: 16px;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("챗봇 설정")
    system_prompt = st.text_area(
        "시스템 프롬프트",
        key="system_prompt",
        value=DEFAULT_SYSTEM_PROMPT,
        height=220,
        help="챗봇의 역할과 답변 방식을 직접 적어보세요.",
    )
    st.caption("프롬프트를 수정하면 다음 질문부터 적용됩니다.")
    if st.button("대화 지우기", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.title("💬 AI 챗봇 실습")
st.write("질문을 입력해 보세요. 왼쪽에서 시스템 프롬프트를 바꾸며 답변을 비교할 수 있습니다.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "안녕하세요! 무엇이든 편하게 질문해 주세요."}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("메시지를 입력해 주세요")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("답변을 작성하고 있어요…"):
                reply = get_assistant_reply(
                    [
                        {"role": message["role"], "content": message["content"]}
                        for message in st.session_state.messages
                        if message["role"] in {"user", "assistant"}
                    ],
                    system_prompt.strip() or DEFAULT_SYSTEM_PROMPT,
                )
            st.markdown(reply)
        except Exception as exc:
            reply = f"답변을 가져오지 못했습니다. 설정을 확인한 뒤 다시 시도해 주세요. ({type(exc).__name__})"
            st.error(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
