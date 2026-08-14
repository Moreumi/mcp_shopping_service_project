import unittest

from backend import response_writer


class ResponseWriterTests(unittest.TestCase):
    def test_no_products(self):
        self.assertIn("조건에 맞는 상품을 찾지 못했습니다", response_writer.deterministic_answer([]))

    def test_review_summary_stays_under_its_product(self):
        answer = response_writer.deterministic_answer([{
            "title": "Black Running Sneakers", "average_rating": 4.5,
            "review_count": 123, "price": 59.99,
            "review_summary": ["Positive: reliable grip", "Caution: short laces"],
        }], message="검은 운동화 추천")
        self.assertIn("추천 상품\n- Black Running Sneakers", answer)
        self.assertIn("리뷰 요약:\n    - Positive: reliable grip", answer)

    def test_compare_header(self):
        answer = response_writer.deterministic_answer([{"title": "Shoe A"}], intent="compare")
        self.assertIn("비교 상품\n- Shoe A", answer)

    def test_korean_review_summary_is_preferred(self):
        answer = response_writer.deterministic_answer([{
            "title": "Shoe A",
            "review_summary": ["Positive: reliable grip"],
            "review_summary_ko": ["장점: 접지력이 안정적입니다."],
        }], message="운동화 추천")
        self.assertIn("장점: 접지력이 안정적입니다.", answer)
        self.assertNotIn("Positive: reliable grip", answer)

    def test_writer_is_always_deterministic(self):
        self.assertFalse(response_writer.LLM_WRITER_ENABLED)
        answer = response_writer.write_product_answer("추천", [{"title": "Shoe A"}])
        self.assertIn("추천 상품", answer)

    def test_stream_emits_line_chunks(self):
        emitted = []
        with response_writer.answer_stream(emitted.append):
            answer = response_writer.write_product_answer("추천", [{"title": "Shoe A"}])
        self.assertEqual("".join(emitted), answer)


if __name__ == "__main__":
    unittest.main()
