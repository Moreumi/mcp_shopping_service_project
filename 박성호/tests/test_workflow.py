import unittest
from unittest.mock import patch
from uuid import uuid4

from backend import agent_graph
from backend.policies import (
    classify_intent,
    detect_requested_audience,
    detect_requested_category,
    detect_requested_color,
    detect_requested_product_kind,
    filter_products,
    has_comfort_evidence,
    rank_products,
    safe_product,
    expand_search_query,
)
from backend.response_writer import SYSTEM_PROMPT, compact_products
from backend.query_understanding import SearchIntent


class PolicyTests(unittest.TestCase):
    def test_safe_product_builds_amazon_url_from_asin(self):
        product = safe_product({"product_id": "B012345678", "title": "Shoe"})
        self.assertEqual(product["amazon_url"], "https://www.amazon.com/dp/B012345678")

    def test_safe_product_does_not_link_invalid_product_id(self):
        product = safe_product({"product_id": "internal-1", "title": "Shoe"})
        self.assertNotIn("amazon_url", product)

    def test_korean_query_expansion_targets_english_catalog(self):
        expanded = expand_search_query("검은 여성 출근용 운동화")
        for term in ("black", "women", "office", "sneakers"):
            self.assertIn(term, expanded.lower())

    def test_code_router_uses_no_model(self):
        self.assertEqual(classify_intent("최근 주문 내역 보여줘"), "orders")
        self.assertEqual(classify_intent("이 상품들 비교해줘", True), "compare")
        self.assertEqual(classify_intent("검은 신발 추천해줘"), "search")

    def test_profile_question_uses_profile_intent(self):
        self.assertEqual(classify_intent("내 취향이 뭐야?"), "profile")

    def test_requested_filters_are_deterministic(self):
        message = "검은 여성 신발 추천해줘"
        self.assertEqual(detect_requested_color(message), "Black")
        self.assertEqual(detect_requested_audience(message), "Women")
        self.assertEqual(detect_requested_category(message), "Shoes")

    def test_requested_shoe_kind_is_deterministic(self):
        self.assertEqual(detect_requested_product_kind("여성 운동화 추천"), "Sneakers")
        self.assertEqual(detect_requested_product_kind("남성 출근 구두"), "FormalShoes")
        self.assertEqual(detect_requested_product_kind("가벼운 여성 샌들"), "Sandals")
        self.assertEqual(detect_requested_product_kind("겨울 여성 코트"), "Coats")
        self.assertEqual(detect_requested_product_kind("여름용 선글라스"), "Sunglasses")

    def test_sneaker_filter_removes_work_shoes(self):
        products = [
            {"product_id": "run", "title": "Women's Running Shoes", "category": "Shoes"},
            {"product_id": "work", "title": "Steel Toe Work Shoes", "category": "Shoes"},
        ]
        result = filter_products(products, category="Shoes", requested_kind="Sneakers")
        self.assertEqual([item["product_id"] for item in result], ["run"])

    def test_sneaker_filter_removes_care_products(self):
        products = [
            {"product_id": "shoe", "title": "Men's Running Sneakers", "category": "Shoes"},
            {"product_id": "care", "title": "Ultimate Sneaker Care Pack", "category": "Shoes"},
        ]
        result = filter_products(products, category="Shoes", requested_kind="Sneakers")
        self.assertEqual([item["product_id"] for item in result], ["shoe"])

    def test_purchased_and_wrong_color_products_are_removed(self):
        products = [
            {"product_id": "bought", "title": "Black Women's Shoe", "color": "Black"},
            {"product_id": "red", "title": "Red Women's Shoe", "color": "Red"},
            {"product_id": "ok", "title": "Black Women's Shoe", "color": "Black"},
        ]
        result = filter_products(
            products,
            exclude_product_ids=["bought"],
            audience="Women",
            category="Shoes",
            required_color="Black",
        )
        self.assertEqual([item["product_id"] for item in result], ["ok"])

    def test_visual_color_match_overrides_unreliable_catalog_color(self):
        product = {
            "product_id": "visual-red",
            "title": "Men's Running Shoes",
            "category": "Shoes",
            "audience": "Men",
            "color": "Gray",
            "visual_color_match": True,
        }
        result = filter_products(
            [product], audience="Men", category="Shoes", required_color="Red", requested_kind="Sneakers"
        )
        self.assertEqual([item["product_id"] for item in result], ["visual-red"])

    def test_comfort_requires_direct_evidence(self):
        self.assertTrue(has_comfort_evidence({"bullet_points": ["Cushioned footbed"]}))
        self.assertFalse(has_comfort_evidence({"title": "Daily Shoe", "description": "Classic style"}))

    def test_deterministic_writer_and_compact_context(self):
        self.assertIn("Deterministic", SYSTEM_PROMPT)
        self.assertIn("no LLM", SYSTEM_PROMPT)
        compact = compact_products([
            {"title": "Shoe", "description": "x" * 1000,
             "bullet_points": ["Soft lining"], "review_summary": "Verified summary"}
        ])[0]
        self.assertEqual(compact["title"], "Shoe")
        self.assertEqual(compact["review_summary"], "Verified summary")
        self.assertNotIn("description", compact)
        self.assertNotIn("bullet_points", compact)

    def test_code_ranking_removes_duplicate_titles(self):
        products = [
            {"product_id": "a", "title": "Same Shoe", "brand": "A", "average_rating": 2.0, "review_count": 4},
            {"product_id": "b", "title": "Same Shoe", "brand": "A", "average_rating": 5.0, "review_count": 100},
            {"product_id": "c", "title": "Other Shoe", "brand": "B", "average_rating": 4.5, "review_count": 50},
        ]
        ranked = rank_products(products, 3)
        self.assertEqual(len(ranked), 2)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        agent_graph.CONTEXT_CACHE.clear()
        agent_graph.SEARCH_CACHE.clear()

    def test_customer_context_cache_avoids_duplicate_dynamodb_reads(self):
        with patch.object(
            agent_graph, "get_user_profile", return_value={"found": True, "user": {}}
        ) as profile, patch.object(
            agent_graph, "get_orders", return_value={"orders": [{"product_id": "old"}]}
        ) as orders:
            first = agent_graph.load_context_node({"intent": "search", "user_id": "user_001"})
            second = agent_graph.load_context_node({"intent": "search", "user_id": "user_001"})
        self.assertEqual(first, second)
        profile.assert_called_once()
        orders.assert_called_once()

    def test_search_cache_avoids_duplicate_opensearch_reads(self):
        product = {"product_id": "p1", "title": "Black Women's Shoe", "color": "Black", "average_rating": 4.5}
        state = {
            "intent": "search", "message": "검은 여성 신발 추천",
            "profile": {}, "purchased_ids": [], "products": [], "retrieval_attempt": 0,
        }
        with patch.object(agent_graph, "compile_search_intent", return_value=self.SEARCH_INTENT), patch.object(
            agent_graph, "hybrid_search", return_value=[product]
        ) as search:
            agent_graph.retrieve_node(state)
            agent_graph.retrieve_node(state)
        search.assert_called_once()

    def test_product_kind_low_recall_skips_near_duplicate_retry(self):
        self.assertEqual(agent_graph.route_after_quality({
            "intent": "search",
            "products": [{"product_id": "p1"}],
            "search_available": True,
            "retrieval_attempt": 1,
            "requested_kind": "Sneakers",
        }), "respond")

    def test_order_answer_is_explicit_bulleted_and_uses_no_llm(self):
        orders = {
            "orders": [{
                "product_id": "B087SWVC6L",
                "title": "Men's Cambridge Sneaker",
                "purchase_date": "2026-08-03",
                "price": 66.48,
                "status": "Delivered",
            }]
        }
        with patch.object(agent_graph, "get_orders", return_value=orders), patch.object(
            agent_graph, "write_product_answer"
        ) as writer:
            result = agent_graph.invoke_shopping_graph_result(
                "내 주문 내역 보여줘", "user_001", str(uuid4())
            )
        writer.assert_not_called()
        self.assertIn("- 2026-08-03 · Men's Cambridge Sneaker · $66.48 · 배송 완료", result["answer"])

    def test_profile_answer_is_bulleted_and_uses_no_search_or_llm(self):
        profile = {
            "found": True,
            "user": {
                "preferred_styles": ["Minimal", "Sporty casual"],
                "preferred_colors": ["Black", "Navy"],
                "budget_range": "$40-$120",
            },
        }
        with patch.object(agent_graph, "get_user_profile", return_value=profile), patch.object(
            agent_graph, "hybrid_search"
        ) as search, patch.object(agent_graph, "write_product_answer") as writer:
            result = agent_graph.invoke_shopping_graph_result(
                "내 취향이 뭐야?", "user_001", str(uuid4())
            )
        search.assert_not_called()
        writer.assert_not_called()
        self.assertIn("- 선호 스타일: Minimal, Sporty casual", result["answer"])
        self.assertIn("- 선호 색상: Black, Navy", result["answer"])

    def test_isolated_guest_does_not_read_customer_tables(self):
        with patch.object(agent_graph, "get_user_profile") as profile, patch.object(
            agent_graph, "get_orders"
        ) as orders:
            result = agent_graph.load_context_node({
                "intent": "search", "user_id": "demo_guest-2"
            })
        profile.assert_not_called()
        orders.assert_not_called()
        self.assertEqual(result["purchased_ids"], [])

    SEARCH_INTENT = SearchIntent(
        semantic_query="women black shoes",
        visual_query="women black shoes",
        product_terms=["black", "shoes"],
        category="Shoes",
        audience="Women",
        color="Black",
    )
    def test_compare_uses_compare_specific_grounded_intro(self):
        answer = agent_graph.write_product_answer(
            "비교해줘",
            [{"product_id": "p1", "title": "Shoe", "average_rating": 4.5}],
            "compare",
        )
        self.assertIn("비교", answer)

    def test_low_recall_search_retries_once_and_writes_once(self):
        product = {"product_id": "p1", "title": "Black Women's Shoe", "color": "Black", "average_rating": 4.5}
        with patch.object(agent_graph, "compile_search_intent", return_value=self.SEARCH_INTENT), patch.object(agent_graph, "get_user_profile", return_value={"found": True, "user": {}}), patch.object(
            agent_graph, "get_orders", return_value={"orders": [{"product_id": "old"}]}
        ), patch.object(agent_graph, "hybrid_search", return_value=[product]) as search, patch.object(
            agent_graph, "write_product_answer", return_value="추천 답변"
        ) as writer:
            result = agent_graph.invoke_shopping_graph_result(
                "검은 여성 신발 추천해줘", "user_001", str(uuid4())
            )

        self.assertEqual(search.call_count, 2)
        writer.assert_called_once()
        self.assertEqual(result["answer"], "추천 답변")
        self.assertEqual(result["products"][0]["product_id"], "p1")
        self.assertIn("old", search.call_args.kwargs["exclude_product_ids"])

    def test_profile_preferences_are_a_small_ranking_boost(self):
        products = [
            {"product_id": str(index), "title": f"Shoe {index}", "brand": "Favorite" if index == 1 else "Other", "review_count": 10, "average_rating": 4.0}
            for index in range(10)
        ]
        ranked = rank_products(products, 3, profile={"user": {"preferred_brands": ["Favorite"]}})
        self.assertEqual(ranked[0]["product_id"], "1")

    def test_orders_use_no_llm(self):
        with patch.object(
            agent_graph,
            "get_orders",
            return_value={"orders": [{"product_id": "p1", "purchase_date": "2026-01-01"}]},
        ), patch.object(agent_graph, "write_product_answer") as writer:
            result = agent_graph.invoke_shopping_graph_result(
                "최근 주문 내역 보여줘", "user_001", str(uuid4())
            )
        writer.assert_not_called()
        self.assertIn("p1", result["answer"])
        self.assertEqual(len(result["orders"]), 1)

    def test_total_search_outage_returns_safe_empty_result(self):
        with patch.object(agent_graph, "compile_search_intent", return_value=self.SEARCH_INTENT), patch.object(agent_graph, "get_user_profile", return_value={}), patch.object(
            agent_graph, "get_orders", return_value={"orders": []}
        ), patch.object(agent_graph, "hybrid_search", side_effect=RuntimeError("vector down")), patch.object(
            agent_graph, "search_products", side_effect=RuntimeError("keyword down")
        ):
            result = agent_graph.invoke_shopping_graph_result(
                "여성 운동화 추천", "user_001", str(uuid4())
            )
        self.assertEqual(result["products"], [])
        self.assertEqual(result["service_status"], "search_unavailable")
        self.assertIn("검색 서비스", result["answer"])
        self.assertNotIn("vector down", result["answer"])
        self.assertNotIn("keyword down", result["answer"])

    def test_followup_reuses_previous_products_without_search(self):
        thread_id = str(uuid4())
        product = {"product_id": "p1", "title": "Black Women's Shoe", "color": "Black", "average_rating": 4.5}
        with patch.object(agent_graph, "compile_search_intent", return_value=self.SEARCH_INTENT), patch.object(agent_graph, "get_user_profile", return_value={}), patch.object(
            agent_graph, "get_orders", return_value={"orders": []}
        ), patch.object(agent_graph, "hybrid_search", return_value=[product]), patch.object(
            agent_graph, "write_product_answer", return_value="첫 답변"
        ):
            agent_graph.invoke_shopping_graph_result("신발 추천", "user_001", thread_id)

        with patch.object(agent_graph, "hybrid_search") as search, patch.object(
            agent_graph, "write_product_answer", return_value="비교 답변"
        ):
            result = agent_graph.invoke_shopping_graph_result("이 상품 비교해줘", "user_001", thread_id)
        search.assert_not_called()
        self.assertEqual(result["products"][0]["product_id"], "p1")


if __name__ == "__main__":
    unittest.main()
