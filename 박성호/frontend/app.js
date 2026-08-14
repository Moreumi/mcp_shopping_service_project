// ==========================================================
// CONFIG
// ==========================================================

// Derived from the host that served this page, so the same build works when
// opened as http://127.0.0.1:5500 locally or http://<presenter-LAN-IP>:5500
// from another laptop on the same network — no per-machine edits needed.
const API_HOST = window.location.hostname || "127.0.0.1";
const API_ORIGIN = `http://${API_HOST}:8000`;
const API_URL = `${API_ORIGIN}/chat/stream`;
const HEALTH_URL = `${API_ORIGIN}/health/details`;
const PERSONALIZED_URL = `${API_ORIGIN}/personalized/recommendations`;
const PERSONALIZED_CLICK_URL = `${API_ORIGIN}/personalized/click`;
const PERSONALIZED_CHAT_URL = `${API_ORIGIN}/personalized/chat`;
const CS_API_URL = `${API_ORIGIN}/cs/chat`;
const CS_STREAM_API_URL = `${API_ORIGIN}/cs/chat/stream`;

// Visual reference galleries for the Detail Search survey - mirrors the
// original style prototype's GUIDE_IMAGES mapping.
const GUIDE_IMAGES = {
    fitTops: {
        "오버핏": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshopping.phinf.naver.net%2Fmain_3894276%2F38942763279.20230326123955.jpg&type=sc960_832",
        "레귤러핏": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshop1.phinf.naver.net%2F20260415_229%2F1776241885302XMcF8_JPEG%2F39233345435276364_37012547.jpg&type=a340",
        "슬림핏": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20260613_131%2F1781311072686Ksc9V_JPEG%2F27753390614117711_114414901.jpg&type=a340",
        "크롭핏": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20220424_8%2F165079580093787JIR_JPEG%2F58260497043079903_730212950.jpg&type=a340",
    },
    neckline: {
        "라운드넥": "https://search.pstatic.net/sunny/?src=http%3A%2F%2Luxboy.interhosting.kr%2F_wizfasta%2Fprada%2Fshort_sleeved_shirts%2Flj73d_bm1_f01ay_42830.jpg&type=a340",
        "V넥": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshop1.phinf.naver.net%2F20250722_54%2F1753150794011P9VBM_JPEG%2F87283654123233168_1467617044.jpg&type=a340",
        "카라/오픈카라/헨리넥": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20240928_3%2F1727497629319dolri_JPEG%2F4135043568336507_1582816217.jpg&type=a340",
        "모크넥/터틀넥": "https://search.pstatic.net/sunny/?src=https%3A%2F%2Fimage.msscdn.net%2Fthumbnails%2Fimages%2Fgoods_img%2F20211105%2F2219075%2F2219075_1_big.jpg%3Fw%3D780&type=a340",
    },
    fitBottoms: {
        "스트레이트": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20251124_219%2F17639213612416tdqc_PNG%2F89552995241945655_1508996527.png&type=sc960_832",
        "슬림핏": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyMDA5MDJfMTA3%2FMDAxNTk5MDE0MDQ5OTU1.DMbAOyuHkh0TLEnlbZglcYgdhEEZMbZwX1qEAHMo9Vcg.uuGRS9GOqlHlN8W_fqaa2ReS_BU0jFi-Y-rHlDcwR6Ig.JPEG.whqudgus2%2FKakaoTalk_20200827_001937589_10.jpg&type=sc960_832",
        "와이드": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshopping.phinf.naver.net%2Fmain_5891877%2F58918777061.20260214011350.jpg&type=sc960_832",
        "세미와이드": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNjA1MDFfMTEx%2FMDAxNzc3NjA4NjM1Mzg3.8Z2e_WkQvmwkQwxzEKv4pcbt9O3sYGipXN8CqhaQwxkg.gweLDJlXnZy0lHgeYcB7lrNb2s6_H5Z8n2kmdmZEYCAg.JPEG%2F3a631497a877.jpg&type=sc960_832",
    },
    material: {
        "면": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNTEwMDNfMTcw%2FMDAxNzU5NDYxMzE2OTMz.j2wBixJECpn5KkVcc-Ox4KyaI4DRtwn4dzy4dsOBAHkg.6IK-hKSTAOMPNgbF1kA_kmfmuIEHDfuRg7poKM7aZn8g.PNG%2FImage_fx.png&type=a340",
        "폴리에스터": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNDEyMjNfMzAg%2FMDAxNzM0OTI4MjkzNzk2.ANN4XpK1dcPREF3qae1lkgjpCgYsO0zttsy0dH50Jg8g.3y2vN4HIqv6em2hfvSOMZdQjSnIo73rNCpwTIR3hfnAg.PNG%2Fimage.png&type=a340",
        "기모": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNTAxMjNfNSAg%2FMDAxNzM3NjA4ODI1Nzc5.Q98pe-JQ2zMVlpYQc0DKLUKdjoMoaW06qBbNsuLJdXwg.FYECdmBiHlmfQM3pmgzEi07Vto5cB8QiooTYTbGY_cYg.PNG%2Fimage.png&type=a340",
        "린넨": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyM10xMTfMjUw%2FMDAxNjMzOTU3NjA4MDIz.8IC1FrHSGYauFdTZtAWt7hXuHv3wfspT-LapVvU16Psg.nMHTq-yDManCwSTynKkC-kPf44hP3o5mIFurXIPpsmMg.JPEG.ranswor%2FKakaoTalk_20211011_182437781_01.jpg&type=a340",
        "청": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyMjAzMDhfMjY2%2FMDAxNxO3NzI0MjU1Mzc4.A8MrvsTG7K2oZSLOk4Lljur9Mj7x1e-v6hHS8dEnXigg.958L7ceSSZcaBZXWYztiw0LQZRqVruv0MbowDavRxZwg.JPEG.nh-motors%2F28.jpg&type=a340",
    },
};


