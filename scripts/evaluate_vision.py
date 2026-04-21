import sys, os, time, json, re, base64
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
import numpy as np
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from app.core.config import settings
from app.domains.vision.agent_utils import convert_pptx_to_images, encode_image

# --- 테스트 케이스 ---
# 직접 준비한 이미지/PPT 경로 + 예상 결과 설정
TEST_CASES = [
    {
        "name": "아키텍처 다이어그램",
        "image_path": "scripts/test_images/architecture.png",
        "expected_keywords": ["AWS", "Docker", "FastAPI"],       # 슬라이드에 있어야 할 키워드
        "has_chart": True,                                        # 차트/다이어그램 있는지
        "is_reference_image": False,                              # 참고용 이미지인지
    },
    {
        "name": "그래프 슬라이드",
        "image_path": "scripts/test_images/graph.png",
        "expected_keywords": ["습도", "40", "60"],
        "has_chart": True,
        "is_reference_image": False,
    },
    {
        "name": "참고용 사진",
        "image_path": "scripts/test_images/reference.png",
        "expected_keywords": [],
        "has_chart": False,
        "is_reference_image": True,
    },
]

MODELS = {
    "gemini-2.0-flash": ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=settings.GEMINI_API_KEY),
    "gemini-1.5-flash": ChatGoogleGenerativeAI(model="gemini-3.0-flash", api_key=settings.GEMINI_API_KEY),
    "gpt-4o-mini": ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY),
    "gpt-4o": ChatOpenAI(model="gpt-4o", api_key=settings.OPENAI_API_KEY),
}

PROMPT_TEMPLATE = """다음 슬라이드를 분석해주세요.
1. 텍스트 내용
2. 차트/그래프/도표/아키텍처 다이어그램은 수치, 구조, 연결 관계를 상세히 분석하세요.
3. 참고용 이미지(사진 등)는 회의 맥락과 어떤 맥락으로 연관되는지만 간략히 서술하세요.
4. 이 슬라이드 내용에서 도출되는 핵심 포인트만 작성하세요.
모든 답변은 한국어로 작성하세요.

반드시 아래 JSON 형식으로만 답변하세요:
{{"ocr_text": "...", "chart_description": "...", "key_points": ["...", "..."], "summary": "..."}}"""

def build_message(image_path: str) -> HumanMessage:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    return HumanMessage(content=[
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encode_image(image_bytes)}"}
        },
        {"type": "text", "text": PROMPT_TEMPLATE}
    ])

def evaluate_one(model_name: str, model, case: dict) -> dict:
    message = build_message(case["image_path"])

    start = time.time()
    try:
        result = model.invoke([message])
        latency = time.time() - start
        error = None
    except Exception as e:
        return {"model": model_name, "case": case["name"], "error": str(e)}

    content = result.content
    meta = result.usage_metadata or {}

    # 1. JSON 파싱 성공 여부
    try:
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        parsed = json.loads(json_match.group()) if json_match else None
        json_ok = parsed is not None
    except Exception:
        parsed = None
        json_ok = False

    # 2. 필드 완성도
    required_fields = ["ocr_text", "chart_description", "key_points", "summary"]
    field_score = sum(1 for f in required_fields if parsed and parsed.get(f)) / len(required_fields) if parsed else 0

    # 3. 키워드 포함률 (OCR 정확도)
    ocr_text = parsed.get("ocr_text", "") if parsed else ""
    keyword_hits = sum(1 for kw in case["expected_keywords"] if kw in ocr_text)
    keyword_score = keyword_hits / len(case["expected_keywords"]) if case["expected_keywords"] else None

    # 4. 차트 설명 적절성 - 차트 있는 슬라이드인데 chart_description이 비어있으면 감점
    chart_desc = parsed.get("chart_description", "") if parsed else ""
    chart_score = None
    if case["has_chart"]:
        chart_score = 1.0 if len(chart_desc) > 50 else 0.5 if len(chart_desc) > 10 else 0.0

    # 5. 참고 이미지 처리 적절성 - 참고용 이미지인데 key_points에 슬라이드 무관 내용 없는지
    reference_handled = None
    if case["is_reference_image"]:
        key_points = parsed.get("key_points", []) if parsed else []
        # key_points가 비어있거나 "참고" 언급이 있으면 적절히 처리된 것
        reference_handled = len(key_points) == 0 or any("참고" in kp or "맥락" in kp for kp in key_points)

    # 6. 한국어 답변 여부
    korean_response = bool(re.search(r'[가-힣]', content))

    # 7. key_points 개수
    key_points_count = len(parsed.get("key_points", [])) if parsed else 0

    return {
        "model": model_name,
        "case": case["name"],
        "latency": round(latency, 2),
        "input_tokens": meta.get("input_tokens", 0),
        "output_tokens": meta.get("output_tokens", 0),
        "json_ok": json_ok,
        "field_score": round(field_score, 2),
        "keyword_score": keyword_score,
        "chart_score": chart_score,
        "reference_handled": reference_handled,
        "korean_response": korean_response,
        "key_points_count": key_points_count,
        "ocr_preview": ocr_text[:80],
        "chart_preview": chart_desc[:80],
        "summary_preview": (parsed.get("summary", "")[:80] if parsed else ""),
        "error": None
    }

