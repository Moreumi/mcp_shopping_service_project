import json
import logging
import os
import re
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agent_graph import invoke_shopping_graph_result
from backend.response_writer import LLM_WRITER_ENABLED
from tools.search_products import INDEX_NAME, client as opensearch_client
from backend.reranker import warm_reranker
from backend.query_understanding import warm_query_model
from tools.hybrid_search import embedding_model_status, warm_embedding_model
from tools.amazon_live_recommendations import (
    chat_style_advice,
    recommend as recommend_live_amazon,
    register_click as register_preference_click,
)
from backend.cs.orchestrator import route_request as cs_route_request
from backend.cs.sample_data import (
    orders as cs_orders,
    payments as cs_payments,
    refunds as cs_refunds,
    persist_all as cs_persist_all,
)

CS_WRITE_ROUTES = {"order_cancel", "delivery_address_change"}


load_dotenv()
logger = logging.getLogger("shopping-assistant")
ALLOWED_ORIGINS = [
    value.strip()
    for value in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",")
    if value.strip()
]
DEMO_USER_IDS = {
    value.strip()
    for value in os.getenv("DEMO_USER_IDS", "user_001").split(",")
    if value.strip()
}
STATUS_MESSAGES = {
    "classify": "요청 유형과 쇼핑 조건을 확인했습니다.",
    "context": "선호 정보와 구매 이력을 확인했습니다.",
    "retrieve": "상품 검색과 추천 조건 검증을 마쳤습니다.",
    "respond": "근거가 확인된 추천 답변을 준비했습니다.",
}
_health_cache = {"time": 0.0, "value": None}
_health_lock = Lock()


# ==========================================
# FastAPI 앱
# ==========================================

app = FastAPI(
    title="Shopping Assistant API",
    description="AI Personalized Shopping Assistant",
    version="1.0.0"
)


# ==========================================
# CORS
# 나중에 웹 UI에서 API 호출할 수 있도록 설정
# ==========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def warm_local_dependencies():
    # Do not delay API startup; status is visible while Ollama warms in the background.
    Thread(target=warm_embedding_model, daemon=True).start()
    Thread(target=warm_query_model, daemon=True).start()
    Thread(target=warm_reranker, daemon=True).start()


# ==========================================
# Request / Response 모델
# ==========================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    user_id: str = Field(default="user_001", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    products: list[dict] = Field(default_factory=list)
    orders: list[dict] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    service_status: str = "ok"
    response_mode: str = "search"


class PreferenceRecommendationRequest(BaseModel):
    category: Literal["tops", "bottoms"] = "bottoms"
    answers: dict[str, str]
    priorities: list[str] = Field(default_factory=list, max_length=3)
    user_id: str = Field(default="user_001", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class PreferenceRecommendationResponse(BaseModel):
    query: str
    priorities: list[str]
    products: list[dict] = Field(default_factory=list)


class PreferenceClickRequest(BaseModel):
    asin: str = Field(min_length=1, max_length=32)


class PreferenceClickResponse(BaseModel):
    asin: str
    clicks: int


class StyleChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)


class StyleChatResponse(BaseModel):
    advice: str
    query: str
    products: list[dict] = Field(default_factory=list)


class CsChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    customer_id: int = Field(default=1, ge=1)
    thread_id: str | None = None


class CsChatResponse(BaseModel):
    answer: str
    route: str | None = None


# 고객센터 탭은 기존 쇼핑 챗봇 파이프라인과 완전히 독립적으로 동작한다.
# 상태(State)와 주문/결제/환불 데이터는 미니 프로젝트 원본 설계와 동일하게
# 프로세스 메모리에 보관되는 정적 데이터를 그대로 사용한다.
CS_STATES: dict[str, dict] = {}


def _get_cs_state(thread_id: str) -> dict:
    if thread_id not in CS_STATES:
        CS_STATES[thread_id] = {
            "pending_action": None,
            "candidate_orders": [],
            "selected_order_id": None,
            "last_order_id": None,
            "recent_candidate_orders": [],
            "recent_list_intent": None,
            "history": [],
            "pending_data": {},
        }
    return CS_STATES[thread_id]


# ==========================================
# Health Check
# ==========================================

@app.get("/")
def root():

    return {
        "service": "Shopping Assistant API",
        "status": "running"
    }


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


