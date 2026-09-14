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
            return route.fulfill(
                status=200, headers=CORS, content_type="image/jpeg",
                body=SAMPLE_IMAGE.read_bytes(),
            )
        return route.fulfill(status=404, headers=CORS, body="")

    def _answer_search(self, route):
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
    assert page.locator(".card__pct").all_inner_texts() == [
        "100.0%", "75.0%", "50.0%", "17.2%", "0.0%",
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
    assert page.locator(".card__label").all_inner_texts() == ["CLOSEST", "MATCH"]


@pytest.mark.parametrize("count,label", [(1, "1 match"), (3, "3 matches")])
def test_result_count_is_pluralised(make_page, count, label):
    page, api, url = make_page()
    api.search_body = {"matches": [match(f"{i}.jpg", 0.2) for i in range(count)]}
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator("#results-count")).to_have_text(label)


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

    expect(page.locator("#api-status")).to_have_text("Registry ready · 78 brands indexed")
    expect(page.locator("#api-dot")).to_have_attribute("data-state", "ready")
    assert api.requests[0] == ("GET", f"{LOCAL_API}/")
    assert not api.urls(f"{LOCAL_API}/search"), "warm-up must not need a search to happen"


def test_unreachable_api_is_reported_as_asleep(make_page):
    page, api, url = make_page()
    api.health_ok = False
    page.goto(url)

    expect(page.locator("#api-status")).to_have_text(
        "Registry asleep — the first search will wake it"
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
    expect(message).to_contain_text("Waking the server")
    first = message.inner_text()
    page.wait_for_timeout(2200)
    assert message.inner_text() != first, "the elapsed counter should be ticking"

    api.release_search()
    expect(page.locator(".card")).to_have_count(1)

    # If the interval were still running it would overwrite the results.
    settled = page.inner_text("#results-list")
    page.wait_for_timeout(1500)
    assert page.inner_text("#results-list") == settled
    assert "Waking" not in settled


# ─── error surfacing ─────────────────────────────────────────────────────────


def test_api_rejection_shows_the_apis_own_message(make_page):
    """A 400 carries a human message (F16). It must reach the user, not be
    flattened into a generic connection failure."""
    page, api, url = make_page()
    api.search_status = 400
    api.search_body = {"detail": "That file could not be read as an image. Try a JPG or PNG."}
    page.goto(url)
    choose_file(page)
    search(page)

    error = page.locator(".results__message--error")
    expect(error).to_have_text("That file could not be read as an image. Try a JPG or PNG.")
    assert not api.urls(f"{PROD_API}/search"), "a 4xx is an answer, not a reason to retry elsewhere"


def test_all_endpoints_down_is_reported(make_page):
    page, api, url = make_page()
    api.local_reachable = False
    api.prod_reachable = False
    page.goto(url)
    choose_file(page)
    search(page)

    expect(page.locator(".results__message--error")).to_have_text("All API endpoints failed")
    assert api.urls(f"{LOCAL_API}/search") and api.urls(f"{PROD_API}/search"), \
        "both endpoints should have been tried before giving up"


def test_submitting_without_a_file_prompts_instead_of_calling_the_api(make_page):
    page, api, url = make_page()
    page.goto(url)
    search(page)      # no dependency on warm-up: click() already waits for the page

    expect(page.locator(".results__message--error")).to_contain_text("Choose an image first")
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
        "That is not an image file. Try a JPG or PNG."
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
