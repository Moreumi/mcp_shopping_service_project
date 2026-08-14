# Shopping Assistant Demo Runbook

## 1. Start and verify

```powershell
.\scripts\start_demo.ps1
```

Open `http://127.0.0.1:5500`, then open **System Status** and confirm:

- API: healthy
- OpenSearch: green, 200,000 documents (catalog size grows over time — confirm the
  current count matches `.env`'s `OPENSEARCH_INDEX`, not this fixed number)
- Active index: `products-amazon-fashion-v2`
- Embedding: `nomic-embed-text`, ready
- LLM writer: matches `.env`'s `LLM_WRITER_ENABLED` (currently `true` — the assistant
  writes one grounded opening sentence per answer; product/review details are always
  assembled by code regardless of this setting)

If preflight reports `ready: false`, do not start the presentation. Check Ollama,
OpenSearch and DynamoDB first.

## 2. Three-minute presentation flow

### Search and grounding

Ask: `검은색 여성 운동화 추천해줘`

Show that exactly three catalog products are returned. Point out that category,
audience and color are enforced in code and that price, rating and review fields
are omitted when unavailable.

### Follow-up comparison

Ask: `추천 상품들의 차이점을 비교해줘`

Show the comparison table. The same three product IDs must be retained from the
previous response; no second retrieval or tool-calling loop is required.

### Personal context

Ask: `최근 주문 내역 보여줘`

Show the three DynamoDB orders. Explain that purchased product IDs are removed
from later recommendations by deterministic policy code.

## 3. Optional safety demonstration

Ask for an unsupported exact price or size. The assistant must not invent it.
Comfort may be mentioned only when `bullet_points` or `description` contains
direct evidence.

## 4. Final pre-demo verification

```powershell
.\.venv\Scripts\python.exe -m scripts.preflight_demo
.\.venv\Scripts\python.exe -m scripts.evaluate_search
.\.venv\Scripts\python.exe -m scripts.evaluate_demo_scenarios
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Expected results:

- Preflight: `ready: true`
- Search evaluation: all cases pass
- Demo evaluation: 5/5, pass rate 1.0
- Unit tests: all pass

## 5. Recovery during presentation

- Slow first search: wait for Embedding status to become ready and retry once.
- OpenSearch unavailable: show System Status; do not claim generated products.
- DynamoDB unavailable: continue with catalog search and comparison.
- Browser stale: hard-refresh the page; keep the API process running.

## 6. Cost cleanup guardrail

The active endpoint contains `shopping-assistant2`. Never delete that domain.
Only the legacy domain named exactly `shopping-assistant` is a cleanup candidate,
and it must be checked in both `us-east-1` and `ap-northeast-2` before deletion.

## 7. Stop the local demo

```powershell
.\scripts\stop_demo.ps1
```

The script only stops the saved API and frontend PIDs when their command lines
still match this demo. It will not terminate an unrelated process that reused a PID.
