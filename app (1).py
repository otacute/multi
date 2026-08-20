import os
import uuid
import gradio as gr
from openai import OpenAI

# ============================================================
# 1. OpenAI API 설정
# ============================================================

# Render에서는 환경변수 OPENAI_API_KEY를 사용합니다.
api_key = os.environ.get("OPENAI_API_KEY")

if not api_key:
    raise ValueError(
        "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
        "Render의 Environment Variables에 API Key를 등록하세요."
    )

client = OpenAI(api_key=api_key)

MODEL = "gpt-4o-mini"


# ============================================================
# 2. Thread 관련 함수
# ============================================================

def create_thread(conversations):
    """현재 사용자의 새로운 대화 Thread를 생성합니다."""
    thread_id = str(uuid.uuid4())

    conversations[thread_id] = {
        "title": "새로운 대화",
        "messages": []
    }

    return thread_id


def get_thread_choices(conversations):
    """왼쪽 이전 대화 목록을 생성합니다."""
    choices = []

    for thread_id, data in conversations.items():
        title = data["title"]

        if len(title) > 30:
            title = title[:30] + "..."

        choices.append((title, thread_id))

    return choices


def make_chat_list_update(conversations, selected_thread_id):
    """Radio 컴포넌트의 choices/value를 업데이트합니다."""
    return gr.Radio(
        choices=get_thread_choices(conversations),
        value=selected_thread_id,
        label="",
        interactive=True
    )


# ============================================================
# 3. OpenAI 응답
# ============================================================

def get_ai_response(thread_id, conversations):
    """현재 Thread의 전체 대화 context를 OpenAI에 전달합니다."""

    messages = conversations[thread_id]["messages"]

    system_message = {
        "role": "system",
        "content": (
            "당신은 친절하고 정확한 AI assistant입니다. "
            "현재 대화의 이전 내용을 기억하고 자연스럽게 답변하세요."
        )
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[system_message] + messages
    )

    return response.choices[0].message.content


# ============================================================
# 4. 메시지 전송
# ============================================================

def send_message(message, thread_id, conversations):

    # Thread가 없으면 새로 생성
    if not thread_id or thread_id not in conversations:
        thread_id = create_thread(conversations)

    # 빈 메시지 처리
    if not message or not message.strip():
        return (
            "",
            conversations[thread_id]["messages"],
            make_chat_list_update(conversations, thread_id),
            thread_id,
            conversations
        )

    message = message.strip()

    # --------------------------------------------------------
    # 사용자 메시지 저장
    # --------------------------------------------------------

    conversations[thread_id]["messages"].append({
        "role": "user",
        "content": message
    })

    # --------------------------------------------------------
    # 첫 번째 질문을 대화 제목으로 사용
    # --------------------------------------------------------

    if len(conversations[thread_id]["messages"]) == 1:
        title = message

        if len(title) > 30:
            title = title[:30] + "..."

        conversations[thread_id]["title"] = title

    # --------------------------------------------------------
    # OpenAI 응답
    # --------------------------------------------------------

    try:
        answer = get_ai_response(
            thread_id,
            conversations
        )

    except Exception as e:
        answer = (
            "⚠️ OpenAI API 호출 중 오류가 발생했습니다.\n\n"
            f"{str(e)}"
        )

    # --------------------------------------------------------
    # AI 응답 저장
    # --------------------------------------------------------

    conversations[thread_id]["messages"].append({
        "role": "assistant",
        "content": answer
    })

    # --------------------------------------------------------
    # 화면 업데이트
    # --------------------------------------------------------

    return (
        "",
        conversations[thread_id]["messages"],
        make_chat_list_update(conversations, thread_id),
        thread_id,
        conversations
    )


# ============================================================
# 5. 새로운 채팅
# ============================================================

def new_chat(conversations):

    thread_id = create_thread(conversations)

    return (
        [],
        make_chat_list_update(conversations, thread_id),
        thread_id,
        conversations
    )


# ============================================================
# 6. 이전 대화 불러오기
# ============================================================

def load_chat(thread_id, conversations):

    if not thread_id or thread_id not in conversations:
        return [], thread_id

    return (
        conversations[thread_id]["messages"],
        thread_id
    )


# ============================================================
# 7. 초기 사용자별 상태
# ============================================================

initial_conversations = {}
initial_thread_id = create_thread(initial_conversations)


# ============================================================
# 8. Gradio UI
# ============================================================

with gr.Blocks(
    title="Multi-Thread Chatbot"
) as demo:

    # --------------------------------------------------------
    # 사용자별 상태
    # --------------------------------------------------------

    conversations_state = gr.State(
        initial_conversations
    )

    current_thread = gr.State(
        initial_thread_id
    )

    with gr.Row():

        # ====================================================
        # 왼쪽 사이드바
        # ====================================================

        with gr.Column(
            scale=1,
            min_width=220
        ):

            gr.Markdown(
                """
                # 💬 Chatbot

                Multi-Thread  
                Multi-Turn
                """
            )

            new_chat_btn = gr.Button(
                "＋ 새로운 채팅",
                variant="primary"
            )

            gr.Markdown(
                "### 📚 이전 대화"
            )

            chat_list = gr.Radio(
                choices=get_thread_choices(
                    initial_conversations
                ),
                value=initial_thread_id,
                label="",
                interactive=True
            )

        # ====================================================
        # 오른쪽 Chat 화면
        # ====================================================

        with gr.Column(
            scale=4
        ):

            gr.Markdown(
                "# 🤖 AI Assistant"
            )

            chatbot = gr.Chatbot(
                label="",
                height=600
            )

            with gr.Row():

                message = gr.Textbox(
                    placeholder="메시지를 입력하세요...",
                    show_label=False,
                    scale=8,
                    lines=2
                )

                send_btn = gr.Button(
                    "전송",
                    variant="primary",
                    scale=1
                )

    # ========================================================
    # 9. 이벤트
    # ========================================================

    # --------------------------------------------------------
    # 전송 버튼
    # --------------------------------------------------------

    send_btn.click(
        fn=send_message,
        inputs=[
            message,
            current_thread,
            conversations_state
        ],
        outputs=[
            message,
            chatbot,
            chat_list,
            current_thread,
            conversations_state
        ]
    )

    # --------------------------------------------------------
    # Enter 키
    # --------------------------------------------------------

    message.submit(
        fn=send_message,
        inputs=[
            message,
            current_thread,
            conversations_state
        ],
        outputs=[
            message,
            chatbot,
            chat_list,
            current_thread,
            conversations_state
        ]
    )

    # --------------------------------------------------------
    # 새로운 채팅
    # --------------------------------------------------------

    new_chat_btn.click(
        fn=new_chat,
        inputs=[
            conversations_state
        ],
        outputs=[
            chatbot,
            chat_list,
            current_thread,
            conversations_state
        ]
    )

    # --------------------------------------------------------
    # 이전 대화 선택
    # --------------------------------------------------------

    chat_list.change(
        fn=load_chat,
        inputs=[
            chat_list,
            conversations_state
        ],
        outputs=[
            chatbot,
            current_thread
        ]
    )


# ============================================================
# 10. Render 실행
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))

    demo.launch(
        server_name="0.0.0.0",
        server_port=port
    )