def visualize(all_results: list[dict]):
    model_names = list(MODELS.keys())
    case_names = [c["name"] for c in TEST_CASES]

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle("Vision 모델 평가 결과", fontsize=16)

    def get_avg(metric, model):
        vals = [r[metric] for r in all_results if r["model"] == model and r.get(metric) is not None and
r.get("error") is None]
        return np.mean(vals) if vals else 0

    # 1. 모델별 평균 응답 시간
    ax = axes[0][0]
    latencies = [get_avg("latency", m) for m in model_names]
    ax.bar(model_names, latencies, color="steelblue")
    ax.set_title("평균 응답 시간 (초)")
    ax.tick_params(axis='x', rotation=20)

    # 2. 모델별 평균 입력 토큰
    ax = axes[0][1]
    input_tokens = [get_avg("input_tokens", m) for m in model_names]
    ax.bar(model_names, input_tokens, color="coral")
    ax.set_title("평균 입력 토큰")
    ax.tick_params(axis='x', rotation=20)

    # 3. 모델별 필드 완성도
    ax = axes[0][2]
    field_scores = [get_avg("field_score", m) for m in model_names]
    ax.bar(model_names, field_scores, color="mediumseagreen")
    ax.set_title("필드 완성도")
    ax.set_ylim(0, 1)
    ax.tick_params(axis='x', rotation=20)

    # 4. 모델별 OCR 키워드 포함률
    ax = axes[1][0]
    keyword_scores = [get_avg("keyword_score", m) for m in model_names]
    ax.bar(model_names, keyword_scores, color="mediumpurple")
    ax.set_title("OCR 키워드 포함률")
    ax.set_ylim(0, 1)
    ax.tick_params(axis='x', rotation=20)

    # 5. 모델별 차트 분석 점수
    ax = axes[1][1]
    chart_scores = [get_avg("chart_score", m) for m in model_names]
    ax.bar(model_names, chart_scores, color="gold")
    ax.set_title("차트 분석 점수")
    ax.set_ylim(0, 1)
    ax.tick_params(axis='x', rotation=20)

    # 6. 종합 레이더 차트
    ax = axes[1][2]
    categories = ["응답속도\n(역수)", "필드완성도", "OCR정확도", "차트분석"]
    x = np.arange(len(categories))
    width = 0.2
    for i, model in enumerate(model_names):
        max_latency = max(get_avg("latency", m) for m in model_names) or 1
        values = [
            1 - get_avg("latency", model) / max_latency,
            get_avg("field_score", model),
            get_avg("keyword_score", model),
            get_avg("chart_score", model),
        ]
        ax.bar(x + i * width, values, width, label=model)
    ax.set_xticks(x + width)
    ax.set_xticklabels(categories, fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_title("종합 비교")
    ax.legend(fontsize=7)

    plt.tight_layout()
    plt.savefig("scripts/vision_eval_result.png", dpi=150)
    print("결과 저장: scripts/vision_eval_result.png")
    plt.show()

    # 정성 평가 출력
    print("\n" + "="*50)
    print("[정성 평가]")
    for r in all_results:
        if r.get("error"):
            print(f"\n[{r['model']} / {r['case']}] 오류: {r['error']}")
            continue
        print(f"\n[{r['model']} / {r['case']}]")
        print(f"  OCR 미리보기: {r['ocr_preview']}")
        print(f"  차트 설명: {r['chart_preview']}")
        print(f"  요약: {r['summary_preview']}")
        print(f"  한국어 응답: {'O' if r['korean_response'] else 'X'}")
        if r['reference_handled'] is not None:
            print(f"  참고이미지 처리: {'O' if r['reference_handled'] else 'X'}")

if __name__ == "__main__":
    print("Vision 모델 평가 시작...")
    all_results = []

    for case in TEST_CASES:
        if not os.path.exists(case["image_path"]):
            print(f"  [SKIP] 이미지 없음: {case['image_path']}")
            continue
        for model_name, model in MODELS.items():
            print(f"  테스트: {case['name']} / {model_name}")
            r = evaluate_one(model_name, model, case)
            all_results.append(r)
            if r.get("error"):
                print(f"    오류: {r['error']}")
            else:
                print(f"    latency: {r['latency']}s, 토큰: {r['input_tokens']}, 필드완성도: {r['field_score']}")

    if all_results:
        visualize(all_results)