// ==========================================================
// DOM
// ==========================================================

const welcomeScreen =
    document.getElementById("welcomeScreen");

const chatScreen =
    document.getElementById("chatScreen");

const welcomeInput =
    document.getElementById("welcomeInput");

const chatInput =
    document.getElementById("chatInput");

const welcomeSendButton =
    document.getElementById("welcomeSendButton");

const chatSendButton =
    document.getElementById("chatSendButton");

const messages =
    document.getElementById("messages");

const newThreadButton =
    document.getElementById("newThreadButton");

const newChatTop =
    document.getElementById("newChatTop");

const customerServiceButton = document.getElementById("customerServiceButton");
const csScreen = document.getElementById("csScreen");
const csMessages = document.getElementById("csMessages");
const csInput = document.getElementById("csInput");
const csSendButton = document.getElementById("csSendButton");

const systemStatusButton = document.getElementById("systemStatusButton");
const statusModal = document.getElementById("statusModal");
const closeStatusButton = document.getElementById("closeStatusButton");
const refreshStatusButton = document.getElementById("refreshStatusButton");
const statusGrid = document.getElementById("statusGrid");
const preferenceModal = document.getElementById("preferenceModal");
const preferenceForm = document.getElementById("preferenceForm");
const closePreferenceButton = document.getElementById("closePreferenceButton");
const preferenceResults = document.getElementById("preferenceResults");
const personalizedProducts = document.getElementById("personalizedProducts");
const resultsQuery = document.getElementById("resultsQuery");
const surveyAgainButton = document.getElementById("surveyAgainButton");
const preferenceError = document.getElementById("preferenceError");

const preferenceTabSurvey = document.getElementById("preferenceTabSurvey");
const preferenceTabChat = document.getElementById("preferenceTabChat");
const preferenceSurveyPanel = document.getElementById("preferenceSurveyPanel");
const preferenceChatPanel = document.getElementById("preferenceChatPanel");
const preferenceChatMessages = document.getElementById("preferenceChatMessages");
const preferenceChatForm = document.getElementById("preferenceChatForm");
const preferenceChatInput = document.getElementById("preferenceChatInput");
const categoryRadios = document.querySelectorAll("input[name='detailCategory']");


// ==========================================================
// STATE
// ==========================================================

let isLoading = false;

function resolveDemoUserId() {
    const requested = new URLSearchParams(window.location.search).get("user_id");
    const valid = value => /^[A-Za-z0-9_-]{1,64}$/.test(value || "");
    if (valid(requested)) {
        const isolated = requested === "user_001"
            ? requested
            : `demo_${requested.replace(/^demo_/, "").slice(0, 48)}`;
        localStorage.setItem("shopping_demo_user_id", isolated);
        return isolated;
    }
    const stored = localStorage.getItem("shopping_demo_user_id");
    return valid(stored) ? stored : "user_001";
}

const USER_ID = resolveDemoUserId();
let threadId = sessionStorage.getItem("shopping_thread_id") || crypto.randomUUID();
sessionStorage.setItem("shopping_thread_id", threadId);

// Customer Service tab is fully independent from the shopping chat above:
// its own thread id, its own customer identity, its own send/render logic.
let csIsLoading = false;
const CS_CUSTOMER_ID = 1;
let csThreadId = sessionStorage.getItem("cs_thread_id") || crypto.randomUUID();
sessionStorage.setItem("cs_thread_id", csThreadId);


// ==========================================================
// TEXTAREA AUTO RESIZE
// ==========================================================

function autoResize(textarea) {

    textarea.style.height = "auto";

    textarea.style.height =
        Math.min(
            textarea.scrollHeight,
            130
        ) + "px";
}


welcomeInput.addEventListener(
    "input",
    () => autoResize(welcomeInput)
);


chatInput.addEventListener(
    "input",
    () => autoResize(chatInput)
);


csInput.addEventListener(
    "input",
    () => autoResize(csInput)
);


// ==========================================================
// SCREEN
// ==========================================================

function openChat() {

    welcomeScreen.classList.add(
        "hidden"
    );

    chatScreen.classList.remove(
        "hidden"
    );
}


function resetChat() {

    messages.innerHTML = "";

    chatInput.value = "";

    welcomeInput.value = "";

    threadId = crypto.randomUUID();
    sessionStorage.setItem("shopping_thread_id", threadId);

    autoResize(chatInput);

    autoResize(welcomeInput);

    chatScreen.classList.add(
        "hidden"
    );

    csScreen.classList.add(
        "hidden"
    );

    welcomeScreen.classList.remove(
        "hidden"
    );

    newChatTop.classList.add("active");
    customerServiceButton.classList.remove("active");

    setTimeout(() => {
        welcomeInput.focus();
    }, 100);
}


// ==========================================================
// CUSTOMER SERVICE TAB (독립 파이프라인)
// ==========================================================

