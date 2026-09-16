"""Real-browser tests for frontend/script.js.

Until these existed, four shipped features — F7 (API routing), F10 (similarity
maths), F14 (warm-up + waking message) and F17 (themes, drop zone) — were verified
only by hand. They run headless Chromium through Playwright's Python API, so they
need no Node toolchain and run under the same pytest as the backend.

Two rules every test here obeys:

* **No real network.** Every call to either API base is intercepted by FakeAPI and
  answered deterministically. Anything else that is not the local static server is
  aborted and recorded, and the fixture fails the test if that list is non-empty.
  These tests can never wake, load or depend on the Render service.
* **Behaviour, not implementation.** Assertions are on what the page renders and
  which requests it makes, so a refactor that keeps behaviour keeps the tests green.

Setup, once per machine:  python -m playwright install chromium
"""
import base64
import functools
import http.server
import json
import re
import socketserver
import threading
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "frontend"
SAMPLE_IMAGE = REPO_ROOT / "scraper" / "normalized" / "1.jpg"

LOCAL_API = "http://localhost:8000"
PROD_API = "https://brandmatch-api-1815.onrender.com"

CORS = {"Access-Control-Allow-Origin": "*"}


def match(filename, distance):
    """One /search match, shaped exactly as api/main.py returns it."""
    return {
        "filename": filename,
        "id": filename.rsplit(".", 1)[0],
        "distance": distance,
        "imageUrl": f"/images/{filename}",
    }


# ─── infrastructure ──────────────────────────────────────────────────────────


class FakeAPI:
    """Stands in for both API bases. Flags are read at request time, so a test can
    configure them after creating the page but before navigating."""

    def __init__(self, context, static_origin):
        self.static_origin = static_origin
        self.requests = []   # (method, url) for every API call the page makes
        self.escaped = []    # anything that tried to leave the sandbox

        self.local_reachable = True
        self.prod_reachable = True
        self.health_ok = True
        self.search_status = 200
        self.search_body = {"matches": [match("1.jpg", 0.0)]}
        self.hold_search = False
        self.search_raw_body = None   # when set, sent verbatim (e.g. invalid JSON)
        self.images_ok = True
        self._held = []

        # Playwright runs matching routes in REVERSE registration order, so the
        # catch-all guard is registered first and only sees what the API routes
        # below do not claim.
        context.route("**/*", self._guard)
        context.route(lambda url: url.startswith(LOCAL_API), self._handle)
        context.route(lambda url: url.startswith(PROD_API), self._handle)

    def _guard(self, route):
        if route.request.url.startswith(self.static_origin):
            return route.continue_()
        self.escaped.append(route.request.url)
        return route.abort()

    def _handle(self, route):
        request = route.request
        self.requests.append((request.method, request.url))

        if request.url.startswith(LOCAL_API) and not self.local_reachable:
            return route.abort("connectionrefused")
        if request.url.startswith(PROD_API) and not self.prod_reachable:
            return route.abort("connectionrefused")

        path = urlparse(request.url).path
        if path == "/":
            if not self.health_ok:
                return route.abort("connectionrefused")
            return route.fulfill(
                status=200, headers=CORS, content_type="application/json",
                body=json.dumps({"status": "ok", "indexed": 78}),
            )
        if path == "/search":
            if self.hold_search:
                self._held.append(route)   # answered later by release_search()
                return None
            return self._answer_search(route)
        if path.startswith("/images/"):
            if not self.images_ok:
                return route.fulfill(status=404, headers=CORS, body="")
            return route.fulfill(
                status=200, headers=CORS, content_type="image/jpeg",
                body=SAMPLE_IMAGE.read_bytes(),
            )
        return route.fulfill(status=404, headers=CORS, body="")

    def _answer_search(self, route):
        if self.search_raw_body is not None:
            return route.fulfill(status=self.search_status, headers=CORS,
                                 content_type="application/json", body=self.search_raw_body)
        return route.fulfill(
            status=self.search_status, headers=CORS, content_type="application/json",
            body=json.dumps(self.search_body),
        )

    def release_search(self):
        assert self._held, "no search request is being held"
        self._answer_search(self._held.pop(0))

    def urls(self, prefix=""):
        return [url for _, url in self.requests if url.startswith(prefix)]


