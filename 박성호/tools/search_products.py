import os
from functools import lru_cache

from dotenv import load_dotenv
from opensearchpy import OpenSearch


# =====================================
# OpenSearch 연결
# =====================================

load_dotenv()


def resolve_opensearch_host():
    configured = os.getenv("OPENSEARCH_HOST", "").strip()

    if configured and "your-domain" not in configured and "xxxxx" not in configured:
        return configured

    raise RuntimeError("Set OPENSEARCH_HOST in .env.")


host = resolve_opensearch_host().removeprefix("https://").rstrip("/")
port = 443

username = os.environ["OPENSEARCH_USERNAME"]
password = os.environ["OPENSEARCH_PASSWORD"]
INDEX_NAME = os.getenv("OPENSEARCH_INDEX", "products-amazon-fashion-v2")


client = OpenSearch(
    hosts=[
        {
            "host": host,
            "port": port
        }
    ],
    http_auth=(username, password),
    use_ssl=True,
    verify_certs=True,
    timeout=60,
    max_retries=3,
    retry_on_timeout=True,
)


@lru_cache(maxsize=1)
def image_embedding_count() -> int:
    """Return the exact unique visual-vector coverage for this API process."""
    response = client.count(
        index=INDEX_NAME,
        body={"query": {"exists": {"field": "image_embedding"}}},
    )
    return int(response.get("count") or 0)


@lru_cache(maxsize=1)
def total_product_count() -> int:
    """Catalog size for this API process - avoids hardcoding a number that
    goes stale the next time the catalog is expanded."""
    response = client.count(index=INDEX_NAME, body={"query": {"match_all": {}}})
    return int(response.get("count") or 0)


# =====================================
# 상품 검색
# =====================================

def search_products(
    query: str = "",
    size: int = 5,
    category: str = None,
    audience: str = None,
    required_color: str = None,
    exclude_product_ids=None,
    exclude_kids: bool = False
):

    if exclude_product_ids is None:
        exclude_product_ids = []

    must_queries = []
    filter_queries = []
    must_not_queries = []


    # =================================
    # 1. 키워드 / 유사성 검색
    # =================================

    if query:

        must_queries.append(
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title^10",
                        "style^7",
                        "category^6",
                        "product_type^5",
                        "bullet_points^3",
                        "description^2",
                        "brand^2"
                    ]
                }
            }
        )


    # =================================
    # 2. 카테고리 HARD FILTER
    # =================================

    if category:

        filter_queries.append(
            {
                "match": {
                    "category": {
                        "query": category,
                        "operator": "and"
                    }
                }
            }
        )


    # =================================
    # 3. 대상 HARD FILTER
    # Women / Men
    # =================================

    if audience:
        audience_title = "women" if audience == "Women" else "men"
        filter_queries.append({
            "bool": {
                "should": [
                    {"term": {"audience": audience}},
                    {"term": {"audience": "Unisex"}},
                    {"match": {"title": audience_title}},
                    {"match": {"category": audience_title}},
                ],
                "minimum_should_match": 1,
            }
        })


    # =================================
    # 4. 색상 HARD FILTER
    # =================================

    if required_color:

        filter_queries.append(
            {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "color": {
                                    "query": required_color,
                                    "operator": "and"
                                }
                            }
                        },
                        {
                            "match": {
                                "title": {
                                    "query": required_color,
                                    "operator": "and"
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            }
        )


    # =================================
    # 5. 이미 구매한 상품 제외
    # =================================

    if exclude_product_ids:

        must_not_queries.append(
            {
                "ids": {
                    "values": exclude_product_ids
                }
            }
        )


    # =================================
    # 6. 아동용 제외
    # =================================

    if exclude_kids:

        kids_terms = [
            "girl",
            "girls",
            "boy",
            "boys",
            "kid",
            "kids",
            "little kid",
            "toddler"
        ]

        for term in kids_terms:

            must_not_queries.append(
                {
                    "match_phrase": {
                        "title": term
                    }
                }
            )


    # =================================
    # 7. Bool Query 생성
    # =================================

    bool_query = {}

    if must_queries:
        bool_query["must"] = must_queries

    if filter_queries:
        bool_query["filter"] = filter_queries

    if must_not_queries:
        bool_query["must_not"] = must_not_queries


    if bool_query:

        search_body = {
            "size": size,
            "query": {
                "bool": bool_query
            }
        }

    else:

        search_body = {
            "size": size,
            "query": {
                "match_all": {}
            }
        }


    # =================================
    # 8. 검색 실행
    # =================================

    response = client.search(
        index=INDEX_NAME,
        body=search_body
    )


    # =================================
    # 9. 결과 정리
    # =================================

    products = []

    for hit in response["hits"]["hits"]:

        source = hit["_source"]

        products.append(
            {
                "product_id": source.get("product_id"),
                "title": source.get("title"),
                "brand": source.get("brand"),
                "product_type": source.get("product_type"),
                "category": source.get("category"),
                "audience": source.get("audience"),
                "bullet_points": source.get("bullet_points"),
                "color": source.get("color"),
                "material": source.get("material"),
                "style": source.get("style"),
                "description": source.get("description"),
                "price": source.get("price"),
                "average_rating": source.get("average_rating"),
                "review_count": source.get("review_count"),
                "verified_review_count": source.get("verified_review_count"),
                "image_url": source.get("image_url"),
                "positive_review_evidence": source.get("positive_review_evidence"),
                "negative_review_evidence": source.get("negative_review_evidence"),
                "score": hit["_score"]
            }
        )

    return products
