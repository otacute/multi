import base64
import json
import mimetypes
import os
import re
from html import escape
from pathlib import Path

import gradio as gr
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
REGIONS = ["거제", "서울", "부산", "인천", "대구", "광주", "대전", "울산", "제주", "수원", "춘천", "전주", "청주", "포항", "여수"]
SITUATIONS = ["일상복", "출근 / 학교", "데이트", "소개팅", "친구 모임", "여행", "면접"]
QUESTION_CHOICES = [
    "전체적인 분위기",
    "색 조합",
    "핏과 비율",
    "오늘 날씨에 어울리는지",
    "더 예뻐 보이는 아이템",
    "10대 아일릿 무드로 바꾸는 법",
]


SYSTEM_PROMPT = """
너는 Fit-Check라는 친절하고 감각적인 AI 패션 스타일리스트다.
사용자가 올린 착장 사진을 실제로 관찰해서 답변한다. 보이지 않는 정보는 추측하지 말고, 확실하지 않으면 그렇게 말한다.
답변은 한국어로 하고, 말투는 귀엽지만 지나치게 가볍지 않게 한다.

반드시 다음 항목을 포함한다:
1. 한 줄 총평과 10점 만점 점수
2. 사진에서 확인되는 아이템과 색상
3. 색 조합 및 전체 실루엣 평가
4. 선택한 지역 날씨와 상황을 고려한 적합성
5. 바로 적용할 수 있는 개선 팁 2~3개
6. 어울리는 브랜드나 쇼핑 키워드 2~3개

외모, 체형, 성별, 나이, 인종을 평가하거나 추측하지 않는다. 옷과 스타일링만 평가한다.
날씨 정보가 제공되지 않은 경우에는 현재 날씨를 단정하지 말고, 사용자가 선택한 지역을 기준으로 확인이 필요하다고 안내한다.
""".strip()