@pytest.fixture(scope="session")
def static_port():
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(FRONTEND))
    )
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def make_page(browser, static_port):
    """Returns (page, api, url). Configure `api`, then `page.goto(url)`.

    host="localhost" exercises the local-dev branch of F7; any other hostname —
    "app.localhost" resolves to loopback in Chromium — exercises the deployed one.
    """
    opened = []

    def _make(host="localhost", color_scheme="light"):
        context = browser.new_context(color_scheme=color_scheme)
        origin = f"http://{host}:{static_port}"
        api = FakeAPI(context, static_origin=origin)
        page = context.new_page()
        opened.append((context, api))
        return page, api, f"{origin}/"

    yield _make

    for context, api in opened:
        context.close()
        if api.escaped:
            pytest.fail(f"page made requests outside the sandbox: {api.escaped}")


def choose_file(page, path=SAMPLE_IMAGE):
    page.set_input_files("#image-input", str(path))


def search(page):
    page.click("button[type=submit]")


def drop(page, name, mime, data):
    """Dispatch a genuine drop event carrying a File, as a user's drag would."""
    transfer = page.evaluate_handle(
        """([name, mime, b64]) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const dt = new DataTransfer();
            dt.items.add(new File([bytes], name, { type: mime }));
            return dt;
        }""",
        [name, mime, base64.b64encode(data).decode()],
    )
    page.dispatch_event("#drop-zone", "drop", {"dataTransfer": transfer})


def css_var(page, name):
    return page.evaluate(
        "n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()", name
    )


# ─── F10: similarity maths ───────────────────────────────────────────────────


def test_percentages_convert_squared_l2_not_cosine(make_page):
    """Chroma returns squared-L2 distances in [0, 2]. The page must render
    (1 - d/2) * 100. The formula this replaced, (1 - d) * 100, gives
    100 / 50 / 0 / -65.6 / -100 for these inputs — so every row below fails
    loudly if that bug comes back."""
    page, api, url = make_page()
    api.search_body = {"matches": [
        match("a.jpg", 0.0),
        match("b.jpg", 0.5),
        match("c.jpg", 1.0),
        match("d.jpg", 1.6564),   # the worst real pair in the committed index
        match("e.jpg", 2.0),      # the theoretical bound
    ]}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(5)
    # es-CO formatting: decimal comma.
    assert page.locator(".card__pct").all_inner_texts() == [
        "100,0%", "75,0%", "50,0%", "17,2%", "0,0%",
    ]


def test_meter_width_tracks_the_percentage(make_page):
    page, api, url = make_page()
    api.search_body = {"matches": [match("a.jpg", 0.5), match("b.jpg", 2.0)]}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(2)
    widths = page.eval_on_selector_all(".card__meter span", "els => els.map(e => e.style.width)")
    assert widths == ["75%", "0%"]


def test_first_result_is_marked_closest(make_page):
    page, api, url = make_page()
    api.search_body = {"matches": [match("a.jpg", 0.1), match("b.jpg", 0.9)]}
    page.goto(url)
    choose_file(page)
    search(page)

    cards = page.locator(".card")
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_have_class(re.compile(r"\bcard--top\b"))
    expect(cards.nth(1)).not_to_have_class(re.compile(r"\bcard--top\b"))
    assert page.locator(".card__label").all_inner_texts() == ["MÁS SIMILAR", "CANDIDATO"]


@pytest.mark.parametrize("count,label", [(1, "1 resultado"), (3, "3 resultados")])
def test_result_count_is_pluralised(make_page, count, label):
    page, api, url = make_page()
    api.search_body = {"matches": [match(f"{i}.jpg", 0.2) for i in range(count)]}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator("#results-count")).to_have_text(label)


# ─── F20: untrusted text renders as text ─────────────────────────────────────
#
# Filenames, image URLs and API error messages all originate outside the page.
# Today they come from a committed index and fixed server strings, but M1/M3 let
# people upload files with names they choose — at which point string-built HTML
# becomes cross-site scripting. Each test below plants a payload that would run
# script or add attributes if it were parsed as HTML.

PAYLOAD_TAG = "<img src=x onerror=window.__pwned=1>"


def _event_handler_attributes(page):
    """Every on* attribute anywhere in the results. Legitimate rendering adds none."""
    return page.eval_on_selector_all(
        "#results-list *",
        "els => els.flatMap(e => e.getAttributeNames().filter(n => n.startsWith('on')))",
    )


def _pwned(page):
    page.wait_for_timeout(600)          # give an injected onerror time to fire
    return page.evaluate("window.__pwned !== undefined")