def _dependency_health():
    now = time.monotonic()
    with _health_lock:
        if _health_cache["value"] and now - _health_cache["time"] < 30:
            return _health_cache["value"]

        catalog = Path("data/amazon_fashion/products.jsonl")
        embedded = Path("data/amazon_fashion/products_embedded.jsonl")
        opensearch = {"available": False, "index": INDEX_NAME}
        try:
            cluster = opensearch_client.cluster.health(request_timeout=5)
            documents = opensearch_client.count(
                index=INDEX_NAME,
                body={"query": {"match_all": {}}},
                request_timeout=5,
            )["count"]
            opensearch.update({
                "available": True,
                "cluster_status": cluster.get("status"),
                "documents": documents,
            })
        except Exception as error:
            opensearch["error"] = type(error).__name__

        value = {
            "overall": "ok" if opensearch["available"] else "degraded",
            "opensearch": opensearch,
            "catalog": {
                "normalized_ready": catalog.exists(),
                "embedded_ready": embedded.exists(),
                "embedded_size_mb": round(embedded.stat().st_size / 1024 / 1024, 1) if embedded.exists() else 0,
            },
            "llm_writer_enabled": LLM_WRITER_ENABLED,
            "embedding_model": embedding_model_status(),
            "checked_at": int(time.time()),
        }
        _health_cache.update({"time": now, "value": value})
        return value


@app.get("/health/details")
def health_details():
    return _dependency_health()


# ==========================================
# Shopping Assistant Chat
# ==========================================

@app.post(
    "/chat",
    response_model=ChatResponse
)
def chat(request: ChatRequest):
    _validate_user(request.user_id)
    started = time.perf_counter()
    try:
        result = invoke_shopping_graph_result(
            request.message,
            request.user_id,
            request.thread_id,
        )

        _log_request(request, result, started)
        return ChatResponse(**result)
    except Exception:
        logger.exception("chat_failed user_id=%s thread_id=%s", request.user_id, request.thread_id)
        raise HTTPException(status_code=500, detail="쇼핑 요청을 처리하지 못했습니다.")


def _validate_user(user_id: str):
    isolated_guest = re.fullmatch(r"demo_[A-Za-z0-9_-]{1,48}", user_id)
    if user_id not in DEMO_USER_IDS and not isolated_guest:
        raise HTTPException(status_code=403, detail="허용되지 않은 데모 사용자입니다.")


@app.post("/personalized/recommendations", response_model=PreferenceRecommendationResponse)
def personalized_recommendations(request: PreferenceRecommendationRequest):
    _validate_user(request.user_id)
    try:
        return recommend_live_amazon(request.category, request.answers, request.priorities)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        logger.warning("live_amazon_not_configured: %s", error)
        raise HTTPException(
            status_code=503,
            detail="실시간 Amazon 추천을 사용하려면 서버의 RAPIDAPI_KEY 설정이 필요합니다.",
        ) from error
    except Exception:
        logger.exception("live_amazon_recommendation_failed")
        raise HTTPException(status_code=502, detail="Amazon 실시간 상품을 불러오지 못했습니다.")


@app.post("/personalized/click", response_model=PreferenceClickResponse)
def personalized_click(request: PreferenceClickRequest):
    try:
        clicks = register_preference_click(request.asin)
        return PreferenceClickResponse(asin=request.asin, clicks=clicks)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/personalized/chat", response_model=StyleChatResponse)
def personalized_chat(request: StyleChatRequest):
    try:
        return chat_style_advice(request.message)
    except RuntimeError as error:
        logger.warning("live_amazon_not_configured: %s", error)
        raise HTTPException(
            status_code=503,
            detail="실시간 Amazon 추천을 사용하려면 서버의 RAPIDAPI_KEY 설정이 필요합니다.",
        ) from error
    except Exception:
        logger.exception("style_chat_failed")
        raise HTTPException(status_code=502, detail="스타일 추천을 불러오지 못했습니다.")


# ==========================================
# Customer Service Chat (독립 파이프라인)
# ==========================================

@app.post("/cs/chat", response_model=CsChatResponse)
def cs_chat(request: CsChatRequest):
    result = _execute_cs_request(request)
    return CsChatResponse(answer=result["response"], route=result.get("route"))


