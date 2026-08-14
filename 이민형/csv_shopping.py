import html
import re
import time
import pandas as pd
from playwright.sync_api import sync_playwright


def get_exact_krw_price(page):
    """아마존 표기 통화(₩/$)를 자동 감지하여 정확한 KRW 가격 반환"""
    price_selectors = [
        "#corePriceDisplay_desktop_feature_div .priceToPay span.a-offscreen",
        "#corePrice_desktop span.a-price.aok-align-center span.a-offscreen",
        "#apex_desktop .priceToPay span.a-offscreen",
        "#corePriceInsideBuyBox_feature_div .a-price span.a-offscreen",
        "#price_inside_buybox",
        ".apexPriceToPay span.a-offscreen",
        "span.a-price span.a-offscreen",
    ]

    for sel in price_selectors:
        elements = page.query_selector_all(sel)
        for el in elements:
            parent_class = (
                el.evaluate("el => el.parentElement.className") if el else ""
            )
            if "a-text-price" in parent_class:
                continue

            raw_text = el.text_content().strip()
            if not raw_text:
                continue

            # 1. 원화(₩, KRW, 원) 표기 시 숫지만 추출
            if "₩" in raw_text or "KRW" in raw_text or "원" in raw_text:
                digits = re.sub(r"[^\d]", "", raw_text)
                if digits:
                    val = int(digits)
                    if val > 0:
                        return f"{val:,}원", val

            # 2. 달러($) 표기 시 1,350원 환율 적용
            if "$" in raw_text:
                clean_usd = raw_text.replace("$", "").replace(",", "").strip()
                usd_match = re.search(r"\d+\.?\d*", clean_usd)
                if usd_match:
                    try:
                        val_usd = float(usd_match.group(0))
                        if val_usd > 0:
                            krw_val = int(val_usd * 1350)
                            return f"{krw_val:,}원", krw_val
                    except ValueError:
                        pass

            # 3. 통화 기호 없는 숫자 자동 구분
            clean_num = re.sub(r"[^\d.]", "", raw_text)
            if clean_num:
                try:
                    val = float(clean_num)
                    if val > 1000:
                        return f"{int(val):,}원", int(val)
                    elif val > 0:
                        krw_val = int(val * 1350)
                        return f"{krw_val:,}원", krw_val
                except ValueError:
                    pass

    return "정보 없음", 0


def extract_colors(page):
    """실제 색상 옵션 수집"""
    color_els = page.query_selector_all(
        "#variation_color_name li, div[id*='inline-twister-row-color'] li"
    )
    colors = []

    for c_el in color_els:
        img = c_el.query_selector("img")
        c_text = (
            img.get_attribute("alt")
            if img
            else (
                c_el.get_attribute("title")
                or c_el.get_attribute("aria-label")
                or ""
            )
        )
        c_clean = (
            c_text.replace("Click to select", "")
            .replace("선택하려면 클릭", "")
            .replace("/*", "")
            .strip()
        )
        if (
            c_clean
            and not c_clean.startswith("/*")
            and len(c_clean) < 30
            and c_clean not in colors
        ):
            colors.append(c_clean)

    if not colors:
        selected_color_el = page.query_selector(
            "#variation_color_name .selection"
        )
        if selected_color_el:
            sel_text = selected_color_el.text_content().strip()
            if sel_text and not sel_text.startswith("/*"):
                colors.append(sel_text)

    return ", ".join(colors[:5]) if colors else "정보 없음"


def extract_sizes_precise(page):
    """화살표, 숫자, 안내문구 등 노이즈를 필터링한 정밀 사이즈 옵션 수집"""
    sizes = []

    # UI 노이즈 필터링 키워드
    ignore_keywords = [
        "←",
        "→",
        "1",
        "2",
        "3",
        "4",
        "5",
        "사용 가능한 옵션 보기",
        "select",
        "size chart",
        "옵션 선택",
        "fit guide",
        "see options",
    ]

    # 1. 버튼 및 스왓치 형태
    size_btn_els = page.query_selector_all(
        "#variation_size_name li span.a-size-base, "
        "div[id*='inline-twister-row-size'] li span.a-size-base, "
        "#tp-inline-twister-dim-values-container li"
    )

    for el in size_btn_els:
        text = el.text_content().strip()
        text_clean = re.sub(r"\s+", " ", text)
        if (
            text_clean
            and not text_clean.startswith("/*")
            and len(text_clean) < 20
        ):
            text_lower = text_clean.lower()
            if not any(
                k in text_lower for k in ignore_keywords
            ) and text_clean not in sizes:
                sizes.append(text_clean)

    # 2. 드롭다운 형태
    if not sizes:
        size_opt_els = page.query_selector_all(
            "select[name='dropdown_selected_size_name'] option, "
            "#native_dropdown_selected_size_name option"
        )
        for opt in size_opt_els:
            opt_text = opt.text_content().strip()
            opt_clean = re.sub(r"\s+", " ", opt_text)
            if opt_clean and len(opt_clean) < 20:
                opt_lower = opt_clean.lower()
                if not any(
                    k in opt_lower for k in ignore_keywords
                ) and opt_clean not in sizes:
                    sizes.append(opt_clean)

    return ", ".join(sizes) if sizes else "정보 없음"