def test_filename_containing_html_renders_as_text(make_page):
    page, api, url = make_page()
    filename = f"{PAYLOAD_TAG}.jpg"
    api.search_body = {"matches": [match(filename, 0.2)]}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(1)
    expect(page.locator(".card__name")).to_have_text(filename)
    assert page.locator(".card img").count() == 1, "the payload must not become a second <img>"
    assert _event_handler_attributes(page) == []
    assert not _pwned(page)


def test_quotes_in_a_filename_cannot_break_out_of_attributes(make_page):
    page, api, url = make_page()
    filename = 'x" onmouseover="window.__pwned=1" data-x="y.jpg'
    api.search_body = {"matches": [match(filename, 0.2)]}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(1)
    assert page.get_attribute(".card img", "alt") == filename
    assert page.get_attribute(".card__name", "title") == filename
    assert _event_handler_attributes(page) == []
    page.hover(".card__name")
    page.hover(".card__plate")
    assert not _pwned(page)


def test_image_url_cannot_break_out_of_src(make_page):
    page, api, url = make_page()
    api.search_body = {"matches": [{
        "filename": "a.jpg", "id": "a", "distance": 0.2,
        "imageUrl": '/images/a.jpg" onerror="window.__pwned=1',
    }]}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(1)
    assert _event_handler_attributes(page) == []
    assert not _pwned(page)


def test_api_error_detail_containing_html_renders_as_text(make_page):
    page, api, url = make_page()
    detail = f'<b id="injected">bad</b> {PAYLOAD_TAG}'
    api.search_status = 400
    api.search_body = {"detail": detail}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".results__message--error")).to_have_text(detail)
    assert page.locator("#injected").count() == 0
    assert page.locator("#results-list img").count() == 0
    assert not _pwned(page)


def test_script_never_builds_html_from_strings():
    """The behavioural tests above prove today's payloads are harmless. This guards
    the code paths they do not reach yet: F23 puts owner names and farms into these
    same cards, and the easy mistake is a template literal assigned to innerHTML.
    Use textContent, DOM properties or setAttribute instead."""
    source = (FRONTEND / "script.js").read_text()
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in code, f"script.js uses {sink}; build nodes instead"


# ─── F21: the interface is in Spanish ───────────────────────────────────────
#
# ICA's staff read this. Every string a user can see — or a screen reader can
# announce — must be Spanish in every state the page can reach, not just the
# landing view. Checked by hunting for the English copy it replaced.

ENGLISH_COPY = [
    r"Cattle Brand Search", r"Switch between light and dark", r"Vector image search",
    r"Find the brand", r"behind the iron", r"Drop in a cattle brand", r"Drop an image",
    r"browse your files", r"Search settings", r"Number of matches", r"Find matches",
    r"high-contrast shape", r"Connecting to the registry", r"\bResults\b",
    r"will appear here", r"image similarity over", r"Registry ready", r"brands indexed",
    r"Registry asleep", r"Searching the registry", r"Waking the server", r"\belapsed\b",
    r"stays fast", r"not an image file", r"Choose an image", r"\bClosest\b", r"\bMatch\b",
    r"\bmatch(es)?\b", r"Image unavailable", r"No matches found", r"Request rejected",
    r"endpoints failed", r"Try a JPG", r"Unexpected token", r"Failed to fetch",
]


def _all_user_text(page):
    """Visible text, the document title, and every aria-label."""
    return page.evaluate("""() => [
        document.title,
        document.body.innerText,
        ...[...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label')),
    ].join('\\n')""")


def _assert_spanish(page, state):
    text = _all_user_text(page)
    leftovers = [p for p in ENGLISH_COPY if re.search(p, text)]
    assert not leftovers, f"English left in state '{state}': {leftovers}"
    assert "Ã" not in text and "�" not in text, f"mojibake in state '{state}'"


def _state_waking(page, api):
    api.health_ok = False
    api.hold_search = True


def _state_results(page, api):
    api.search_body = {"matches": [match("a.jpg", 0.1), match("b.jpg", 0.7)]}


def _state_image_unavailable(page, api):
    api.images_ok = False


def _state_no_matches(page, api):
    api.search_body = {"matches": []}


def _state_all_endpoints_down(page, api):
    api.local_reachable = False
    api.prod_reachable = False


def _state_unreadable_response(page, api):
    api.search_raw_body = "<html>not json</html>"


def _state_rejection_without_text(page, api):
    api.search_status = 422
    api.search_body = {"detail": [{"loc": ["body", "file"], "msg": "Field required"}]}