function openCustomerService() {

    welcomeScreen.classList.add("hidden");
    chatScreen.classList.add("hidden");
    csScreen.classList.remove("hidden");

    newChatTop.classList.remove("active");
    customerServiceButton.classList.add("active");

    if (!csMessages.children.length) {
        addCsAssistantMessage(
            "안녕하세요! 주문, 결제, 배송 관련 문의를 도와드리겠습니다. 무엇을 도와드릴까요?"
        );
    }

    setTimeout(() => {
        csInput.focus();
    }, 100);
}


// ==========================================================
// USER MESSAGE
// ==========================================================

function addUserMessage(text) {

    const wrapper =
        document.createElement("div");

    wrapper.className =
        "message user";


    const bubble =
        document.createElement("div");

    bubble.className =
        "user-bubble";

    bubble.textContent = text;


    wrapper.appendChild(
        bubble
    );

    messages.appendChild(
        wrapper
    );

    scrollToBottom();
}


// ==========================================================
// AI MESSAGE
// ==========================================================

function createProductCards(products) {

    const grid = document.createElement("div");
    grid.className = "product-grid";

    products.forEach(product => {
        const card = document.createElement(product.amazon_url ? "a" : "article");
        card.className = "product-card";
        if (product.amazon_url) {
            card.href = product.amazon_url;
            card.target = "_blank";
            card.rel = "noopener noreferrer";
            card.setAttribute("aria-label", `${product.title || "Amazon product"} 상품 페이지 열기`);
        }

        let image;
        if (product.image_url) {
            image = document.createElement("img");
            image.className = "product-image";
            image.src = product.image_url;
            image.alt = product.title || "Product image";
            image.loading = "lazy";
            image.referrerPolicy = "no-referrer";
            image.addEventListener("error", () => {
                const placeholder = document.createElement("div");
                placeholder.className = "product-image-placeholder";
                placeholder.innerHTML = '<span class="material-symbols-outlined">shopping_bag</span>';
                image.replaceWith(placeholder);
            }, { once: true });
        } else {
            image = document.createElement("div");
            image.className = "product-image-placeholder";
            image.innerHTML = '<span class="material-symbols-outlined">shopping_bag</span>';
        }

        const title = document.createElement("h3");
        title.textContent = product.title || "Untitled product";

        const meta = document.createElement("p");
        meta.className = "product-meta";
        meta.textContent = [product.brand, product.color]
            .filter(Boolean)
            .join(" · ");

        const commerce = document.createElement("p");
        commerce.className = "product-commerce";
        const commerceParts = [];
        if (Number.isFinite(Number(product.average_rating))) {
            commerceParts.push(`★ ${Number(product.average_rating).toFixed(1)}`);
        }
        if (Number.isFinite(Number(product.review_count))) {
            commerceParts.push(`${Number(product.review_count).toLocaleString("en-US")} reviews`);
        }
        if (Number.isFinite(Number(product.price))) {
            commerceParts.push(`$${Number(product.price).toFixed(2)}`);
        }
        commerce.textContent = commerceParts.join(" · ");

        const id = document.createElement("code");
        id.className = "product-id";
        id.textContent = product.product_id || "";

        card.append(image, title);
        if (meta.textContent) card.appendChild(meta);
        if (commerce.textContent) card.appendChild(commerce);
        card.appendChild(id);
        grid.appendChild(card);
    });

    return grid;
}


function displayValue(value, formatter = String) {
    return value === undefined || value === null || value === ""
        ? "Not available"
        : formatter(value);
}