def image_to_data_url(image_path: str) -> str:
    path = Path(image_path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def format_history(history):
    lines = []
    for message in history or []:
        if isinstance(message, dict) and message.get("content"):
            role = "사용자" if message.get("role") == "user" else "스타일리스트"
            content = message["content"]
            if isinstance(content, str):
                lines.append(f"{role}: {content}")
    return "\n".join(lines[-8:])


def weather_card(region):
    index = REGIONS.index(region) if region in REGIONS else 0
    weather = [
        ("☀️", "SUNNY MOOD", "가볍고 반짝이는 날", "#ffd166"),
        ("🌤️", "SOFT CLOUD", "레이어드하기 좋은 날", "#b9d9ff"),
        ("🌧️", "RAINY POP", "러블리한 우산 포인트", "#a7b8ff"),
        ("🌈", "RAINBOW DAY", "컬러를 하나 더", "#ff9ecb"),
        ("☁️", "CLOUD NINE", "포근한 텍스처", "#d9d3f8"),
        ("🌬️", "BREEZY", "리본이 날리는 날", "#b8f0e4"),
    ][index % 6]
    return f"""
    <div class='weather-card' style='--weather-accent:{weather[3]}'>
        <div class='weather-icon'>{weather[0]}</div>
        <div><small>{escape(str(region))} · TODAY'S VIBE</small><strong>{weather[1]}</strong><span>{weather[2]}</span></div>
    </div>
    """


def build_visual_report(raw_answer, region, situation):
    data = {}
    match = re.search(r"\{.*\}", raw_answer, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    def value(key, fallback):
        item = data.get(key, fallback)
        return ", ".join(str(part) for part in item) if isinstance(item, list) else str(item)

    score = value("score", "분석 중")
    mood = value("mood", "오늘의 무드 체크")
    colors = value("colors", "핑크 · 크림 · 포인트 컬러")
    items = value("items", "핏에 맞는 베이직 아이템")
    styling = value("styling", "실루엣과 비율을 가볍게 정리해보세요")
    tips = value("tips", "작은 액세서리로 나만의 포인트를 더해보세요")
    commentary = value("commentary", raw_answer)
    score_number = re.search(r"\d+(?:\.\d+)?", score)
    score_value = min(10, max(0, float(score_number.group(0)))) if score_number else 0
    score_width = int(score_value * 10)
    palette = [part.strip() for part in colors.split(",") if part.strip()][:4]
    palette_html = "".join(f"<span class='color-chip'><i></i>{escape(part)}</span>" for part in palette)
    item_list = [part.strip() for part in items.split(",") if part.strip()][:3]
    items_html = "".join(f"<div class='item-gadget'><b>{idx:02d}</b><span>✦</span><strong>{escape(part)}</strong></div>" for idx, part in enumerate(item_list, 1))
    return f"""
    <section class='look-report'>
      <div class='report-top'>
        <div><small>✦ FIT-CHECK / STYLE BOARD</small><h2>{escape(mood)}</h2></div>
        <div class='sticker'>today<br><b>look!</b></div>
      </div>
      <div class='gadget-grid'>
        <div class='score-gadget'><span>LOOK<br>ENERGY</span><b>{escape(score)}</b><div class='meter'><i style='width:{score_width}%'></i></div><small>your vibe is loading...</small></div>
        <div class='palette-gadget'><span class='gadget-label'>COLOR STICKERS</span><div class='chip-list'>{palette_html}</div></div>
      </div>
      <div class='gadget-label section-label'>CLOSET PICKS / 03</div>
      <div class='item-gadgets'>{items_html}</div>
      <div class='move-gadget'><span class='gadget-label'>✧ ONE LITTLE STYLE MOVE</span><strong>{escape(styling)}</strong><p>{escape(tips)}</p></div>
      <div class='report-note'><b>{escape(str(region))} / {escape(str(situation))}</b><p>{escape(commentary)}</p></div>
    </section>
    """


def evaluate_look(image_path, question, region, situation, history):
    if isinstance(question, list):
        question = ", ".join(question)
    question = (question or "전체적인 분위기").strip()
    if not image_path:
        return history or [], "사진을 먼저 올려주세요.", "<div class='empty-report'>사진을 올리면 여기에 비주얼 리포트가 나타나요 ✦</div>"
        return history or [], "사진을 먼저 올려주세요. 옷이 잘 보이는 전신 또는 상반신 사진이면 좋아요."

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return history or [], "OPENAI_API_KEY가 설정되지 않았어요.", "<div class='empty-report'>API 키를 설정하면 스타일 리포트가 생성돼요.</div>"
        return history or [], "OPENAI_API_KEY가 설정되지 않았어요. `.env.example`을 참고해 환경변수를 설정한 뒤 다시 실행해주세요."

    try:
        client = OpenAI(api_key=api_key)
        context = f"선택 지역: {region}\n착용 상황: {situation}\n사용자 질문: {question}"
        context += "\nReturn ONLY valid JSON with keys: score, mood, colors, items, styling, tips, commentary. Write every value in natural Korean and keep it short."
        previous = format_history(history)
        if previous:
            context += f"\n이전 대화:\n{previous}"
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": context},
                    {"type": "input_image", "image_url": image_to_data_url(image_path), "detail": "high"},
                ],
            }],
        )
        answer = response.output_text.strip()
        report = build_visual_report(answer, region, situation)
        try:
            parsed = json.loads(re.search(r"\{.*\}", answer, re.DOTALL).group(0))
            chat_answer = parsed.get("commentary", answer)
        except (AttributeError, json.JSONDecodeError):
            chat_answer = answer
        updated = list(history or [])
        updated.extend([{"role": "user", "content": question}, {"role": "assistant", "content": chat_answer}])
        return updated, "", report
    except Exception as exc:
        return history or [], f"분석 중 문제가 발생했어요: {exc}", "<div class='empty-report'>잠시 후 다시 시도해 주세요.</div>"
        return history or [], f"분석 중 문제가 생겼어요: {exc}"


def clear_chat():
    return [], "", "<div class='empty-report'>사진을 올리면 여기에 비주얼 리포트가 나타나요 ✦</div>"
    return [], ""