SEARCH_STATES = {
    "results": (_state_results, lambda page: expect(page.locator(".card")).to_have_count(2)),
    "image unavailable": (_state_image_unavailable,
                          lambda page: expect(page.locator(".card__missing")).to_have_count(1)),
    # The in-progress "Buscando…" message shares the .results__message class, so
    # waiting for that class alone checks the wrong message. A finished message is
    # the only one without the elapsed-time <small>.
    "no matches": (_state_no_matches, lambda page: page.wait_for_function(
        """() => { const m = document.querySelector('#results-list .results__message');
                   return m && !m.querySelector('small'); }""")),
    "all endpoints down": (_state_all_endpoints_down,
                           lambda page: expect(page.locator(".results__message--error")).to_be_visible()),
    "unreadable response": (_state_unreadable_response,
                            lambda page: expect(page.locator(".results__message--error")).to_be_visible()),
    "rejection without text": (_state_rejection_without_text,
                               lambda page: expect(page.locator(".results__message--error")).to_be_visible()),
    "waking": (_state_waking,
               lambda page: expect(page.locator(".results__message small")).to_be_visible()),
}


def test_document_language_is_colombian_spanish(make_page):
    page, api, url = make_page()
    page.goto(url)
    assert page.get_attribute("html", "lang") == "es-CO"


@pytest.mark.parametrize("state,dot", [("registry ready", "ready"), ("registry asleep", "down")])
def test_page_without_a_search_is_spanish(make_page, state, dot):
    page, api, url = make_page()
    api.health_ok = dot == "ready"
    page.goto(url)
    expect(page.locator("#api-dot")).to_have_attribute("data-state", dot)
    _assert_spanish(page, state)


@pytest.mark.parametrize("state", list(SEARCH_STATES))
def test_every_search_outcome_is_spanish(make_page, state):
    configure, settled = SEARCH_STATES[state]
    page, api, url = make_page()
    configure(page, api)
    page.goto(url)
    choose_file(page)
    search(page)
    settled(page)
    _assert_spanish(page, state)


@pytest.mark.parametrize("state", ["no file", "not an image"])
def test_every_input_error_is_spanish(make_page, state):
    page, api, url = make_page()
    page.goto(url)
    if state == "no file":
        search(page)
    else:
        drop(page, "notes.txt", "text/plain", b"not an image")
    expect(page.locator(".results__message--error")).to_be_visible()
    _assert_spanish(page, state)


def test_unexpected_failures_do_not_leak_browser_english(make_page):
    """A response that is not JSON makes the browser throw its own English message
    ('Unexpected token…'). The user must see a Spanish sentence instead."""
    page, api, url = make_page()
    api.search_raw_body = "<html>not json</html>"
    page.goto(url)
    choose_file(page)
    search(page)
    expect(page.locator(".results__message--error")).to_have_text(
        "No se pudo completar la búsqueda. Intente de nuevo."
    )


def test_rejection_without_a_readable_message_falls_back_to_spanish(make_page):
    """FastAPI's own validation errors carry a list, not a sentence. Showing it
    would print '[object Object]'."""
    page, api, url = make_page()
    api.search_status = 422
    api.search_body = {"detail": [{"loc": ["body", "file"], "msg": "Field required"}]}
    page.goto(url)
    choose_file(page)
    search(page)
    expect(page.locator(".results__message--error")).to_have_text(
        "La solicitud fue rechazada (422)."
    )


def test_accented_text_renders_correctly(make_page):
    page, api, url = make_page()
    api.search_body = {"matches": [match("a.jpg", 0.1)]}
    page.goto(url)
    assert "Búsqueda" in page.title()
    expect(page.locator(".hero__title")).to_contain_text("detrás")
    choose_file(page)
    search(page)
    # to_have_text reads the DOM text; CSS uppercases it only when rendered, which
    # test_first_result_is_marked_closest checks through inner_text.
    expect(page.locator(".card__label")).to_have_text("Más similar")
    assert page.inner_text(".card__label") == "MÁS SIMILAR"


# ─── F7: which API the page talks to ─────────────────────────────────────────


def test_local_page_uses_the_local_api(make_page):
    page, api, url = make_page(host="localhost")
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(1)
    assert api.urls(LOCAL_API), "a localhost page should call the local API"
    assert not api.urls(PROD_API), "the local API answered, so production must not be touched"