function createComparisonTable(products) {
    const wrapper = document.createElement("div");
    wrapper.className = "comparison-wrapper";
    const table = document.createElement("table");
    table.className = "comparison-table";
    const fields = [
        ["Product", product => product.title || "Untitled product"],
        ["Brand", product => displayValue(product.brand)],
        ["Price", product => displayValue(product.price, value => `$${Number(value).toFixed(2)}`)],
        ["Rating", product => displayValue(product.average_rating, value => `${Number(value).toFixed(1)}/5`)],
        ["Reviews", product => displayValue(product.review_count, value => Number(value).toLocaleString("en-US"))],
        ["Color", product => displayValue(product.color)],
        ["Material", product => displayValue(product.material)],
    ];
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    const empty = document.createElement("th");
    empty.textContent = "Comparison";
    headRow.appendChild(empty);
    products.forEach((_, index) => {
        const th = document.createElement("th");
        th.textContent = `Product ${index + 1}`;
        headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);
    const body = document.createElement("tbody");
    fields.forEach(([label, getter]) => {
        const row = document.createElement("tr");
        const labelCell = document.createElement("th");
        labelCell.textContent = label;
        row.appendChild(labelCell);
        products.forEach(product => {
            const cell = document.createElement("td");
            cell.textContent = getter(product);
            row.appendChild(cell);
        });
        body.appendChild(row);
    });
    table.appendChild(body);
    wrapper.appendChild(table);
    return wrapper;
}


function createLearnMoreButton() {
    const container = document.createElement("div");
    container.className = "learn-more-actions";

    const moreButton = document.createElement("button");
    moreButton.type = "button";
    moreButton.className = "more-recommendations-button";
    moreButton.textContent = "Recommend";
    moreButton.addEventListener("click", () => sendMessage("더 많은 상품 추천해줘"));
    container.appendChild(moreButton);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "learn-more-button";
    button.textContent = "Detail Search";
    button.addEventListener("click", openPreferenceSurvey);
    container.appendChild(button);

    return container;
}


const TOPS_ANSWER_KEYS = ["gender", "color", "fit", "material", "type", "neckline", "budget", "season"];
const BOTTOMS_ANSWER_KEYS = ["gender", "color", "fit", "material", "mood", "use", "budget", "season"];

function getSelectedCategory() {
    const checked = Array.from(categoryRadios).find(input => input.checked);
    return checked ? checked.value : "tops";
}


function updateCategoryFields() {
    const category = getSelectedCategory();
    document.querySelectorAll("[data-category-fields]").forEach(element => {
        const matches = element.dataset.categoryFields === category;
        element.classList.toggle("hidden", !matches);
        // Both category blocks share field names (color/fit/material/...),
        // so FormData would otherwise always read whichever block comes
        // first in DOM order - disabling the hidden one excludes it from
        // FormData entirely, which is exactly what a native form does.
        element.querySelectorAll("select, input").forEach(field => { field.disabled = !matches; });
        if (!matches) {
            element.querySelectorAll("input[type='checkbox']").forEach(box => { box.checked = false; });
        }
    });
}


function switchPreferenceTab(tab) {
    const isSurvey = tab === "survey";
    preferenceTabSurvey.classList.toggle("active", isSurvey);
    preferenceTabChat.classList.toggle("active", !isSurvey);
    preferenceSurveyPanel.classList.toggle("hidden", !isSurvey);
    preferenceChatPanel.classList.toggle("hidden", isSurvey);
}


function renderGuideGallery(containerId, imageMap) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.replaceChildren();
    Object.entries(imageMap).forEach(([label, url]) => {
        const figure = document.createElement("figure");
        const img = document.createElement("img");
        // Not loading="lazy" - these sit inside a collapsed <details> (and a
        // category-hidden block for half of them), so IntersectionObserver
        // never sees them as near-viewport and native lazy loading defers
        // the fetch indefinitely even after the details is opened.
        img.src = url;
        img.alt = label;
        img.referrerPolicy = "no-referrer";
        const caption = document.createElement("figcaption");
        caption.textContent = label;
        figure.append(img, caption);
        container.appendChild(figure);
    });
}


function renderGuideGalleries() {
    renderGuideGallery("guideFitTops", GUIDE_IMAGES.fitTops);
    renderGuideGallery("guideFitBottoms", GUIDE_IMAGES.fitBottoms);
    renderGuideGallery("guideNeckline", GUIDE_IMAGES.neckline);
    renderGuideGallery("guideMaterial", GUIDE_IMAGES.material);
}


function openPreferenceSurvey() {
    preferenceForm.classList.remove("hidden");
    preferenceResults.classList.add("hidden");
    preferenceError.classList.add("hidden");
    switchPreferenceTab("survey");
    updateCategoryFields();
    preferenceModal.classList.remove("hidden");
}


function closePreferenceSurvey() {
    preferenceModal.classList.add("hidden");
}


function addProductText(parent, className, text) {
    const element = document.createElement("p");
    element.className = className;
    element.textContent = text;
    parent.appendChild(element);
}


async function registerPreferenceClick(asin, badge) {
    try {
        const response = await fetch(PERSONALIZED_CLICK_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ asin })
        });
        const data = await response.json();
        if (response.ok && badge) badge.textContent = `👍 관심 등록 ${data.clicks}회`;
    } catch (error) {
        // Non-critical - the survey result itself is already shown.
    }
}


function renderPersonalizedProducts(data) {
    personalizedProducts.replaceChildren();
    resultsQuery.textContent = `Amazon search: ${data.query}`;

    if (!data.products.length) {
        addProductText(personalizedProducts, "recommendation-loading", "조건에 맞는 실시간 Amazon 상품을 찾지 못했습니다.");
        return;
    }

    data.products.forEach((product, index) => {
        const card = document.createElement("article");
        card.className = "personalized-card";

        const image = document.createElement("img");
        image.src = product.image_url || "";
        image.alt = product.title;
        image.loading = "lazy";
        card.appendChild(image);

        const info = document.createElement("div");
        const title = document.createElement("h4");
        title.textContent = `${index + 1}. ${product.title}`;
        info.appendChild(title);
        addProductText(info, "personalized-score", `AI match ${product.score} · 조건 일치 ${product.match_percent}%`);
        addProductText(info, "personalized-meta", `${product.price_krw || "가격 정보 확인 필요"} · ★ ${product.rating || "-"} · ${Number(product.reviews || 0).toLocaleString()} reviews`);

        if (product.reasons?.length) {
            const reasons = document.createElement("ul");
            reasons.className = "personalized-reasons";
            product.reasons.slice(0, 3).forEach(reason => {
                const item = document.createElement("li");
                item.textContent = reason;
                reasons.appendChild(item);
            });
            info.appendChild(reasons);
        }

        const actions = document.createElement("div");
        actions.className = "personalized-actions";

        const interestButton = document.createElement("button");
        interestButton.type = "button";
        interestButton.className = "interest-button";
        const initialClicks = product.clicks || 0;
        interestButton.textContent = initialClicks ? `👍 관심 등록 ${initialClicks}회` : "👍 관심 등록";
        interestButton.addEventListener("click", () => registerPreferenceClick(product.asin, interestButton));
        actions.appendChild(interestButton);

        const link = document.createElement("a");
        link.className = "amazon-link";
        link.href = product.amazon_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Amazon에서 보기 →";
        actions.appendChild(link);

        info.appendChild(actions);
        card.appendChild(info);
        personalizedProducts.appendChild(card);
    });
}