custom_css = """
:root {
    --ink: #17151b;
    --muted: #746f7d;
    --line: #e8e3ed;
    --surface: rgba(255, 255, 255, .84);
    --lavender: #eee9ff;
    --pink: #ff4f9a;
    --violet: #6d4aff;
}

body {
    background: radial-gradient(circle at 8% 0%, #f9d9ea 0, transparent 28%),
                radial-gradient(circle at 92% 10%, #d9e8ff 0, transparent 28%),
                #f8f7fb;
    color: var(--ink);
}

.gradio-container {
    max-width: 1180px !important;
    padding: 28px 22px 42px !important;
}

.hero {
    position: relative;
    overflow: hidden;
    border: 1px solid rgba(23, 21, 27, .1);
    border-radius: 28px;
    background: linear-gradient(125deg, #201a2b 0%, #403061 52%, #ff71ad 150%);
    padding: 42px 46px 38px;
    margin-bottom: 22px;
    box-shadow: 0 18px 45px rgba(49, 35, 75, .18);
}

.hero:after {
    content: '✦';
    position: absolute;
    right: 7%;
    top: 12px;
    color: #fff;
    font-size: 112px;
    opacity: .12;
    transform: rotate(15deg);
}

.hero h1 {
    position: relative;
    z-index: 1;
    margin: 0;
    color: #fff;
    font-size: clamp(42px, 7vw, 78px);
    line-height: .92;
    letter-spacing: -.07em;
    font-weight: 850;
}

.hero p {
    position: relative;
    z-index: 1;
    max-width: 620px;
    margin: 18px 0 0;
    color: rgba(255, 255, 255, .76);
    font-size: 16px;
    line-height: 1.65;
}

.panel {
    border: 1px solid var(--line) !important;
    border-radius: 22px !important;
    background: var(--surface) !important;
    padding: 22px !important;
    box-shadow: 0 12px 30px rgba(38, 26, 57, .07) !important;
    backdrop-filter: blur(14px);
}

.panel h3, .panel h4 { color: var(--ink); letter-spacing: -.03em; }

.panel .gr-image, .panel .image-container {
    border-radius: 16px !important;
    border: 1.5px dashed #c8bfdc !important;
    background: var(--lavender) !important;
}

label span, .label {
    color: var(--muted) !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    letter-spacing: .04em;
    text-transform: uppercase;
}

textarea, input, .wrap, .form {
    border-color: var(--line) !important;
    border-radius: 13px !important;
    background: #fff !important;
}

button.primary {
    border: 0 !important;
    border-radius: 13px !important;
    background: linear-gradient(110deg, var(--pink), #ff78b4) !important;
    color: #fff !important;
    font-weight: 800 !important;
    box-shadow: 0 8px 18px rgba(255, 79, 154, .25) !important;
}

button.secondary {
    border: 1px solid var(--line) !important;
    border-radius: 13px !important;
    background: #fff !important;
}

.chatbot {
    border: 1px solid var(--line) !important;
    border-radius: 18px !important;
    background: rgba(255,255,255,.7) !important;
}

footer { color: var(--muted); font-size: 12px; margin-top: 24px; }

.weather-card { display:flex; align-items:center; gap:14px; padding:14px 16px; margin:4px 0 18px; border:1px solid var(--line); border-radius:18px; background:linear-gradient(120deg, #fff, var(--weather-accent)); box-shadow:0 8px 18px rgba(65,45,85,.08); }
.weather-icon { font-size:34px; filter:drop-shadow(0 4px 4px rgba(50,30,60,.12)); }
.weather-card small, .look-report small { display:block; color:var(--muted); font-size:10px; font-weight:800; letter-spacing:.12em; }
.weather-card strong { display:block; font-size:14px; letter-spacing:.04em; }
.weather-card span { display:block; color:var(--muted); font-size:12px; margin-top:2px; }
.look-report { margin:12px 0 24px; padding:24px; border-radius:24px; background:linear-gradient(135deg,#fff 0%,#fff8fc 55%,#f1edff 100%); border:1px solid #eadfea; box-shadow:0 16px 34px rgba(65,42,90,.1); }
.report-top { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }
.report-top h2 { margin:6px 0 18px; font-size:clamp(22px,4vw,34px); letter-spacing:-.05em; }
.score-pill { padding:9px 13px; border-radius:99px; background:var(--ink); color:#fff; font-size:11px; white-space:nowrap; }
.score-pill b { color:#ff75b2; font-size:20px; margin-left:6px; }
.score-pill i { color:#aaa; font-style:normal; }
.style-table { width:100%; border-collapse:collapse; font-size:13px; }
.style-table tr { border-top:1px solid var(--line); }
.style-table th { width:30%; padding:14px 10px 14px 0; color:var(--muted); text-align:left; font-size:10px; letter-spacing:.1em; }
.style-table td { padding:14px 0; line-height:1.55; }
.swatches { display:inline-flex; vertical-align:middle; gap:4px; margin-right:8px; }
.swatches i { display:inline-block; width:13px; height:13px; border-radius:50%; background:#ff80b9; border:2px solid #fff; box-shadow:0 0 0 1px #e3d7e5; }
.swatches i:nth-child(2) { background:#ffe9c5; }.swatches i:nth-child(3) { background:#aaa0ff; }
.report-note { margin-top:18px; padding:14px 16px; border-radius:15px; background:rgba(238,233,255,.7); font-size:12px; }
.report-note p { margin:6px 0 0; color:#625d6d; line-height:1.6; }
.empty-report { padding:42px 20px; border:1px dashed #cfc5df; border-radius:20px; color:var(--muted); text-align:center; background:rgba(255,255,255,.55); }

/* glossy Y2K teen-pop skin */
body { background:#b9e9ff; background-image:radial-gradient(#fff 1px, transparent 1px), linear-gradient(135deg,#c8f1ff 0%,#f7d6ef 48%,#d6d2ff 100%); background-size:22px 22px,100% 100%; }
.gradio-container { max-width:1120px !important; padding-top:20px !important; }
.hero { border:3px solid #19151e; border-radius:30px; background:linear-gradient(125deg,#ff8fbd 0%,#ffd4eb 43%,#b6efff 100%); box-shadow:8px 9px 0 #19151e, inset 0 0 0 2px rgba(255,255,255,.6); padding:38px 42px 34px; }
.hero:before { content:'NEW LOOK ☆'; position:absolute; right:34px; bottom:25px; padding:8px 12px; border:2px solid #19151e; border-radius:8px; background:#d7ff66; color:#19151e; font-size:11px; font-weight:900; transform:rotate(-7deg); box-shadow:3px 3px #19151e; }
.hero:after { content:'✦'; color:#fff; text-shadow:4px 5px #ff4f9a; opacity:.85; font-size:100px; }
.hero h1 { color:#fff; text-shadow:4px 4px 0 #ff4f9a, 7px 7px 0 #19151e; -webkit-text-stroke:0; letter-spacing:-.09em; }
.hero p { color:#19151e; font-weight:650; max-width:560px; }
.panel { border:3px solid #19151e !important; border-radius:24px !important; background:#fffdfb !important; box-shadow:6px 7px 0 #19151e !important; backdrop-filter:none; }
.panel h3 { font-size:20px; }
.panel .gr-image, .panel .image-container { border:3px dashed #19151e !important; border-radius:18px !important; background:#e7f8ff !important; }
button.primary { border:2px solid #19151e !important; border-radius:10px !important; background:#ff5ca7 !important; color:#19151e !important; box-shadow:4px 4px 0 #19151e !important; }
button.secondary { border:2px solid #19151e !important; border-radius:10px !important; color:#19151e !important; box-shadow:3px 3px 0 #19151e !important; }
.weather-card { border:2px solid #19151e; border-radius:15px; box-shadow:4px 4px 0 #19151e; }
.look-report { border:3px solid #19151e; border-radius:24px; background:#fffdfb; box-shadow:7px 8px 0 #19151e; padding:24px; }
.report-top h2 { color:#ff4f9a; text-shadow:2px 2px #19151e; }
.sticker { width:62px; height:62px; display:grid; place-content:center; text-align:center; border:2px solid #19151e; border-radius:50%; background:#d8ff5e; color:#19151e; font-size:10px; line-height:.9; transform:rotate(9deg); box-shadow:3px 3px 0 #19151e; }
.sticker b { font-size:16px; }
.gadget-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:4px 0 22px; }
.score-gadget, .palette-gadget, .move-gadget { border:2px solid #19151e; border-radius:15px; background:#d9f6ff; padding:15px; box-shadow:3px 3px 0 #19151e; }
.score-gadget { background:#ffe0ee; }
.score-gadget > span, .gadget-label { color:#5d5263; font-size:10px; font-weight:900; letter-spacing:.12em; }
.score-gadget > b { display:block; font-size:46px; line-height:1; color:#ff4f9a; text-shadow:2px 2px #19151e; margin:8px 0; }
.score-gadget small { color:#6b6571; font-size:10px; }
.meter { height:10px; border:2px solid #19151e; border-radius:99px; background:#fff; overflow:hidden; margin:9px 0 7px; }
.meter i { display:block; height:100%; border-radius:99px; background:#d8ff5e; border-right:2px solid #19151e; }
.section-label { margin:4px 0 9px; }
.chip-list { display:flex; flex-wrap:wrap; gap:7px; margin-top:16px; }
.color-chip { display:flex; align-items:center; gap:6px; padding:7px 9px; border:1.5px solid #19151e; border-radius:99px; background:#fff; font-size:11px; font-weight:750; }
.color-chip i { width:14px; height:14px; border-radius:50%; background:#ff75b2; box-shadow:inset -2px -2px rgba(0,0,0,.12); }
.color-chip:nth-child(2) i { background:#ffd879; }.color-chip:nth-child(3) i { background:#a8a0ff; }.color-chip:nth-child(4) i { background:#d8ff5e; }
.item-gadgets { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:16px; }
.item-gadget { min-height:92px; position:relative; display:flex; flex-direction:column; justify-content:flex-end; padding:12px; border:2px solid #19151e; border-radius:15px; background:#fff; box-shadow:3px 3px 0 #19151e; }
.item-gadget b { position:absolute; right:10px; top:8px; color:#aaa1b1; font-size:10px; }.item-gadget span { font-size:24px; }.item-gadget strong { font-size:12px; line-height:1.2; }
.move-gadget { background:#d8ff5e; margin-top:5px; }.move-gadget strong { display:block; font-size:17px; margin-top:10px; }.move-gadget p { margin:6px 0 0; font-size:12px; }
.report-note { border:2px solid #19151e; border-radius:12px; background:#fff; }
.checkbox-group { gap:8px !important; }
.checkbox-group label { border:2px solid #19151e !important; border-radius:12px !important; background:#fff !important; padding:9px 11px !important; transition:transform .15s, background .15s; }
.checkbox-group label:hover { transform:translateY(-2px) rotate(-1deg); background:#fff0f7 !important; }
.checkbox-group label:has(input:checked) { background:#d8ff5e !important; box-shadow:3px 3px 0 #19151e; }
@media (max-width:700px) { .hero:before { right:18px; bottom:16px; }.gadget-grid,.item-gadgets { grid-template-columns:1fr; } }

@media (max-width: 700px) {
    .gradio-container { padding: 16px 12px 28px !important; }
    .hero { border-radius: 20px; padding: 30px 24px; }
    .panel { padding: 16px !important; }
}
"""

