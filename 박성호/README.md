# Shopping Assistant

Amazon Fashion 20만 건 카탈로그를 대상으로 상품 검색·개인화 추천·주문/결제 고객센터 기능을 제공하는 데모 프로젝트입니다. 질의 이해와 임베딩은 로컬 Ollama 모델을 사용하고, 검색은 Amazon OpenSearch Service, 고객/주문 데이터는 DynamoDB를 사용합니다.

## 주요 기능

- BM25 + 텍스트 벡터 + 이미지 벡터 하이브리드 검색
- RRF 결합 및 선택적 cross-encoder 재랭킹
- 구매 이력과 사용자 프로필을 반영한 개인화
- 상품 카드 우선 표시와 SSE 답변 스트리밍
- 주문 확인, 결제 확인, 주문 취소, 배송지 변경, 주문 변경 안내
- 최근 주문 목록과 후속 표현(`첫번째`, `그 주문`)을 연결하는 대화 상태 관리
- SQLite 기반 일반 쇼핑 대화 이력 보관(기본 7일)
- 로컬 Qwen 기반 구조화된 질의 이해

## 아키텍처

```text
Browser
  ├─ POST /chat/stream       상품 검색 SSE
  └─ POST /cs/chat/stream    고객센터 SSE
          │
       FastAPI
          │
  ┌───────┼────────────────────────────┐
  │       │                            │
Ollama  OpenSearch                  DynamoDB
Qwen    BM25/Text/Image vectors     profile/orders/CS data
  │
SQLite (일반 쇼핑 대화 이력)
```

상세 이미지는 [docs/shopping-assistant-architecture.png](docs/shopping-assistant-architecture.png)를 참고하세요.

## 기술 스택

- Python 3.12, FastAPI, LangGraph, Pydantic
- Ollama `qwen3:4b`, `nomic-embed-text`
- Amazon OpenSearch Service
- Amazon DynamoDB
- SigLIP, PyTorch, Transformers
- HTML, CSS, JavaScript, SSE
- SQLite

## 디렉터리

```text
backend/                 FastAPI, 검색 워크플로, 고객센터
backend/cs/              고객센터 상태 머신과 정책
frontend/                정적 웹 UI
tools/                   OpenSearch·DynamoDB·임베딩 도구
scripts/                 데이터 구축, 색인, 평가, 데모 실행
tests/                   단위·회귀·20턴 대화 공격 테스트
docs/                    아키텍처 이미지
iam/                     최소 권한 IAM 정책 예시
```

`data/amazon_fashion/`의 원본·임베딩 카탈로그는 수 GB이므로 Git에 포함하지 않습니다.

## 사전 요구사항