async function submitPreferenceSurvey(event) {
    event.preventDefault();
    const formData = new FormData(preferenceForm);
    const priorities = formData.getAll("priority");
    if (priorities.length > 3) {
        preferenceError.textContent = "중요 조건은 최대 3개까지 선택할 수 있습니다.";
        preferenceError.classList.remove("hidden");
        return;
    }

    preferenceError.classList.add("hidden");
    preferenceForm.classList.add("hidden");
    preferenceResults.classList.remove("hidden");
    personalizedProducts.replaceChildren();
    addProductText(personalizedProducts, "recommendation-loading", "Amazon에서 취향에 맞는 상품을 찾고 있습니다...");

    const category = getSelectedCategory();
    const answerKeys = category === "tops" ? TOPS_ANSWER_KEYS : BOTTOMS_ANSWER_KEYS;
    const answers = Object.fromEntries(answerKeys.map(key => [key, formData.get(key)]));
    try {
        const response = await fetch(PERSONALIZED_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category, answers, priorities, user_id: USER_ID })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "실시간 추천을 불러오지 못했습니다.");
        renderPersonalizedProducts(data);
    } catch (error) {
        personalizedProducts.replaceChildren();
        addProductText(personalizedProducts, "recommendation-loading", error.message);
    }
}


// ----- Detail Search 챗봇 탭 (CS 탭의 메시지 렌더링 패턴을 그대로 미러링) -----

function addDetailChatUserMessage(text) {
    const wrapper = document.createElement("div");
    wrapper.className = "message user";
    const bubble = document.createElement("div");
    bubble.className = "user-bubble";
    bubble.textContent = text;
    wrapper.appendChild(bubble);
    preferenceChatMessages.appendChild(wrapper);
    scrollDetailChatToBottom();
}


function addDetailChatAssistantMessage(advice, products = []) {
    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";

    const container = document.createElement("div");
    container.className = "assistant-message";

    const avatar = document.createElement("div");
    avatar.className = "ai-avatar";
    avatar.innerHTML = '<span class="material-symbols-outlined">styler</span>';

    const content = document.createElement("div");
    content.className = "ai-content";
    content.textContent = advice;

    container.append(avatar, content);
    wrapper.appendChild(container);

    if (products.length) {
        const gallery = document.createElement("div");
        gallery.className = "detail-chat-products";
        products.forEach(product => {
            const card = document.createElement("article");
            card.className = "detail-chat-card";
            const image = document.createElement("img");
            image.src = product.image_url || "";
            image.alt = product.title;
            image.loading = "lazy";
            card.appendChild(image);
            const title = document.createElement("p");
            title.className = "detail-chat-card-title";
            title.textContent = product.title;
            card.appendChild(title);
            addProductText(card, "detail-chat-card-meta", `${product.price_krw || "가격 변동"} · ★ ${product.rating || "-"}`);
            const link = document.createElement("a");
            link.className = "amazon-link";
            link.href = product.amazon_url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "구매 링크 →";
            card.appendChild(link);
            gallery.appendChild(card);
        });
        wrapper.appendChild(gallery);
    }

    preferenceChatMessages.appendChild(wrapper);
    scrollDetailChatToBottom();
}


function addDetailChatLoadingMessage() {
    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";
    wrapper.id = "detailChatLoadingMessage";

    const container = document.createElement("div");
    container.className = "assistant-message";

    const avatar = document.createElement("div");
    avatar.className = "ai-avatar";
    avatar.innerHTML = '<span class="material-symbols-outlined">styler</span>';

    const loading = document.createElement("div");
    loading.className = "loading";
    loading.innerHTML = "<span></span><span></span><span></span>";

    container.append(avatar, loading);
    wrapper.appendChild(container);
    preferenceChatMessages.appendChild(wrapper);
    scrollDetailChatToBottom();
}


function removeDetailChatLoadingMessage() {
    const loading = document.getElementById("detailChatLoadingMessage");
    if (loading) loading.remove();
}


function scrollDetailChatToBottom() {
    requestAnimationFrame(() => {
        preferenceChatMessages.scrollTo({
            top: preferenceChatMessages.scrollHeight,
            behavior: "smooth"
        });
    });
}