with gr.Blocks(title="Fit-Check", css=custom_css, theme=gr.themes.Soft(primary_hue="pink")) as demo:
    gr.HTML("<div class='hero'><h1>FIT-CHECK ✦</h1><p>오늘의 착장 사진을 보여주면, 귀여운 AI 스타일리스트가 날씨·색 조합·상황별 코디를 체크해줘요.</p></div>")
    with gr.Row():
        with gr.Column(scale=5, elem_classes="panel"):
            gr.Markdown("### 01 / 오늘의 착장")
            image = gr.Image(label="착장 사진", type="filepath", sources=["upload", "webcam"], height=390)
            gr.Markdown("사진은 옷이 잘 보이는 전신 또는 상반신 사진을 추천해요.")
        with gr.Column(scale=5, elem_classes="panel"):
            gr.Markdown("### 02 / 상황 설정")
            with gr.Row():
                region = gr.Dropdown(REGIONS, value="거제", label="날씨 지역")
                situation = gr.Dropdown(SITUATIONS, value="일상복", label="착용 상황")
            question = gr.CheckboxGroup(
                choices=QUESTION_CHOICES,
                label="무엇이 궁금해? (여러 개 선택 가능)",
                info="궁금한 항목을 톡톡 눌러 골라주세요 ✦",
            )
            with gr.Row():
                ask = gr.Button("✦ GO! 스타일 체크", variant="primary")
                clear = gr.Button("대화 지우기")
            error = gr.Markdown()
    weather = gr.HTML(weather_card(REGIONS[0]))
    region.change(weather_card, inputs=region, outputs=weather)
    gr.Markdown("### 03 / FIT-CHECK VISUAL REPORT")
    report = gr.HTML("<div class='empty-report'>사진을 올리면 여기에 비주얼 리포트가 나타나요 ✦</div>")
    chatbot = gr.Chatbot(label="스타일 상담", height=430, elem_classes="panel")
    gr.HTML("<footer>사진 속 옷과 스타일링만 평가해요 · Fit-Check</footer>")

    ask.click(evaluate_look, [image, question, region, situation, chatbot], [chatbot, error, report])
    clear.click(clear_chat, outputs=[chatbot, error, report])


if __name__ == "__main__":
    launch_kwargs = {
        "server_name": os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0"),
        "server_port": int(os.environ.get("GRADIO_SERVER_PORT", os.environ.get("PORT", "7860"))),
        "show_error": True,
    }
    login_user = os.environ.get("FITCHECK_USER")
    login_password = os.environ.get("FITCHECK_PASSWORD")
    if login_user and login_password:
        launch_kwargs["auth"] = (login_user, login_password)
    demo.launch(**launch_kwargs)