def _execute_cs_request(request: CsChatRequest) -> dict:
    thread_id = request.thread_id or "default"
    state = _get_cs_state(thread_id)
    try:
        result = cs_route_request(
            user_input=request.message,
            customer_id=request.customer_id,
            orders=cs_orders,
            state=state,
            payments=cs_payments,
            refunds=cs_refunds,
        )
        state.setdefault("history", []).append({"role": "user", "content": request.message})
        state["history"].append({"role": "assistant", "content": result["response"]})
        state["history"] = state["history"][-8:]
        if result.get("route") in CS_WRITE_ROUTES:
            cs_persist_all()
        return result
    except Exception:
        logger.exception("cs_chat_failed thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="고객센터 요청을 처리하지 못했습니다.")


@app.post("/cs/chat/stream")
def cs_chat_stream(request: CsChatRequest):
    def events():
        yield sse_event("status", {"message": "문의 내용을 확인하고 있습니다."})
        try:
            result = _execute_cs_request(request)
            answer = result.get("response", "")
            yield sse_event("status", {"message": "확인된 내용을 정리했습니다."})
            for chunk in _answer_chunks(answer, words_per_chunk=2):
                yield sse_event("answer_delta", {"text": chunk})
            yield sse_event("result", {
                "answer": answer,
                "route": result.get("route"),
            })
        except HTTPException:
            yield sse_event("error", {"message": "고객센터 요청을 처리하지 못했습니다."})
        yield sse_event("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _log_request(request: ChatRequest, result: dict, started: float):
    logger.info(
        "chat_completed user_id=%s thread_id=%s products=%d orders=%d latency_ms=%d stages=%s",
        request.user_id,
        request.thread_id,
        len(result.get("products", [])),
        len(result.get("orders", [])),
        round((time.perf_counter() - started) * 1000),
        result.get("timings", {}),
    )


def sse_event(event, data):
    return (
        f"event: {event}\n"
        + "data: "
        + json.dumps(data, ensure_ascii=False, default=str)
        + "\n\n"
    )


def _answer_chunks(answer: str, words_per_chunk: int = 3):
    """Yield small natural-language chunks without adding artificial delay."""
    words = re.findall(r"\S+\s*", answer or "")
    for index in range(0, len(words), words_per_chunk):
        yield "".join(words[index:index + words_per_chunk])


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    _validate_user(request.user_id)

    def events():
        yield sse_event(
            "status",
            {"message": "요청과 쇼핑 조건을 분석하고 있습니다."},
        )

        started = time.perf_counter()
        queue = Queue()
        answer_started = False
        products_emitted = False
        pending_answer = []

        def run_workflow():
            try:
                result = invoke_shopping_graph_result(
                    request.message,
                    request.user_id,
                    request.thread_id,
                    progress_callback=lambda node: queue.put(("status", node)),
                    event_callback=lambda event, payload: queue.put((event, payload)),
                    answer_callback=lambda text: queue.put(("answer_delta", text)),
                )
                queue.put(("result", result))
            except Exception as error:
                queue.put(("error", error))
            finally:
                queue.put(("done", None))

        Thread(target=run_workflow, daemon=True).start()
        while True:
            try:
                event, payload = queue.get(timeout=15)
            except Empty:
                yield ": keep-alive\n\n"
                continue
            if event == "status":
                yield sse_event("status", {"message": STATUS_MESSAGES.get(payload, "처리 중입니다.")})
            elif event == "products":
                yield sse_event("products", payload)
                products_emitted = True
                for text in pending_answer:
                    yield sse_event("answer_delta", {"text": text})
                    answer_started = True
                pending_answer.clear()
            elif event == "answer_delta":
                # Cards are the useful first paint. The writer may emit while
                # the graph's respond node is still running, so briefly buffer
                # its chunks until the product event has entered the stream.
                if products_emitted:
                    answer_started = True
                    yield sse_event("answer_delta", {"text": payload})
                else:
                    pending_answer.append(payload)
            elif event == "result":
                _log_request(request, payload, started)
                # Empty-result and non-search responses legitimately have no
                # product event; release their already-produced answer now.
                for text in pending_answer:
                    yield sse_event("answer_delta", {"text": text})
                    answer_started = True
                pending_answer.clear()
                # Mocked/legacy writers may not emit deltas; keep compatibility.
                if not answer_started:
                    for chunk in _answer_chunks(payload.get("answer", "")):
                        yield sse_event("answer_delta", {"text": chunk})
                    answer_started = True
                yield sse_event("result", payload)
            elif event == "error":
                logger.exception(
                    "chat_stream_failed user_id=%s thread_id=%s",
                    request.user_id,
                    request.thread_id,
                    exc_info=(type(payload), payload, payload.__traceback__),
                )
                yield sse_event("error", {"message": "쇼핑 요청을 처리하지 못했습니다."})
            elif event == "done":
                break

        yield sse_event("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ==========================================
# 직접 실행
# ==========================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "backend.api:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