async function sendDetailSearchChatMessage(text) {
    text = text.trim();
    if (!text) return;

    addDetailChatUserMessage(text);
    preferenceChatInput.value = "";
    addDetailChatLoadingMessage();

    try {
        const response = await fetch(PERSONALIZED_CHAT_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        removeDetailChatLoadingMessage();
        if (!response.ok) throw new Error(data.detail || "스타일 추천을 불러오지 못했습니다.");
        addDetailChatAssistantMessage(data.advice, data.products || []);
    } catch (error) {
        removeDetailChatLoadingMessage();
        addDetailChatAssistantMessage(error.message, []);
    }
}


closePreferenceButton.addEventListener("click", closePreferenceSurvey);
surveyAgainButton.addEventListener("click", openPreferenceSurvey);
preferenceForm.addEventListener("submit", submitPreferenceSurvey);
preferenceModal.addEventListener("click", event => {
    if (event.target === preferenceModal) closePreferenceSurvey();
});
preferenceForm.querySelectorAll("input[name='priority']").forEach(input => {
    input.addEventListener("change", () => {
        const checked = preferenceForm.querySelectorAll("input[name='priority']:checked");
        if (checked.length > 3) input.checked = false;
    });
});
categoryRadios.forEach(input => input.addEventListener("change", updateCategoryFields));
preferenceTabSurvey.addEventListener("click", () => switchPreferenceTab("survey"));
preferenceTabChat.addEventListener("click", () => switchPreferenceTab("chat"));
preferenceChatForm.addEventListener("submit", event => {
    event.preventDefault();
    sendDetailSearchChatMessage(preferenceChatInput.value);
});
renderGuideGalleries();


function addAssistantMessage(text, products = [], suggestions = [], responseMode = "search") {

    const wrapper =
        document.createElement("div");

    wrapper.className =
        "message assistant";


    const container =
        document.createElement("div");

    container.className =
        "assistant-message";


    const avatar =
        document.createElement("div");

    avatar.className =
        "ai-avatar";

    avatar.innerHTML = `
        <span class="material-symbols-outlined">
            auto_awesome
        </span>
    `;


    const content =
        document.createElement("div");

    content.className =
        "ai-content";

    content.textContent = text;

    if (products.length) {
        content.appendChild(
            responseMode === "compare"
                ? createComparisonTable(products)
                : createProductCards(products)
        );
    }

    if (products.length && responseMode !== "compare") {
        content.appendChild(createLearnMoreButton());
    }


    container.appendChild(
        avatar
    );

    container.appendChild(
        content
    );

    wrapper.appendChild(
        container
    );

    messages.appendChild(
        wrapper
    );

    scrollToBottom();
}


function addStreamingAssistantMessage() {
    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";

    const container = document.createElement("div");
    container.className = "assistant-message";

    const avatar = document.createElement("div");
    avatar.className = "ai-avatar";
    avatar.innerHTML = '<span class="material-symbols-outlined">auto_awesome</span>';

    const content = document.createElement("div");
    content.className = "ai-content";
    const answer = document.createElement("span");
    answer.className = "streaming-answer";
    content.appendChild(answer);

    container.append(avatar, content);
    wrapper.appendChild(container);
    messages.appendChild(wrapper);
    scrollToBottom();
    return { content, answer };
}


function finishStreamingAssistantMessage(stream, data) {
    if (data.products?.length) renderStreamingProducts(stream, data.products, data.response_mode);
    if (data.products?.length && data.response_mode !== "compare") {
        if (!stream.learnMoreRendered) {
            stream.content.appendChild(createLearnMoreButton());
            stream.learnMoreRendered = true;
        }
    }
    scrollToBottom();
}


function renderStreamingProducts(stream, products, responseMode = "search") {
    if (!products?.length) return;
    if (!stream.productsContainer) {
        stream.productsContainer = document.createElement("div");
        stream.productsContainer.className = "streaming-products";
        stream.content.appendChild(stream.productsContainer);
    }
    // A fast BM25 preview is replaced in place by the final hybrid/reranked cards.
    stream.productsContainer.replaceChildren(
        responseMode === "compare"
            ? createComparisonTable(products)
            : createProductCards(products)
    );
    stream.productsRendered = true;
    if (responseMode !== "compare" && !stream.learnMoreRendered) {
        stream.content.appendChild(createLearnMoreButton());
        stream.learnMoreRendered = true;
    }
    scrollToBottom();
}


// ==========================================================
// LOADING
// ==========================================================

function addLoadingMessage() {

    const wrapper =
        document.createElement("div");

    wrapper.className =
        "message assistant";

    wrapper.id =
        "loadingMessage";


    const container =
        document.createElement("div");

    container.className =
        "assistant-message";


    const avatar =
        document.createElement("div");

    avatar.className =
        "ai-avatar";

    avatar.innerHTML = `
        <span class="material-symbols-outlined">
            auto_awesome
        </span>
    `;


    const loading =
        document.createElement("div");

    loading.className =
        "loading";

    loading.innerHTML = `
        <span></span>
        <span></span>
        <span></span>
    `;


    container.appendChild(
        avatar
    );

    container.appendChild(
        loading
    );

    wrapper.appendChild(
        container
    );

    messages.appendChild(
        wrapper
    );

    scrollToBottom();
}


function removeLoadingMessage() {

    const loading =
        document.getElementById(
            "loadingMessage"
        );

    if (loading) {
        loading.remove();
    }
}


function updateLoadingMessage(text) {
    const loading = document.getElementById("loadingMessage");
    if (!loading) return;

    let status = loading.querySelector(".loading-status");
    if (!status) {
        status = document.createElement("span");
        status.className = "loading-status";
        loading.querySelector(".assistant-message").appendChild(status);
    }
    status.textContent = text;
}


function parseSseBlock(block) {
    let event = "message";
    const data = [];

    block.split("\n").forEach(line => {
        if (line.startsWith("event:")) {
            event = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
            data.push(line.slice(5).trim());
        }
    });

    return {
        event,
        data: data.length ? JSON.parse(data.join("\n")) : {}
    };
}


// ==========================================================
// SCROLL
// ==========================================================

function scrollToBottom() {

    requestAnimationFrame(() => {

        messages.scrollTo({
            top: messages.scrollHeight,
            behavior: "smooth"
        });

    });
}


// ==========================================================
// API
// ==========================================================

async function sendMessage(text) {

    text = text.trim();

    if (!text || isLoading) {
        return;
    }


    isLoading = true;

    openChat();

    addUserMessage(text);

    chatInput.value = "";

    welcomeInput.value = "";

    autoResize(chatInput);

    autoResize(welcomeInput);


    welcomeSendButton.disabled = true;
    chatSendButton.disabled = true;


    addLoadingMessage();


    try {

        const response =
            await fetch(
                API_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message: text,
                        user_id: USER_ID,
                        thread_id: threadId
                    })
                }
            );


        if (!response.ok) {
            let detail = `Request failed (HTTP ${response.status})`;
            try {
                const errorBody = await response.json();
                if (errorBody.detail) detail = errorBody.detail;
            } catch (_) {
                // Keep the status-based message when the body is not JSON.
            }
            throw new Error(detail);
        }


        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let data = null;
        let streamedAnswer = "";
        let streamingMessage = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const blocks = buffer.split("\n\n");
            buffer = blocks.pop();

            blocks.forEach(block => {
                if (!block.trim()) return;
                const message = parseSseBlock(block);

                if (message.event === "status") {
                    updateLoadingMessage(message.data.message);
                } else if (message.event === "products") {
                    if (!streamingMessage) {
                        removeLoadingMessage();
                        streamingMessage = addStreamingAssistantMessage();
                    }
                    const earlyProducts = message.data.products || [];
                    renderStreamingProducts(
                        streamingMessage,
                        earlyProducts,
                        message.data.response_mode || "search"
                    );
                } else if (message.event === "answer_delta") {
                    if (!streamingMessage) {
                        removeLoadingMessage();
                        streamingMessage = addStreamingAssistantMessage();
                    }
                    streamedAnswer += message.data.text || "";
                    streamingMessage.answer.textContent = streamedAnswer;
                    scrollToBottom();
                } else if (message.event === "result") {
                    data = message.data;
                } else if (message.event === "error") {
                    throw new Error(message.data.message);
                }
            });
        }


        removeLoadingMessage();


        if (!data || !data.answer) {

            addAssistantMessage(
                "The assistant returned an empty response."
            );

            return;
        }


        if (streamingMessage) {
            streamingMessage.answer.textContent = data.answer;
            finishStreamingAssistantMessage(streamingMessage, data);
        } else {
            addAssistantMessage(
                data.answer,
                data.products || [],
                data.suggestions || [],
                data.response_mode || "search"
            );
        }

    }

    catch (error) {

        console.error(
            "API Error:",
            error
        );


        removeLoadingMessage();


        addAssistantMessage(error.message || "The shopping request could not be completed.");

    }

    finally {

        isLoading = false;

        welcomeSendButton.disabled = false;
        chatSendButton.disabled = false;

        chatInput.focus();
    }
}


