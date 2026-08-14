import argparse

from tools.search_products import client


def index_body():
    return {
        "settings": {
            "index": {
                "knn": True,
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "-1",
            }
        },
        "mappings": {
            "dynamic": False,
            "properties": {
                "product_id": {"type": "keyword"},
                "dataset": {"type": "keyword"},
                "main_category": {"type": "keyword"},
                "title": {"type": "text"},
                "brand": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                "product_type": {"type": "text"},
                "category": {"type": "text"},
                "categories": {"type": "keyword"},
                "audience": {"type": "keyword"},
                "bullet_points": {"type": "text"},
                "description": {"type": "text"},
                "color": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                "material": {"type": "text"},
                "style": {"type": "text"},
                "price": {"type": "float"},
                "average_rating": {"type": "half_float"},
                "review_count": {"type": "integer"},
                "verified_review_count": {"type": "integer"},
                "image_url": {"type": "keyword", "index": False},
                "positive_review_evidence": {"type": "object", "enabled": False},
                "negative_review_evidence": {"type": "object", "enabled": False},
                "review_summary": {"type": "text", "index": False},
                "review_summary_ko": {"type": "text", "index": False},
                "review_translation_source_hash": {"type": "keyword"},
                "review_translation_model": {"type": "keyword"},
                "details": {"type": "object", "enabled": False},
                "bought_together": {"type": "keyword"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 768,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 128, "m": 16},
                    },
                },
                "review_embedding": {
                    "type": "knn_vector",
                    "dimension": 768,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 128, "m": 16},
                    },
                },
            },
        },
    }


def create_index(index_name):
    if client.indices.exists(index=index_name, request_timeout=120):
        raise RuntimeError(f"Index already exists: {index_name}")

    return client.indices.create(
        index=index_name,
        body=index_body(),
        request_timeout=120,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="products-amazon-fashion-v2")
    args = parser.parse_args()
    print(create_index(args.index))