def extract_stock_quantity_precise(page):
    """재고 문구 및 구매 수량 드롭다운 파싱을 통한 수량 파악"""
    avail_el = page.query_selector("#availability span, #availability")
    if avail_el:
        avail_text = avail_el.text_content().strip()

        if (
            "Currently unavailable" in avail_text
            or "Currently out of stock" in avail_text
        ):
            return "품절 (0개)"

        # "Only X left in stock" 패턴 탐색
        left_match = re.search(r"only\s+(\d+)\s+left", avail_text, re.IGNORECASE)
        if left_match:
            return f"{left_match.group(1)}개 남음 (품절 임박)"

    # 수량 선택 드롭다운(#quantity)의 최대치 검사
    qty_options = page.query_selector_all(
        "#quantity option, select[name='quantity'] option"
    )
    if qty_options:
        valid_qty = []
        for opt in qty_options:
            val = opt.get_attribute("value") or opt.text_content().strip()
            if val.isdigit():
                valid_qty.append(int(val))

        if valid_qty:
            max_qty = max(valid_qty)
            if max_qty >= 10:
                return "10개 이상 (재고 여유)"
            else:
                return f"최대 {max_qty}개 구매 가능"

    if avail_el and "In Stock" in avail_el.text_content():
        return "재고 있음 (수량 미표시)"

    return "정보 없음"


def extract_fit(page, title):
    """핏 정보 수집 (없을 시 '정보 없음')"""
    overview_rows = page.query_selector_all("#productOverview_feature_div tr")
    for row in overview_rows:
        row_text = row.text_content().lower()
        if "fit type" in row_text or "fit" in row_text:
            val_el = row.query_selector("td:nth-child(2) span")
            if val_el:
                res = val_el.text_content().strip()
                if res and not res.startswith("/*"):
                    return res

    bullet_el = page.query_selector("#feature-bullets")
    full_text = (
        (title + " " + (bullet_el.text_content() if bullet_el else "")).lower()
    )

    if "semi wide" in full_text or "semi-wide" in full_text:
        return "Semi Wide Fit"
    elif "wide leg" in full_text or "wide-leg" in full_text:
        return "Wide Leg Fit"
    elif "straight leg" in full_text or "straight" in full_text:
        return "Straight Fit"
    elif "loose" in full_text or "relaxed" in full_text:
        return "Loose / Relaxed Fit"

    return "정보 없음"


def fetch_amazon_products(keyword, max_items=50):
    products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # 영문 언어 설정을 유지하여 번역 노이즈(스토어, 아미그린 등) 방지
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()

        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        encoded_kw = keyword.replace(" ", "+")
        page_num = 1
        target_urls = []

        print(f"아마존 수집 시작: {keyword}")

        while len(target_urls) < max_items and page_num <= 3:
            url = f"https://www.amazon.com/s?k={encoded_kw}&page={page_num}"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2.5)

            for _ in range(3):
                page.mouse.wheel(0, 1000)
                time.sleep(0.8)

            items = page.query_selector_all(
                "div[data-component-type='s-search-result'], div.s-result-item[data-asin]:not([data-asin=''])"
            )

            for item in items:
                link_el = item.query_selector("h2 a, a.a-link-normal")
                if link_el:
                    href = link_el.get_attribute("href")
                    if href and "/dp/" in href:
                        clean_url = (
                            f"https://www.amazon.com{href}"
                            if href.startswith("/")
                            else href
                        )
                        clean_url = clean_url.split("/ref=")[0]
                        if clean_url not in target_urls:
                            target_urls.append(clean_url)

                if len(target_urls) >= max_items:
                    break

            page_num += 1

        print(
            f"총 {len(target_urls)}개 URL 수집 완료. 상세 검수 및 정밀 수집 시작...\n"
        )

        for idx, item_url in enumerate(target_urls, 1):
            print(f"[{idx}/{len(target_urls)}] 상세 검수 중: {item_url}")
            try:
                page.goto(
                    item_url, wait_until="domcontentloaded", timeout=60000
                )
                time.sleep(2.5)

                title_el = page.query_selector("#productTitle")
                if not title_el:
                    continue
                title = html.unescape(title_el.text_content().strip())

                # 항목별 정밀 파싱
                price_str, raw_krw_num = get_exact_krw_price(page)
                real_colors = extract_colors(page)
                real_sizes = extract_sizes_precise(page)
                real_stock = extract_stock_quantity_precise(page)
                real_fit = extract_fit(page, title)

                # 브랜드 노이즈 정제 (스토어, 방문, Visit the 등 제거)
                brand_el = page.query_selector(
                    "#bylineInfo, a#bylineInfo_feature_div"
                )
                brand = "정보 없음"
                if brand_el:
                    brand_text = brand_el.text_content().strip()
                    clean_brand = (
                        brand_text.replace("Brand:", "")
                        .replace("Visit the", "")
                        .replace("Store", "")
                        .replace("스토어", "")
                        .replace("방문", "")
                        .replace("페이지", "")
                        .replace("의", "")
                        .strip()
                    )
                    if clean_brand and not clean_brand.startswith("/*"):
                        brand = clean_brand

                rating_el = page.query_selector(
                    "span[data-hook='rating-out-of-text'], #acrPopover span.a-icon-alt"
                )
                rating = "정보 없음"
                if rating_el:
                    r_match = re.search(
                        r"(\d+\.\d+)", rating_el.text_content()
                    )
                    if r_match:
                        rating = float(r_match.group(1))

                products.append(
                    {
                        "제품명": title,
                        "가격(KRW)": price_str,
                        "raw_krw": raw_krw_num,
                        "브랜드": brand,
                        "카테고리": "Women's Fashion > Pants",
                        "평점": rating,
                        "색상": real_colors,
                        "핏": real_fit,
                        "사이즈": real_sizes,
                        "재고 수량": real_stock,
                        "제품 URL 링크": item_url,
                    }
                )

            except Exception as e:
                print(f"   └─ 수집 스킵 (사유: {e})")
                continue

        browser.close()

    return products