// ==========================================================
// CUSTOMER SERVICE MESSAGES / API (독립 파이프라인)
// ==========================================================

function addCsUserMessage(text) {

    const wrapper = document.createElement("div");
    wrapper.className = "message user";

    const bubble = document.createElement("div");
    bubble.className = "user-bubble";
    bubble.textContent = text;

    wrapper.appendChild(bubble);
    csMessages.appendChild(wrapper);

    scrollCsToBottom();
}


function addCsAssistantMessage(text) {

    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";

    const container = document.createElement("div");
    container.className = "assistant-message";

    const avatar = document.createElement("div");
    avatar.className = "ai-avatar";
    avatar.innerHTML = '<span class="material-symbols-outlined">support_agent</span>';

    const content = document.createElement("div");
    content.className = "ai-content";
    content.textContent = text;

    container.append(avatar, content);
    wrapper.appendChild(container);
    csMessages.appendChild(wrapper);

    scrollCsToBottom();

    return { wrapper, content };
}


function addCsLoadingMessage() {

    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";
    wrapper.id = "csLoadingMessage";

    const container = document.createElement("div");
    container.className = "assistant-message";

    const avatar = document.createElement("div");
    avatar.className = "ai-avatar";
    avatar.innerHTML = '<span class="material-symbols-outlined">support_agent</span>';

    const loading = document.createElement("div");
    loading.className = "loading";
    loading.innerHTML = "<span></span><span></span><span></span>";

    container.append(avatar, loading);
    wrapper.appendChild(container);
    csMessages.appendChild(wrapper);

    scrollCsToBottom();
}


function removeCsLoadingMessage() {
    const loading = document.getElementById("csLoadingMessage");
    if (loading) loading.remove();
}


function scrollCsToBottom() {
    requestAnimationFrame(() => {
        csMessages.scrollTo({
            top: csMessages.scrollHeight,
            behavior: "smooth"
        });
    });
}