def test_local_page_falls_back_to_production(make_page):
    """With no local API running, developing against the deployed one still works."""
    page, api, url = make_page(host="localhost")
    api.local_reachable = False
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(1)
    assert api.urls(f"{PROD_API}/search")
    image_src = page.get_attribute(".card img", "src")
    assert image_src.startswith(PROD_API), "thumbnails must come from the API that answered"


def test_deployed_page_never_requests_localhost(make_page):
    """The F7 bug: every production search used to begin with a request to
    localhost:8000 that could not possibly succeed."""
    page, api, url = make_page(host="app.localhost")
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".card")).to_have_count(1)
    assert api.urls(PROD_API)
    assert not api.urls(LOCAL_API), f"deployed page contacted localhost: {api.urls(LOCAL_API)}"


# ─── F14: warm-up and the waking message ─────────────────────────────────────


def test_warm_up_fires_on_load_before_any_search(make_page):
    page, api, url = make_page()
    page.goto(url)

    expect(page.locator("#api-status")).to_have_text("Registro listo · 78 hierros registrados")
    expect(page.locator("#api-dot")).to_have_attribute("data-state", "ready")
    assert api.requests[0] == ("GET", f"{LOCAL_API}/")
    assert not api.urls(f"{LOCAL_API}/search"), "warm-up must not need a search to happen"


def test_unreachable_api_is_reported_as_asleep(make_page):
    page, api, url = make_page()
    api.health_ok = False
    page.goto(url)

    expect(page.locator("#api-status")).to_have_text(
        "Registro en reposo — la primera búsqueda lo activará"
    )
    expect(page.locator("#api-dot")).to_have_attribute("data-state", "down")


def test_cold_search_shows_a_ticking_wake_message_that_stops(make_page):
    page, api, url = make_page()
    api.health_ok = False       # the server is asleep: warm-up cannot reach it
    api.hold_search = True      # and the search is still in flight
    page.goto(url)
    choose_file(page)
    search(page)

    message = page.locator("#results-list .results__message")
    expect(message).to_contain_text("Activando el servidor")
    first = message.inner_text()
    page.wait_for_timeout(2200)
    assert message.inner_text() != first, "the elapsed counter should be ticking"

    api.release_search()
    expect(page.locator(".card")).to_have_count(1)

    # If the interval were still running it would overwrite the results.
    settled = page.inner_text("#results-list")
    page.wait_for_timeout(1500)
    assert page.inner_text("#results-list") == settled
    assert "Activando" not in settled


# ─── error surfacing ─────────────────────────────────────────────────────────


def test_api_rejection_shows_the_apis_own_message(make_page):
    """A 400 carries a human message (F16). It must reach the user, not be
    flattened into a generic connection failure."""
    page, api, url = make_page()
    api.search_status = 400
    api.search_body = {"detail": "No se pudo leer el archivo como imagen. Use un JPG o PNG."}
    page.goto(url)
    choose_file(page)
    search(page)

    error = page.locator(".results__message--error")
    expect(error).to_have_text("No se pudo leer el archivo como imagen. Use un JPG o PNG.")
    assert not api.urls(f"{PROD_API}/search"), "a 4xx is an answer, not a reason to retry elsewhere"


def test_all_endpoints_down_is_reported(make_page):
    page, api, url = make_page()
    api.local_reachable = False
    api.prod_reachable = False
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".results__message--error")).to_have_text(
        "No fue posible conectar con el servidor. Intente de nuevo en unos minutos."
    )
    assert api.urls(f"{LOCAL_API}/search") and api.urls(f"{PROD_API}/search"), \
        "both endpoints should have been tried before giving up"


def test_submitting_without_a_file_prompts_instead_of_calling_the_api(make_page):
    page, api, url = make_page()
    page.goto(url)
    search(page)      # no dependency on warm-up: click() already waits for the page

    expect(page.locator(".results__message--error")).to_contain_text("Primero elija una imagen")
    assert not api.urls(f"{LOCAL_API}/search")


# ─── F17: themes ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scheme,background,body_rgb",
    [("light", "#F7F4EC", "rgb(247, 244, 236)"), ("dark", "#111A15", "rgb(17, 26, 21)")],
)
def test_theme_follows_the_os_by_default(make_page, scheme, background, body_rgb):
    page, api, url = make_page(color_scheme=scheme)
    page.goto(url)

    assert page.evaluate("document.documentElement.getAttribute('data-theme')") is None
    assert css_var(page, "--bg") == background
    # The token alone is not enough — the page has to actually use it.
    expect(page.locator("body")).to_have_css("background-color", body_rgb)


