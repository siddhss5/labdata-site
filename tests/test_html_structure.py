"""Structural checks on every HTML page of the demo site, built with the theme.

Each check is a property read from the markup alone: one <h1> and no skipped
heading level going down, an alt on every <img>, a lang on <html>, a non-empty
<title>, no id used twice, and a name on every link (its text, an aria-label, an
aria-labelledby or the alt of an image inside it). Each check also has a test
that it fails on a small page that breaks it.

Skipped when Bundler or the pinned Jekyll is not installed.
"""

from html.parser import HTMLParser

import pytest

from test_site_build import build, demo_data


class Structure(HTMLParser):
    """Collects what the checks read from one page."""

    def __init__(self):
        super().__init__()
        self.lang = None
        self.title = None
        self.headings = []
        self.images_without_alt = []
        self.nameless_links = []
        self.ids = []
        self._link = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "html":
            self.lang = attrs.get("lang")
        elif tag == "title" and self.title is None:
            self._in_title, self.title = True, ""
        elif len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
            self.headings.append(int(tag[1]))
        elif tag == "img":
            if "alt" not in attrs:
                self.images_without_alt.append(attrs.get("src"))
            elif self._link is not None:
                self._link["name"] += attrs["alt"] or ""
        if tag == "a" and "href" in attrs:
            self._link = {"href": attrs["href"], "name": " ".join(
                attrs.get(a) or "" for a in ("aria-label", "aria-labelledby"))}

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._link is not None:
            if not self._link["name"].strip():
                self.nameless_links.append(self._link["href"])
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._link is not None:
            self._link["name"] += data


def problems(text):
    """The structural problems in one page, as short messages."""
    page = Structure()
    page.feed(text)
    page.close()
    found = []
    if page.headings.count(1) != 1:
        found.append(f"{page.headings.count(1)} <h1> elements")
    previous = 0
    for level in page.headings:
        if level > previous + 1:
            found.append(f"<h{level}> follows <h{previous}>" if previous else f"<h{level}> before any <h1>")
        previous = level
    found += [f"<img> without alt: {src}" for src in page.images_without_alt]
    if not (page.lang or "").strip():
        found.append("<html> without lang")
    if not (page.title or "").strip():
        found.append("no <title> text")
    found += [f"link without a name: {href}" for href in page.nameless_links]
    found += [f"id used {page.ids.count(i)} times: {i}"
              for i in sorted(set(page.ids)) if page.ids.count(i) > 1]
    return found


def wrap(body, lang=' lang="en"', title="<title>T</title>"):
    return f"<!doctype html><html{lang}><head>{title}</head><body>{body}</body></html>"


GOOD = wrap('<h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2>'
            '<img src="a.png" alt=""><a href="/x">Text</a>'
            '<a href="/y" aria-label="Named"><i class="icon"></i></a>'
            '<a href="/z"><img src="i.png" alt="Image name"></a>'
            '<a id="anchor-without-href"></a>')


def test_good_page_has_no_problems():
    assert problems(GOOD) == []


@pytest.mark.parametrize("text, expected", [
    (wrap("<p>No heading</p>"), "0 <h1> elements"),
    (wrap("<h1>A</h1><h1>B</h1>"), "2 <h1> elements"),
    (wrap("<h1>A</h1><h3>C</h3>"), "<h3> follows <h1>"),
    (wrap("<h2>B</h2><h1>A</h1>"), "<h2> before any <h1>"),
    (wrap('<h1>A</h1><img src="a.png">'), "<img> without alt: a.png"),
    (wrap("<h1>A</h1>", lang=""), "<html> without lang"),
    (wrap("<h1>A</h1>", lang=' lang=""'), "<html> without lang"),
    (wrap("<h1>A</h1>", title=""), "no <title> text"),
    (wrap("<h1>A</h1>", title="<title> </title>"), "no <title> text"),
    (wrap('<h1>A</h1><a href="/x"></a>'), "link without a name: /x"),
    (wrap('<h1>A</h1><a href="/x"><i class="icon"></i> </a>'), "link without a name: /x"),
    (wrap('<h1>A</h1><a href="/x"><img src="i.png" alt=""></a>'), "link without a name: /x"),
    (wrap('<h1 id="a">A</h1><h2 id="a">B</h2>'), "id used 2 times: a"),
])
def test_each_check_fails_on_a_page_that_breaks_it(text, expected):
    assert problems(text) == [expected]


@pytest.fixture(scope="module")
def themed_demo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("themed")
    return build(tmp, *demo_data(tmp), theme=True)


def test_every_demo_page_is_structurally_sound(themed_demo):
    pages = sorted(themed_demo.rglob("*.html"))
    # Entity pages, the indexes, the co-author graph and the works list.
    assert len(pages) > 40
    for path in ["coauthors", "coauthor-graph", "publications", "people", "projects"]:
        assert themed_demo / path / "index.html" in pages, path
    failures = {str(p.relative_to(themed_demo)): problems(p.read_text(encoding="utf-8"))
                for p in pages}
    assert {p: f for p, f in failures.items() if f} == {}