def evaluate_amazon_criteria(product):
    title_lower = product["제품명"].lower()
    krw_val = product["raw_krw"]

    c1 = any(
        color in title_lower or color in product["색상"].lower()
        for color in [
            "black",
            "white",
            "grey",
            "gray",
            "beige",
            "ivory",
            "cream",
            "charcoal",
            "khaki",
        ]
    )
    c2 = any(
        fit in title_lower or fit in product["핏"].lower()
        for fit in [
            "semi wide",
            "wide leg",
            "loose fit",
            "relaxed fit",
            "straight leg",
            "palazzo",
        ]
    )
    c3 = "cotton" in title_lower or "linen" in title_lower
    c4 = True
    c5 = True
    c6 = 20000 <= krw_val <= 70000 if krw_val > 0 else False
    c7 = any(
        word in title_lower
        for word in [
            "lightweight",
            "breathable",
            "summer",
            "cool",
            "thin",
            "soft",
        ]
    )
    c8 = any(
        word in title_lower
        for word in [
            "high waist",
            "high waisted",
            "pleated",
            "elastic waist",
            "drawstring",
            "tummy control",
        ]
    )

    matched_codes = []
    if c1:
        matched_codes.append("C1")
    if c2:
        matched_codes.append("C2")
    if c3:
        matched_codes.append("C3")
    if c4:
        matched_codes.append("C4")
    if c5:
        matched_codes.append("C5")
    if c6:
        matched_codes.append("C6")
    if c7:
        matched_codes.append("C7")
    if c8:
        matched_codes.append("C8")

    return {
        "제품명": product["제품명"],
        "브랜드": product["브랜드"],
        "카테고리": product["카테고리"],
        "가격(KRW)": product["가격(KRW)"],
        "색상": product["색상"],
        "핏": product["핏"],
        "사이즈": product["사이즈"],
        "재고 수량": product["재고 수량"],
        "평점": product["평점"],
        "제품 URL 링크": product["제품 URL 링크"],
        "충족 개수": len(matched_codes),
        "충족 항목": ", ".join(matched_codes),
    }


def main():
    print("아마존 최종 정제 수집을 시작합니다...")
    raw_products = fetch_amazon_products(
        "women semi wide cotton pants", max_items=50
    )

    if not raw_products:
        print("수집 완료된 상품이 없습니다.")
        return

    processed = [evaluate_amazon_criteria(p) for p in raw_products]
    df = pd.DataFrame(processed)
    df = df.drop_duplicates(subset=["제품명"]).reset_index(drop=True)
    df = df.sort_values(by="충족 개수", ascending=False)

    output_filename = "amazon_recommend_clothing_perfect.csv"
    df.to_csv(output_filename, index=False, encoding="utf-8-sig")

    print("\n=================== 정제 수집 및 CSV 저장 완료 ===================")
    print(f"최종 저장 파일: {output_filename}")


if __name__ == "__main__":
    main()