def test_toggle_switches_theme_and_icon(make_page):
    page, api, url = make_page(color_scheme="light")
    page.goto(url)
    expect(page.locator(".theme-toggle__sun")).to_be_visible()

    page.click("#theme-toggle")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    assert css_var(page, "--bg") == "#111A15"
    expect(page.locator("body")).to_have_css("background-color", "rgb(17, 26, 21)")
    expect(page.locator(".theme-toggle__moon")).to_be_visible()
    expect(page.locator(".theme-toggle__sun")).to_be_hidden()

    page.click("#theme-toggle")
    assert css_var(page, "--bg") == "#F7F4EC"


def test_theme_choice_survives_reload_and_beats_the_os(make_page):
    page, api, url = make_page(color_scheme="dark")
    page.goto(url)
    page.click("#theme-toggle")                 # OS says dark, user picks light

    page.reload()
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"
    assert css_var(page, "--bg") == "#F7F4EC"
    expect(page.locator("body")).to_have_css("background-color", "rgb(247, 244, 236)")


def test_theme_is_applied_before_the_main_script_runs(make_page):
    """The inline <head> script sets the stored theme before first paint, so a
    returning visitor never sees a flash of the wrong one."""
    page, api, url = make_page(color_scheme="dark")
    page.goto(url)
    page.evaluate("localStorage.setItem('brandmatch-theme', 'light')")

    page.route("**/script.js*", lambda route: route.abort())   # main script never loads
    page.reload()
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"


# ─── F17: drop zone ──────────────────────────────────────────────────────────


def test_dropping_an_image_loads_it(make_page):
    page, api, url = make_page()
    page.goto(url)
    drop(page, "dropped-brand.jpg", "image/jpeg", SAMPLE_IMAGE.read_bytes())

    expect(page.locator("#drop-zone")).to_have_class(re.compile(r"\bhas-image\b"))
    expect(page.locator("#file-name")).to_have_text("dropped-brand.jpg")
    expect(page.locator("#drop-prompt")).to_be_hidden()
    assert page.evaluate("document.getElementById('image-input').files.length") == 1
    assert page.get_attribute("#preview-image", "src").startswith("blob:")


def test_dropped_file_is_what_gets_searched(make_page):
    """The drop must feed the real <input>, or the form would submit nothing."""
    page, api, url = make_page()
    page.goto(url)
    drop(page, "dropped-brand.jpg", "image/jpeg", SAMPLE_IMAGE.read_bytes())
    search(page)

    expect(page.locator(".card")).to_have_count(1)
    assert api.urls(f"{LOCAL_API}/search")


def test_dragging_over_highlights_and_leaving_clears(make_page):
    page, api, url = make_page()
    page.goto(url)
    zone = page.locator("#drop-zone")

    page.dispatch_event("#drop-zone", "dragenter")
    expect(zone).to_have_class(re.compile(r"\bis-dragging\b"))
    page.dispatch_event("#drop-zone", "dragleave")
    expect(zone).not_to_have_class(re.compile(r"\bis-dragging\b"))


def test_dropping_a_non_image_is_rejected(make_page):
    page, api, url = make_page()
    page.goto(url)
    drop(page, "notes.txt", "text/plain", b"not an image")

    expect(page.locator(".results__message--error")).to_have_text(
        "Ese archivo no es una imagen. Use un JPG o PNG."
    )
    expect(page.locator("#drop-zone")).not_to_have_class(re.compile(r"\bhas-image\b"))
    assert page.evaluate("document.getElementById('image-input').files.length") == 0


def test_choosing_through_the_file_picker_still_works(make_page):
    page, api, url = make_page()
    page.goto(url)
    choose_file(page)

    expect(page.locator("#file-name")).to_have_text("1.jpg")
    expect(page.locator("#drop-zone")).to_have_class(re.compile(r"\bhas-image\b"))


# ─── deploy hygiene ──────────────────────────────────────────────────────────


def test_assets_are_cache_busted():
    """Without a version query, a returning visitor gets new markup with a cached
    old stylesheet and sees an unstyled page. This happened during F17 testing."""
    html = (FRONTEND / "index.html").read_text()
    assert re.search(r'href="styles\.css\?v=[^"]+"', html)
    assert re.search(r'src="script\.js\?v=[^"]+"', html)