async function sendCsMessage(text) {

    text = text.trim();

    if (!text || csIsLoading) {
        return;
    }

    csIsLoading = true;

    addCsUserMessage(text);

    csInput.value = "";
    autoResize(csInput);

    csSendButton.disabled = true;

    addCsLoadingMessage();

    try {

        const response = await fetch(
            CS_STREAM_API_URL,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: text,
                    customer_id: CS_CUSTOMER_ID,
                    thread_id: csThreadId
                })
            }
        );

        if (!response.ok) {
            let detail = `Request failed (HTTP ${response.status})`;
            try {
                const errorBody = await response.json();
                if (errorBody.detail) detail = errorBody.detail;
            } catch (_) {
                // Keep the status-based message when the body is not JSON.
            }
            throw new Error(detail);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let data = null;
        let streamedAnswer = "";
        let streamingMessage = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const blocks = buffer.split("\n\n");
            buffer = blocks.pop();

            for (const block of blocks) {
                if (!block.trim()) continue;
                const message = parseSseBlock(block);
                if (message.event === "status") {
                    updateLoadingMessage(message.data.message);
                } else if (message.event === "answer_delta") {
                    if (!streamingMessage) {
                        removeCsLoadingMessage();
                        streamingMessage = addCsAssistantMessage("");
                    }
                    streamedAnswer += message.data.text || "";
                    streamingMessage.content.textContent = streamedAnswer;
                    scrollCsToBottom();
                } else if (message.event === "result") {
                    data = message.data;
                } else if (message.event === "error") {
                    throw new Error(message.data.message);
                }
            }
        }

        removeCsLoadingMessage();
        if (streamingMessage && data?.answer) {
            streamingMessage.content.textContent = data.answer;
        } else if (!streamingMessage) {
            addCsAssistantMessage(data?.answer || "고객센터 응답을 받지 못했습니다.");
        }

    }

    catch (error) {

        console.error("CS API Error:", error);

        removeCsLoadingMessage();

        addCsAssistantMessage(
            error.message || "고객센터 요청을 처리하지 못했습니다."
        );

    }

    finally {

        csIsLoading = false;

        csSendButton.disabled = false;

        csInput.focus();
    }
}


csSendButton.addEventListener(
    "click",
    () => {
        sendCsMessage(csInput.value);
    }
);


csInput.addEventListener(
    "keydown",
    (event) => {

        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendCsMessage(csInput.value);
        }

    }
);


customerServiceButton.addEventListener(
    "click",
    openCustomerService
);


// ==========================================================
// SEND BUTTONS
// ==========================================================

welcomeSendButton.addEventListener(
    "click",
    () => {

        sendMessage(
            welcomeInput.value
        );

    }
);


chatSendButton.addEventListener(
    "click",
    () => {

        sendMessage(
            chatInput.value
        );

    }
);


// ==========================================================
// ENTER SEND
// ==========================================================

function handleEnter(
    event,
    textarea
) {

    if (
        event.key === "Enter"
        &&
        !event.shiftKey
    ) {

        event.preventDefault();

        sendMessage(
            textarea.value
        );
    }
}


welcomeInput.addEventListener(
    "keydown",
    (event) => {

        handleEnter(
            event,
            welcomeInput
        );

    }
);


chatInput.addEventListener(
    "keydown",
    (event) => {

        handleEnter(
            event,
            chatInput
        );

    }
);


// ==========================================================
// NEW CHAT
// ==========================================================

newThreadButton.addEventListener(
    "click",
    resetChat
);


newChatTop.addEventListener(
    "click",
    resetChat
);


// ==========================================================
// INITIAL FOCUS
// ==========================================================

window.addEventListener(
    "load",
    () => {

        welcomeInput.focus();

    }
);


function statusCard(label, value, healthy) {
    const card = document.createElement("div");
    card.className = "status-card";
    const dot = document.createElement("span");
    dot.className = `status-dot ${healthy ? "healthy" : "unhealthy"}`;
    const title = document.createElement("strong");
    title.textContent = label;
    const detail = document.createElement("span");
    detail.textContent = value;
    card.append(dot, title, detail);
    return card;
}


async function loadSystemStatus() {
    statusGrid.replaceChildren(statusCard("Status", "Checking", true));
    try {
        const response = await fetch(HEALTH_URL);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        statusGrid.replaceChildren(
            statusCard("API", "Healthy", true),
            statusCard(
                "OpenSearch",
                data.opensearch.available
                    ? `${data.opensearch.cluster_status} · ${Number(data.opensearch.documents).toLocaleString("en-US")} documents`
                    : `Connection failed · ${data.opensearch.error || "unknown"}`,
                data.opensearch.available
            ),
            statusCard("Current Index", data.opensearch.index || "Not configured", data.opensearch.available),
            statusCard(
                "Local Catalog",
                data.catalog.embedded_ready ? `Embeddings ${data.catalog.embedded_size_mb}MB` : "No embeddings",
                data.catalog.normalized_ready && data.catalog.embedded_ready
            ),
            statusCard("LLM Writer", data.llm_writer_enabled ? "Enabled" : "Disabled · deterministic responses", true)
        );
        statusGrid.append(statusCard(
            "Embedding",
            data.embedding_model.ready
                ? `${data.embedding_model.model} · ready · ${data.embedding_model.cached_queries} cached`
                : data.embedding_model.warming
                    ? `${data.embedding_model.model} · warming up`
                    : `${data.embedding_model.model} · ${data.embedding_model.error || "not ready"}`,
            data.embedding_model.ready
        ));
    } catch (error) {
        statusGrid.replaceChildren(statusCard("API", `Status check failed · ${error.message}`, false));
    }
}


systemStatusButton.addEventListener("click", () => {
    statusModal.classList.remove("hidden");
    loadSystemStatus();
});
closeStatusButton.addEventListener("click", () => statusModal.classList.add("hidden"));
refreshStatusButton.addEventListener("click", loadSystemStatus);
statusModal.addEventListener("click", event => {
    if (event.target === statusModal) statusModal.classList.add("hidden");
});