- Windows PowerShell
- Python 3.12
- [Ollama](https://ollama.com/)
- AWS 자격 증명(DynamoDB 및 OpenSearch 접근 권한)
- 준비된 OpenSearch 인덱스

모델을 준비합니다.

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

## 설치

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`에 실제 연결 정보를 입력합니다. `.env`와 데이터 파일은 Git에서 제외됩니다.

```dotenv
OPENSEARCH_HOST=https://your-domain.us-east-1.es.amazonaws.com
OPENSEARCH_USERNAME=your-user
OPENSEARCH_PASSWORD=your-password
OPENSEARCH_INDEX=products-amazon-fashion-v2

AWS_REGION=us-east-1
USERS_TABLE=shopping-users
ORDERS_TABLE=shopping-orders
CS_ORDERS_TABLE=customer-service-demo-orders
CS_PAYMENTS_TABLE=customer-service-demo-payments
CS_REFUNDS_TABLE=customer-service-demo-refunds

OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_QUERY_MODEL=qwen3:4b
OLLAMA_QUERY_KEEP_ALIVE=2h
OLLAMA_EMBED_KEEP_ALIVE=2h

ALLOWED_ORIGINS=http://127.0.0.1:5500,http://localhost:5500
DEMO_USER_IDS=user_001
```

`Domain_Endpoint` 같은 별도 평문 파일은 사용하지 않습니다. OpenSearch 주소는 반드시 환경변수로 설정합니다.

## 실행

AWS 자격 증명이 설정된 PowerShell에서 실행합니다.

```powershell
.\scripts\start_demo.ps1
```

기본 접속 주소:

- 프런트엔드: `http://127.0.0.1:5500`
- API 문서: `http://127.0.0.1:8000/docs`
- 상세 상태: `http://127.0.0.1:8000/health/details`

종료:

```powershell
.\scripts\stop_demo.ps1
```

수동 API 실행:

```powershell
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

## API

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/chat` | 일반 쇼핑 JSON 응답 |
| `POST` | `/chat/stream` | 상품 카드와 답변 SSE |
| `POST` | `/cs/chat` | 고객센터 JSON 응답 |
| `POST` | `/cs/chat/stream` | 고객센터 답변 SSE |
| `POST` | `/personalized/recommendations` | 선택적 실시간 Amazon 추천 |
| `GET` | `/health` | 기본 상태 |
| `GET` | `/health/details` | OpenSearch·카탈로그·임베딩 상태 |

SSE 이벤트는 `status`, `products`(상품 검색), `answer_delta`, `result`, `error`, `done` 순으로 전달됩니다.

## 데이터 구축

원본 Amazon Reviews 2023 데이터는 저장소에 포함되지 않습니다.

```powershell
python -m scripts.download_amazon_fashion
python -m scripts.build_amazon_fashion --limit 200000 --candidate-limit 260000 --min-reviews 3
python -m scripts.embed_catalog --input data\amazon_fashion\products.jsonl --output data\amazon_fashion\products_embedded.jsonl --batch-size 128
python -m scripts.create_catalog_index --index products-amazon-fashion-v2
python -m scripts.upload_catalog --input data\amazon_fashion\products_embedded.jsonl --index products-amazon-fashion-v2 --chunk-size 50 --thread-count 1
```

이미지 임베딩은 선택 사항입니다.

```powershell
python -m scripts.embed_catalog_images_siglip --apply
```

리뷰 요약 사전 번역:

```powershell
python -m scripts.translate_review_summaries
```

## 고객센터 데이터

고객센터 데모 테이블은 일반 쇼핑 주문 테이블과 분리합니다. 샘플 데이터 입력은 실제 DynamoDB를 변경하므로 대상 AWS 계정과 테이블명을 확인한 뒤 실행하세요.

```powershell
python -m scripts.seed_customer_service_demo_data
```

고객센터 쓰기 작업은 최종 확인 이후에만 실행됩니다. 테스트는 복사된 인메모리 데이터로 수행합니다.

## 테스트

AWS·OpenSearch 연동 테스트는 올바른 자격 증명과 외부 서비스가 필요합니다.

```powershell
python -m unittest discover -s tests -v
```

핵심 로컬 회귀 테스트:

```powershell
python -m unittest tests.test_cs_adversarial_session tests.test_cs_topic_switch tests.test_cs_explicit_order tests.test_cs_recent_orders
```

검색 품질 평가:

```powershell
python -m scripts.evaluate_search
python -m scripts.evaluate_demo_scenarios
python -m scripts.verify_v2_readiness
```

## 보안 및 공개 전 확인

- `.env`, AWS 키, OpenSearch 주소/비밀번호를 커밋하지 않습니다.
- `data/`, 로그, SQLite DB, 체크포인트, 모델 캐시를 커밋하지 않습니다.
- IAM 정책은 실제 리소스 ARN에 맞게 최소 권한으로 수정합니다.
- 데모 주문 취소·배송지 변경은 DynamoDB 데이터를 변경합니다.
- 선택 기능인 RapidAPI를 사용할 때만 `RAPIDAPI_KEY`를 설정합니다.

## 데모 운영

발표 전 점검 및 복구 절차는 [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md)를 참고하세요.
