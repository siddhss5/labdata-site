"""Build the Jekyll site from a fixture data file and check the HTML it writes.

The fixture is the demo document the pinned sslabdata emits, with strings
that carry HTML and Markdown and links that cover each origin and verification
status put in place of the demo's; tests that need other hostile input change
fields of the same document. The site
is copied to a temporary directory with the fixture as `_data/lab.yml` and
built with the pinned gems (`site/Gemfile.lock`). The theme is switched off so
the checks cover only this repository. In its place a stub `single` layout
prints the page title and the navigation from `_data/navigation.yml`, which
it filters as `_includes/masthead.html` does, the two values the theme's
layout takes from this repository; the other checks are on
page content, which the theme does not produce.

Before each build, scripts/generate_pages.py writes the entity pages from the
data file. The same build is also run on the demo document the pinned
sslabdata emits, to check which of its links are shown and that its entity
pages link each relationship both ways. The demo is also built once with the
theme, to check that no page loads anything from another host.

Skipped when Bundler or the pinned Jekyll is not installed.
"""

import copy
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml


REPO_ROOT = Path(__file__).parent.parent
SITE = REPO_ROOT / "site"
GEMFILE = SITE / "Gemfile"

SCRIPT_TITLE = "<script>alert(1)</script> and a tidy kitchen"
NOTE = "*emphasis* & <b>bold</b>"
PERSON_NAME = "*Ada* <i>Lovelace</i>"

# A bio with surrounding whitespace and two paragraphs, separated by blank
# lines one of which holds only spaces; its first paragraph has a line break.
# It carries HTML, Markdown, kramdown typography and Liquid, all text.
BIO = ('\n  First line with <b>bold</b>, *stars* & [a link](https://bio.invalid/)  \n'
       'second line {{ site.title }} {% if true %}liquid{% endif %} -- "quoted"\n'
       '\n   \n\n'
       '<script>alert(5)</script> Second paragraph.\n')
BIO_PARAGRAPHS = [["First line with <b>bold</b>, *stars* & [a link](https://bio.invalid/)",
                   'second line {{ site.title }} {% if true %}liquid{% endif %} -- "quoted"'],
                  ["<script>alert(5)</script> Second paragraph."]]
# A bio of whitespace alone, which has no paragraph.
BLANK_BIO_PERSON = "ccote"

# Earlier roles the fixture gives. The PI's are a chain before the current
# professor role, oldest first, with a degree and a thesis where one was
# finished and a co-advisor on one; ADA's one earlier role carries HTML,
# Markdown, kramdown typography and Liquid in every string, and a start year
# alone.
PI_EARLIER = [
    {"role": "undergrad", "start_year": 2004, "end_year": 2008, "degree": "BS",
     "thesis_title": "Sorting Socks by Touch", "co_advisor": None},
    {"role": "phd_student", "start_year": 2008, "end_year": 2013, "degree": "PhD",
     "thesis_title": "Planning for Tidy Kitchens", "co_advisor": "Carl Coe"},
    {"role": "postdoc", "start_year": 2013, "end_year": 2015, "degree": None,
     "thesis_title": None, "co_advisor": None},
]
PI_EARLIER_SHOWN = [
    ["Undergrad, 2004–2008", "Degree: BS", "Thesis: Sorting Socks by Touch"],
    ["Phd Student, 2008–2013", "Degree: PhD", "Thesis: Planning for Tidy Kitchens",
     "Co-advisor: Carl Coe"],
    ["Postdoc, 2013–2015"],
]
ADA_EARLIER = [
    {"role": "<b>intern</b>_*x*_{{ site.title }}", "start_year": 2019, "end_year": None,
     "degree": " <i>MS</i> ", "thesis_title": "*Thesis* [y](https://earlier.invalid/) "
     "{% if true %}liquid{% endif %}", "co_advisor": '<u>Co</u> -- "quoted"'},
]
ADA_EARLIER_SHOWN = [
    ["<b>intern</b> *x* {{ site.title }}, from 2019", "Degree: <i>MS</i>",
     "Thesis: *Thesis* [y](https://earlier.invalid/) {% if true %}liquid{% endif %}",
     'Co-advisor: <u>Co</u> -- "quoted"'],
]
# A person whose `earlier_roles` is [].
NO_EARLIER_PERSON = "ddavis"

# Derived links: DOI and arXiv are built from a declared identifier; a PDF is
# guessed from a pattern.
DOI_UNCHECKED = "https://doi-derived.invalid/10.1/x"
ARXIV_UNCHECKED = "https://arxiv-derived.invalid/abs/2401.00001"
PDF_UNCHECKED = "https://pdf-unchecked.invalid/script2024.pdf"
PDF_MISSING = "https://pdf-missing.invalid/missing2024.pdf"
PDF_VERIFIED = "https://pdf-verified.invalid/plain2024.pdf"
SIDECAR_UNCHECKED = "https://sidecar-unchecked.invalid/abs/1"
INPUT_UNCHECKED = "https://input-unchecked.invalid/talk"
INPUT_VERIFIED = "https://input-verified.invalid/talk"
INPUT_MISSING = "https://input-missing.invalid/talk"
INPUT_MISSING_WEB = "https://input-missing.invalid/site"

# A photo is a file of the site or an http or https URL; any other value is
# not shown.
PHOTO_RELATIVE = "assets/people/ada.png"
PHOTO_ABSOLUTE = "https://photo.invalid/pi.png"
BAD_PHOTOS = {"ccote": "javascript:alert(3)", "ddavis": "mailto:photo@mail.invalid",
              "eevans": "//photo-host.invalid/x.png", "hhughes": "\\\\photo-host.invalid\\x.png",
              "jjones": "data:image/png;base64,AAAA"}

# A project's image follows the same rules as a photo. The demo gives
# PROJECT a file of the site; the fixture gives the other two projects an
# http(s) URL and a URL that is not shown.
IMAGE_ABSOLUTE = "https://image.invalid/legged.png"
BAD_IMAGE = "javascript:alert(4)"

# Only http, https and mailto become links; anything else is not rendered.
BAD_URLS = ["javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=",
            "vbscript:msgbox(1)", "JaVaScRiPt:alert(2)", "relative/page.html"]
GOOD_URLS = ["http://http.invalid/", "https://https.invalid/", "mailto:ada@mail.invalid"]


def link(url, origin, status):
    return {"url": url, "label": None, "origin": origin,
            "verification": {"status": status}}


# Entities of the demo document that the fixture gives hostile values.
SCRIPT, PLAIN, MISSING = "brown2025tidy", "davis2025handover", "fischer2025benchmark"
ADA, PI, PROJECT, COLLAB = "bbrown", "aadams", "homebot", "trent-turner-62d45583"
# A person the fixture adds with no works, as a new member would have.
NEWCOMER = "newcomer"
# A role written as Markdown, which a group titled from it must print as text.
# Its URL is not one of BAD_URLS, which no page may contain even as text.
MARKDOWN_ROLE = "[x](javascript:alert(document.domain)) **b**"

# Awards the fixture adds. SCRIPT has several, one given in a year other than
# the work's; the hostile one holds HTML, Markdown, kramdown typography and
# Liquid. MISSING has one with no year.
AWARD_HOSTILE = ('Best <b>Paper</b> *Award* [x](https://award.invalid/) -- "quoted" '
                 '{{ site.title }} {% if true %}liquid{% endif %}')
FIXTURE_AWARDS = {
    SCRIPT: [{"name": AWARD_HOSTILE, "year": 2025}, {"name": "Test of Time Award", "year": 2035},
             {"name": "Audience Choice Award", "year": 2025}],
    PLAIN: [{"name": "A Systems Paper Award", "year": 2025}],
    MISSING: [{"name": "Honourable Mention", "year": None}],
}


def fixture_document(document):
    """The demo document the pinned sslabdata emits, with its strings, links
    and URLs replaced by hostile input and some roles changed so that the
    People page groups cover roles a fixed list would drop."""
    works = {w["bib_id"]: w for w in document["works"]}
    people = {p["id"]: p for p in document["people"]}
    projects = {x["id"]: x for x in document["projects"]}
    coauthors = {c["key"]: c for c in document["collaborators"]}
    document["lab"].update({"name": "Fixture <Lab>", "department": "*Dept*",
                            "university": "U & U", "description": "<b>desc</b>",
                            "website": GOOD_URLS[0], "github": BAD_URLS[3], "youtube": BAD_URLS[1]})
    for bib_id, title, note, links in [
        (SCRIPT, SCRIPT_TITLE, NOTE, {
            "pdf": [link(PDF_UNCHECKED, "derived", "unchecked")],
            "doi": [link(DOI_UNCHECKED, "derived", "unchecked")],
            "arxiv": [link(SIDECAR_UNCHECKED, "sidecar", "unchecked"),
                      link(ARXIV_UNCHECKED, "derived", "unchecked")],
            "video": [link(INPUT_UNCHECKED, "input", "unchecked")],
            "url": [link(BAD_URLS[0], "input", "unchecked")]}),
        (PLAIN, "A plain title", None, {
            "pdf": [link(PDF_VERIFIED, "derived", "verified")],
            "doi": [link(GOOD_URLS[1], "derived", "unchecked")],
            "url": [link(INPUT_VERIFIED, "input", "verified")],
            "video": [link(INPUT_VERIFIED, "input", "verified")]}),
        (MISSING, "An input link nobody found", None, {
            "pdf": [link(PDF_MISSING, "derived", "missing")],
            "url": [link(INPUT_MISSING_WEB, "input", "missing")],
            "video": [link(INPUT_MISSING, "input", "missing")]}),
    ]:
        works[bib_id].update({"title": title, "note": note, "links": links,
                              "category": "<b>Journal</b> Papers",
                              "abstract": "An abstract with <img src=x onerror=alert(2)>."})
        works[bib_id]["venue"]["name"] = "*Journal* <em>of</em> Tests"
    for bib_id, awards in FIXTURE_AWARDS.items():
        works[bib_id]["awards"] = awards
    for w in works.values():
        for a in w["authors"]:
            if a["person_id"] == ADA:
                a["name"] = PERSON_NAME
            if a["collaborator_key"] == COLLAB:
                a["name"] = "<u>Grace</u> Hopper"
    people[ADA].update({"name": PERSON_NAME, "thesis_title": "*Thesis* <b>x</b>",
                        "co_advisor": "<i>Someone</i>", "website": BAD_URLS[2],
                        "photo": PHOTO_RELATIVE})
    people[PI].update({"name": "<b>The</b> *PI*", "website": GOOD_URLS[2], "photo": PHOTO_ABSOLUTE})
    people[ADA]["bio"] = BIO
    people[PI]["earlier_roles"] = PI_EARLIER
    people[ADA]["earlier_roles"] = ADA_EARLIER
    people[PI]["bio"] = None
    people[BLANK_BIO_PERSON]["bio"] = " \n\n  \t\n"
    for person_id, photo in BAD_PHOTOS.items():
        people[person_id]["photo"] = photo
    # Roles a fixed list of groups would drop, and a professor among the alumni.
    people["ffischer"]["role"] = "engineer"
    people["ggreen"]["role"] = "visiting_scholar"
    people["iingram"]["role"] = "professor"
    document["people"].append({**people["eevans"], "id": NEWCOMER, "name": "Nadia Newcomer",
                               "work_ids": []})
    document["people"].append({**people["eevans"], "id": "markdownrole", "name": "Mark Down",
                               "role": MARKDOWN_ROLE, "work_ids": []})
    projects[PROJECT].update({"title": "*Project* <b>One</b>",
                              "description": "Project _description_ <script>x</script>",
                              "status": "active", "website": BAD_URLS[4]})
    # Work counts the Projects page words differently: one work and none.
    projects["legged"]["work_ids"] = projects["legged"]["work_ids"][:1]
    projects["sharedcontrol"]["work_ids"] = []
    projects["legged"]["image"] = IMAGE_ABSOLUTE
    projects["sharedcontrol"]["image"] = BAD_IMAGE
    coauthors[COLLAB]["name"] = "<b>Collab</b> *Orator*"
    return document


# People groups for the fixture build. `professor` and `engineer` are each
# named twice; `visiting_scholar` and the other roles are not named.
PEOPLE_GROUPS = [{"title": "Faculty", "roles": ["professor"]},
                 {"title": "Research Staff", "roles": ["engineer", "professor"]},
                 {"title": "Engineers", "roles": ["engineer"]}]


# The title is filtered as the theme's seo.html and single.html filter it.
STUB_LAYOUT = """<!doctype html>
<title>{{ page.title | markdownify | strip_html | strip_newlines | escape_once }}</title>
<nav>{% for item in site.data.navigation.main %}{% assign first_char = item.url | slice: 0 %}{% if first_char == "/" %}{% assign target = site.pages | where: "url", item.url | first %}{% unless target %}{% continue %}{% endunless %}{% endif %}<a href="{{ item.url | relative_url }}">{{ item.title | escape }}</a>{% endfor %}</nav>
<h1 class="page-title">{{ page.title | markdownify | remove: "<p>" | remove: "</p>" | strip }}</h1>
{{ content }}
"""


def missing_tool(reason):
    """Skip for a missing tool, or fail if SITE_REQUIRE_TOOLS=1, as CI sets it."""
    if os.environ.get("SITE_REQUIRE_TOOLS") == "1":
        pytest.fail(reason + " (SITE_REQUIRE_TOOLS=1)")
    pytest.skip(reason)


def _jekyll_available():
    if shutil.which("bundle") is None:
        return False
    env = dict(os.environ, BUNDLE_GEMFILE=str(GEMFILE))
    result = subprocess.run(["bundle", "exec", "jekyll", "--version"],
                            capture_output=True, env=env, cwd=SITE)
    return result.returncode == 0


def build(tmp, data, people_groups=None, theme=False, site_config=None):
    """Build a copy of site/ with `data` as _data/lab.yml; return the output.
    `site_config`, a file such as generate_site_config.py writes, is read last."""
    if not _jekyll_available():
        missing_tool("bundle exec jekyll is not available")
    source = tmp / "site"
    shutil.copytree(SITE, source, ignore=shutil.ignore_patterns(
        "_site", ".jekyll-cache", ".jekyll-metadata", ".bundle", "vendor",
        "lab.yml", "_config.generated.yml", "_entities"))
    (source / "_data" / "lab.yml").write_text(data, encoding="utf-8")
    subprocess.run([sys.executable, "scripts/generate_pages.py", source / "_data" / "lab.yml",
                    source / "_entities"], check=True, cwd=REPO_ROOT)
    if not theme:
        # Drop the theme, whose layouts these checks do not cover; a later
        # config file cannot unset it.
        config = source / "_config.yml"
        lines = config.read_text(encoding="utf-8").splitlines(keepends=True)
        config.write_text("".join(l for l in lines if not l.startswith("theme:")),
                          encoding="utf-8")
        (source / "_layouts").mkdir()
        (source / "_layouts" / "single.html").write_text(STUB_LAYOUT, encoding="utf-8")
    (source / "_config.test.yml").write_text(
        "title: Fixture\nurl: https://fixture.invalid\nbaseurl: ''\n"
        "repository: fixture/fixture\n" +
        (yaml.safe_dump({"people_groups": people_groups}) if people_groups else ""),
        encoding="utf-8")
    dest = tmp / "_site"
    env = dict(os.environ, BUNDLE_GEMFILE=str(GEMFILE), BUNDLE_FROZEN="true",
               JEKYLL_ENV="production")
    result = subprocess.run(
        ["bundle", "exec", "jekyll", "build", "--source", str(source),
         "--destination", str(dest),
         "--config", ",".join(str(c) for c in [source / "_config.yml", source / "_config.test.yml",
                                                  site_config] if c)],
        capture_output=True, text=True, env=env, cwd=SITE)
    assert result.returncode == 0, result.stdout + result.stderr
    return dest


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build(tmp_path_factory.mktemp("site"),
                 yaml.safe_dump(FIXTURE, allow_unicode=True), PEOPLE_GROUPS)


@pytest.fixture(scope="module")
def unconfigured(tmp_path_factory):
    """The fixture built with no people_groups at all."""
    return build(tmp_path_factory.mktemp("unconfigured"),
                 yaml.safe_dump(FIXTURE, allow_unicode=True))


def demo_data(tmp):
    """The demo document the pinned sslabdata emits, as text, and the
    people_groups generate_site_config.py writes from demo/lab.yaml."""
    data = tmp / "lab.yml"
    result = subprocess.run(
        [str(Path(sys.executable).parent / "sslabdata"), "--config", "demo/lab.yaml",
         "--output", str(data)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    config = tmp / "_config.generated.yml"
    subprocess.run([sys.executable, "scripts/generate_site_config.py", "demo/lab.yaml", config],
                   check=True, cwd=REPO_ROOT)
    people_groups = yaml.safe_load(config.read_text(encoding="utf-8"))["people_groups"]
    return data.read_text(encoding="utf-8"), people_groups


with tempfile.TemporaryDirectory() as _tmp:
    FIXTURE = fixture_document(yaml.safe_load(demo_data(Path(_tmp))[0]))


def irregular_document(document):
    """The fixture with values sslabdata emits with only a warning: people with
    no role (`role: null`) and with a status other than current or alumni,
    among people whose role is "other", the title of the no-role group."""
    document = copy.deepcopy(document)
    people = {p["id"]: p for p in document["people"]}
    for person_id in ["ccote", "jjones", "nnolan"]:
        people[person_id]["role"] = None
    for person_id in ["eevans", "iingram"]:
        people[person_id]["role"] = "other"
    people["ddavis"]["status"] = "former"
    people["nnolan"]["status"] = "former"
    people["hhughes"]["status"] = None
    return document


IRREGULAR = irregular_document(FIXTURE)


@pytest.fixture(scope="module")
def irregular(tmp_path_factory):
    return build(tmp_path_factory.mktemp("irregular"),
                 yaml.safe_dump(IRREGULAR, allow_unicode=True), PEOPLE_GROUPS)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """The site built from the demo document the pinned sslabdata emits."""
    tmp = tmp_path_factory.mktemp("demo")
    data, people_groups = demo_data(tmp)
    return build(tmp, data, people_groups), yaml.safe_load(data)


def page(built, path):
    return (built / path / "index.html").read_text(encoding="utf-8")


def all_html(built):
    return "\n".join(p.read_text(encoding="utf-8") for p in built.rglob("*.html"))


PAGES = ["", "publications", "projects"]
# The pages above that list works; the Projects page lists projects only.
WORK_LISTS = ["", "publications"]


@pytest.mark.parametrize("path", WORK_LISTS)
def test_title_is_literal_text(built, path):
    html = page(built, path)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; and a tidy kitchen" in html
    assert "<script>alert(1)</script>" not in html


@pytest.mark.parametrize("path", WORK_LISTS)
def test_note_is_plain_text_not_markdown(built, path):
    html = page(built, path)
    assert "*emphasis* &amp; &lt;b&gt;bold&lt;/b&gt;" in html
    assert "<em>emphasis</em>" not in html
    assert "<b>bold</b>" not in html


def test_no_markup_from_data_reaches_the_site(built):
    html = all_html(built)
    for raw in ["<script>x</script>", "<b>", "<i>", "<u>", "<em>of</em>",
                "<img src=x", "<em>Ada</em>", "<em>Dept</em>", "<em>PI</em>",
                "<em>Project</em>", "<em>description</em>", "<em>Thesis</em>",
                "<em>Orator</em>", "<em>Journal</em>", "<Lab>"]:
        assert raw not in html, raw
    for literal in ["*Ada* &lt;i&gt;Lovelace&lt;/i&gt;", "*Thesis* &lt;b&gt;x&lt;/b&gt;",
                    "&lt;b&gt;The&lt;/b&gt; *PI*", "*Project* &lt;b&gt;One&lt;/b&gt;",
                    "Project _description_ &lt;script&gt;x&lt;/script&gt;",
                    "&lt;b&gt;Collab&lt;/b&gt; *Orator*", "*Journal* &lt;em&gt;of&lt;/em&gt; Tests",
                    "&lt;b&gt;Journal&lt;/b&gt; Papers", "Fixture &lt;Lab&gt;"]:
        assert literal in html, literal


@pytest.mark.parametrize("url", [PDF_UNCHECKED, PDF_MISSING, SIDECAR_UNCHECKED])
def test_unverified_guessed_and_other_origin_links_are_not_rendered(built, url):
    for p in built.rglob("*"):
        if p.is_file():
            assert url not in p.read_text(encoding="utf-8", errors="replace"), p


@pytest.mark.parametrize("path", ["", "publications"])
def test_identifier_links_are_rendered_without_label(built, path):
    """Derived DOI and arXiv links are rendered though unchecked, unlabelled."""
    html = page(built, path)
    for url, text in [(DOI_UNCHECKED, "DOI"), (ARXIV_UNCHECKED, "arXiv")]:
        anchor = f'<a href="{url}" class="btn btn--inverse btn--small" target="_blank">{text}</a>'
        assert anchor in html, text
        assert anchor + " <small" not in html, text


def test_verified_guessed_link_is_rendered_without_label(built):
    for path, anchor in [
        ("publications", f'<a href="{PDF_VERIFIED}" class="btn btn--inverse btn--small" target="_blank">PDF</a>'),
        (f"publications/{PLAIN}", f'<a href="{PDF_VERIFIED}" class="btn btn--inverse btn--small" target="_blank">PDF</a>'),
    ]:
        html = page(built, path)
        assert anchor in html, path
        assert anchor + " <small" not in html, path


@pytest.mark.parametrize("path", ["", "publications", f"people/{PI}", f"projects/{PROJECT}",
                                  f"publications/{PLAIN}"])
def test_work_with_a_pdf_shows_a_pdf_button_and_its_title_links_to_its_page(built, path):
    html = page(built, path)
    assert f'<strong><a href="/publications/{PLAIN}/">A plain title</a></strong>' in html
    assert f'<a href="{PDF_VERIFIED}" class="btn btn--inverse btn--small" target="_blank">PDF</a>' in html


def test_unverified_input_link_is_shown_as_it_is(built):
    for path, anchor in [
        ("publications", f'<a href="{INPUT_UNCHECKED}" class="btn btn--inverse btn--small" target="_blank">Video</a>'),
    ]:
        html = page(built, path)
        assert anchor in html, path
        assert anchor + " <small" not in html, path


def test_missing_input_link_is_shown_as_it_is(built):
    for path, anchors in [
        ("publications", [f'<a href="{INPUT_MISSING_WEB}" class="btn btn--inverse btn--small" target="_blank">Website</a>',
                          f'<a href="{INPUT_MISSING}" class="btn btn--inverse btn--small" target="_blank">Video</a>']),
        (f"publications/{MISSING}", [f'<a href="{INPUT_MISSING_WEB}" class="btn btn--inverse btn--small" target="_blank">Website</a>']),
    ]:
        html = page(built, path)
        for anchor in anchors:
            assert anchor in html, path
            assert anchor + " <small" not in html, path
        assert "(missing)" not in html, path


@pytest.mark.parametrize("site", ["built", "demo"])
def test_no_page_labels_a_link_unchecked(site, request):
    built = request.getfixturevalue(site)
    built = built[0] if site == "demo" else built
    assert "(unchecked)" not in all_html(built)


def test_verified_input_link_has_no_label(built):
    for path, attrs in [("publications", 'class="btn btn--inverse btn--small" target="_blank"'),
                        (f"publications/{PLAIN}", 'class="btn btn--inverse btn--small" target="_blank"')]:
        html = page(built, path)
        for text in ["Website", "Video"]:
            anchor = f'<a href="{INPUT_VERIFIED}" {attrs}>{text}</a>'
            assert anchor in html, (path, text)
            assert anchor + " <small" not in html, (path, text)


def test_photos_are_site_files_or_http_urls_with_the_name_as_alt(built):
    ada = f'<img src="/{PHOTO_RELATIVE}" alt="*Ada* &lt;i&gt;Lovelace&lt;/i&gt;"'
    pi = f'<img src="{PHOTO_ABSOLUTE}" alt="&lt;b&gt;The&lt;/b&gt; *PI*"'
    assert re.findall(r'<img src="([^"]*)"', page(built, "people")) == [PHOTO_ABSOLUTE, f"/{PHOTO_RELATIVE}"]
    assert ada in page(built, "people") and ada in page(built, f"people/{ADA}")
    assert pi in page(built, "people") and pi in page(built, f"people/{PI}")
    text = all_html(built)
    for person_id, photo in BAD_PHOTOS.items():
        assert "<img" not in page(built, f"people/{person_id}"), person_id
        assert photo not in text and "photo-host.invalid" not in text, photo


def test_project_images_are_site_files_or_http_urls_with_the_title_as_alt(built):
    projects = {x["id"]: x for x in FIXTURE["projects"]}
    entries = project_entries(built)
    for project_id, src in [(PROJECT, f"/{projects[PROJECT]['image']}"), ("legged", IMAGE_ABSOLUTE)]:
        img = f'<img src="{src}" alt="{html.escape(projects[project_id]["title"])}"'
        assert img in entries[project_id], project_id
        assert img in page(built, f"projects/{project_id}"), project_id
    assert "<img" not in entries["sharedcontrol"]
    assert "<img" not in page(built, "projects/sharedcontrol")
    assert BAD_IMAGE not in all_html(built)


def test_only_http_https_and_mailto_urls_become_links(built):
    html = all_html(built)
    for url in BAD_URLS:
        assert url not in html, url
    for url in GOOD_URLS:
        assert f'href="{url}"' in html, url
    targets = re.findall(r'(?:href|src)="([^"]*)"', html)
    assert all(t.startswith(("http://", "https://", "mailto:", "/")) for t in targets), targets


def test_works_not_publications(built):
    html = all_html(built)
    assert "Publications" not in html
    works = page(built, "publications")
    assert "<title>Works</title>" in works
    assert '<h1 class="page-title">Works</h1>' in works
    for path in PAGES + ["people"]:
        assert '<a href="/publications/">Works</a>' in page(built, path), path
    assert "Recent Works" in page(built, "")
    project = next(x for x in FIXTURE["projects"] if x["id"] == PROJECT)
    assert f"<p>{len(project['work_ids'])} works</p>" in page(built, "projects")


def test_demo_shows_identifier_links_and_hides_guessed_pdfs(demo):
    built, document = demo
    html = all_html(built)
    links = [(kind, l) for w in document["works"]
             for kind, records in (w.get("links") or {}).items() for l in records
             if l["origin"] != "input"]
    by_kind = {kind: [l for k, l in links if k == kind] for kind in ("doi", "arxiv", "pdf")}
    # The pinned sslabdata builds all three as derived and unchecked, except
    # a PDF the entry names in its own `pdf` field.
    assert all(l["origin"] == "derived" and l["verification"]["status"] == "unchecked"
               for records in by_kind.values() for l in records)
    assert by_kind["doi"] and by_kind["arxiv"] and by_kind["pdf"]
    for kind, text in [("doi", "DOI"), ("arxiv", "arXiv")]:
        for l in by_kind[kind]:
            anchor = f'<a href="{l["url"]}" class="btn btn--inverse btn--small" target="_blank">{text}</a>'
            assert anchor in html, l["url"]
            assert anchor + " <small" not in html, l["url"]
    for l in by_kind["pdf"]:
        assert l["url"] not in html, l["url"]


def test_demo_work_with_a_pdf_field_shows_a_pdf_button_to_it(demo):
    built, document = demo
    named = [(w, l) for w in document["works"] for l in (w.get("links") or {}).get("pdf") or []
             if l["origin"] == "input"]
    assert [l["url"] for _, l in named] == ["https://example.org/papers/cote2024pantry.pdf"]
    [(w, l)] = named
    anchor = f'<a href="{l["url"]}" class="btn btn--inverse btn--small" target="_blank">PDF</a>'
    title = f'<strong><a href="/publications/{w["bib_id"]}/">{html.escape(w["title"])}</a></strong>'
    for path in ["publications", f"publications/{w['bib_id']}", f"projects/{w['project_ids'][0]}"]:
        assert anchor in page(built, path), path
        assert title in page(built, path), path


def test_demo_work_websites_and_videos_are_on_the_works_list_and_work_pages(demo):
    """Every work's website and video is shown on the works list and on the
    work's page, and at least one work shows both."""
    built, document = demo
    shown = {}
    for w in document["works"]:
        # Each equal contributor is starred, then the note appears once.
        equal = [(html.escape(a["name"]), "") for a in w["authors"] if a.get("equal_contribution")]
        assert re.findall(r"([^<>]*)(?:</a>)?<sup>\*</sup>( equal contribution</span>)?",
                          page(built, f"publications/{w['bib_id']}")) == \
            equal + [(" &mdash; ", " equal contribution</span>")] * bool(equal), w["bib_id"]
        for kind, text in [("url", "Website"), ("video", "Video")]:
            for l in (w.get("links") or {}).get(kind) or []:
                # The demo's are written in the input and unchecked.
                assert l["origin"] == "input" and l["verification"]["status"] == "unchecked"
                anchor = (f'<a href="{html.escape(l["url"])}" class="btn btn--inverse btn--small" '
                          f'target="_blank">{text}</a>')
                for path in ["publications", f"publications/{w['bib_id']}"]:
                    assert anchor in page(built, path), (path, l["url"])
                shown.setdefault(w["bib_id"], set()).add(kind)
    assert len([i for i, kinds in shown.items() if "url" in kinds]) >= 2
    assert {"url", "video"} in shown.values()


def test_demo_photos_are_shown_with_the_name_as_alt(demo):
    built, document = demo
    with_photo = [p for p in document["people"] if p.get("photo")]
    assert len(with_photo) >= 3
    for p in with_photo:
        assert (built / p["photo"]).is_file(), p["photo"]
        img = f'<img src="/{p["photo"]}" alt="{html.escape(p["name"])}"'
        for path in ["people", f"people/{p['id']}"]:
            assert img in page(built, path), (path, p["id"])


def test_demo_project_images_are_shown_with_the_title_as_alt(demo):
    """Two demo projects have an image, shown on the Projects page and on
    their pages; the third has none, and no <img> stands in for it."""
    built, document = demo
    entries = project_entries(built)
    with_image = [x for x in document["projects"] if x.get("image")]
    assert len(with_image) == 2 and len(document["projects"]) == 3
    for x in document["projects"]:
        pages = [entries[x["id"]], page(built, f"projects/{x['id']}")]
        if x.get("image"):
            assert (built / x["image"]).is_file(), x["image"]
            img = f'<img src="/{x["image"]}" alt="{html.escape(x["title"])}"'
            assert all(img in text for text in pages), x["id"]
        else:
            assert all("<img" not in text for text in pages), x["id"]


def test_demo_entity_pages_link_both_ways(demo):
    """Every work, person, project and co-author has a page; each relationship
    in the data file is linked from both ends; every internal link resolves."""
    built, document = demo
    url = {"work": "/publications/{}/", "person": "/people/{}/",
           "project": "/projects/{}/", "coauthor": "/coauthors/{}/"}
    works = {w["bib_id"]: w for w in document["works"]}
    pages = [url["work"].format(i) for i in works]
    edges = set()
    for w in works.values():
        work = url["work"].format(w["bib_id"])
        for a in w["authors"]:
            edges.add((work, url["person"].format(a["person_id"]) if a["person_id"]
                       else url["coauthor"].format(a["collaborator_key"])))
        edges |= {(work, url["project"].format(i)) for i in w["project_ids"]}
    for kind, key, entities in [("person", "id", document["people"]),
                                ("project", "id", document["projects"]),
                                ("coauthor", "key", document["collaborators"])]:
        for e in entities:
            here = url[kind].format(e[key])
            pages.append(here)
            for wid in e["work_ids"]:
                edges.add((here, url["work"].format(wid)))
                for a in works[wid]["authors"]:
                    if kind == "person" and a["collaborator_key"]:
                        edges.add((here, url["coauthor"].format(a["collaborator_key"])))
                    if kind == "coauthor" and a["person_id"]:
                        edges.add((here, url["person"].format(a["person_id"])))
            edges |= {(here, url["person"].format(i)) for i in e.get("people_ids", [])}
    for p in pages:
        assert (built / p.strip("/") / "index.html").is_file(), p

    def links(path):
        return set(re.findall(r'href="(/[^"#]*)', (built / path.strip("/") / "index.html").read_text(encoding="utf-8")))

    for a, b in edges:
        assert b in links(a), (a, b)
        assert a in links(b), (b, a)
    for f in built.rglob("*.html"):
        for target in re.findall(r'href="(/[^"#]*)', f.read_text(encoding="utf-8")):
            assert (built / target.lstrip("/") / "index.html").is_file() or \
                (built / target.lstrip("/")).is_file(), (f, target)


def list_pages(document):
    """The pages that list works: the home page, the Works list, and every
    person, project and co-author page."""
    return (WORK_LISTS + [f"people/{p['id']}" for p in document["people"]]
            + [f"projects/{x['id']}" for x in document["projects"]]
            + [f"coauthors/{c['key']}" for c in document["collaborators"]])


@pytest.mark.parametrize("site", ["built", "demo"])
def test_list_pages_show_no_abstract_or_bibtex(site, request):
    built = request.getfixturevalue(site)
    built, document = built if site == "demo" else (built, FIXTURE)
    details = [w[f] for w in document["works"] for f in ("abstract", "bibtex") if w.get(f)]
    assert details
    for path in list_pages(document):
        text = page(built, path)
        assert "onclick" not in text and "<code" not in text and ">Details</a>" not in text, path
        for d in details:
            assert d not in html.unescape(text), path


@pytest.mark.parametrize("site", ["built", "demo"])
def test_work_pages_show_the_abstract_once_and_bibtex_in_details(site, request):
    """A work's page shows its abstract once, as text, and its BibTeX in a
    <details> element whose visible <summary> opens it without JavaScript."""
    built = request.getfixturevalue(site)
    built, document = built if site == "demo" else (built, FIXTURE)
    assert any(w.get("abstract") for w in document["works"])
    for w in document["works"]:
        text = page(built, f"publications/{w['bib_id']}")
        [(summary, body)] = re.findall(r"<details[^>]*>\s*<summary([^>]*)>BibTeX</summary>(.*?)</details>",
                                        text, re.S)
        if w.get("abstract"):
            # Once outside the BibTeX, which carries it as a field.
            assert html.unescape(text.replace(body, "")).count(w["abstract"]) == 1, w["bib_id"]
        assert "display: none" not in summary and "onclick" not in summary, w["bib_id"]
        assert w["bibtex"] in html.unescape(body), w["bib_id"]
        # The only script on the page is Copy's.
        assert text.count("onclick") == 1 and "Copy</button>" in body, w["bib_id"]


def project_entries(built):
    """Each entry of the Projects page, as its markup keyed by project id."""
    return dict(re.findall(r'<div id="([^"]+)" style="margin-top: 2.5em;">(.*?)</div>',
                           page(built, "projects"), re.S))


@pytest.mark.parametrize("site", ["built", "demo"])
def test_projects_page_lists_each_project_compactly(site, request):
    """Each project's title links to its page; its status is a label, not a
    link; a Website button shows only for an http, https or mailto website;
    the work count is text, omitted when zero. No work is listed."""
    built = request.getfixturevalue(site)
    built, document = built if site == "demo" else (built, FIXTURE)
    text = page(built, "projects")
    assert "<details" not in text and "pub-entry" not in text
    assert not re.search(r'href="/publications/[^"]+/"', text)
    entries = project_entries(built)
    assert list(entries) == [x["id"] for x in document["projects"]]
    websites, counts = set(), set()
    for x in document["projects"]:
        entry = entries[x["id"]]
        assert (built / "projects" / x["id"] / "index.html").is_file(), x["id"]
        assert (f'<h2 style="display: inline; margin-right: 0.5em;"><a href="/projects/{x["id"]}/">'
                f'{html.escape(x["title"])}</a></h2>') in entry, x["id"]
        status = "Active" if x["status"] == "active" else html.escape(x["status"].capitalize())
        kind = "success" if x["status"] == "active" else "secondary"
        assert f'<span class="btn btn--{kind} btn--small">{status}</span>' in entry, x["id"]
        assert not re.search(r"<a [^>]*btn--(success|secondary)", entry), x["id"]
        website = (x.get("website") or "").strip()
        safe = website.split(":")[0].lower() in ("http", "https", "mailto") and ":" in website
        websites.add("safe" if safe else "unsafe" if website else "missing")
        button = f'<a href="{html.escape(website)}" class="btn btn--inverse btn--small" target="_blank">Website</a>'
        assert (button in entry) == safe and entry.count(">Website</a>") == safe, x["id"]
        n = len(x["work_ids"])
        counts.add(min(n, 2))
        assert re.findall(r"\b\d+ works?\b", entry) == ([] if n == 0 else ["1 work"] if n == 1
                                                         else [f"{n} works"]), x["id"]
    # The fixture has a project for each case.
    if site == "built":
        assert websites == {"safe", "unsafe", "missing"} and counts == {0, 1, 2}


def assert_titled(text, name):
    """The page's title and heading are `name` as escaped text; returns the title."""
    title = re.search(r"<title>(.*)</title>", text)[1]
    heading = re.search(r'<h1 class="page-title">(.*)</h1>', text)[1]
    for shown in (title, heading):
        assert html.unescape(shown) == name and "<" not in shown, (shown, name)
    return title


def test_demo_entity_pages_are_titled_by_their_entity(demo):
    """Each entity page's title and heading are its entity's name, escaped, and
    no two pages of a kind share a title."""
    built, document = demo
    for path, key, name, entities in [("publications", "bib_id", "title", document["works"]),
                                      ("people", "id", "name", document["people"]),
                                      ("projects", "id", "title", document["projects"]),
                                      ("coauthors", "key", "name", document["collaborators"])]:
        titles = [assert_titled(page(built, f"{path}/{e[key]}"), e[name]) for e in entities]
        assert len(set(titles)) == len(titles) == len(entities), path


def test_fixture_entity_titles_are_literal_text(built):
    for path, name in [(f"people/{ADA}", PERSON_NAME), (f"publications/{SCRIPT}", SCRIPT_TITLE),
                       (f"projects/{PROJECT}", "*Project* <b>One</b>"),
                       (f"coauthors/{COLLAB}", "<b>Collab</b> *Orator*")]:
        assert_titled(page(built, path), name)


def test_demo_coauthor_pages_show_other_spellings_only_when_there_are_some(demo):
    built, document = demo
    for c in document["collaborators"]:
        text = page(built, f"coauthors/{c['key']}")
        assert "not a verified person" in text, c["name"]
        if len(c["name_variants"]) == 1:
            assert "Also written as" not in text, c["name"]
    priya = next(c for c in document["collaborators"] if c["name"] == "Priya Patel")
    assert "<p>Also written as P. Patel.</p>" in page(built, f"coauthors/{priya['key']}")


def test_demo_coauthor_index_links_every_coauthor(demo):
    built, document = demo
    text = page(built, "coauthors")
    assert "not a verified person" in text
    for c in document["collaborators"]:
        assert f'<a href="/coauthors/{c["key"]}/">{html.escape(c["name"])}</a>' in text, c["name"]


def people_sections(built):
    """The People page's headings, in order, each with the ids of the people under it."""
    text = page(built, "people").split("Collaborators")[0]
    sections = []
    for m in re.finditer(r'<h[23][^>]*>(.*?)</h[23]>|<span id="([^"]+)"><a href="/people/', text):
        if m[1] is not None:
            sections.append((html.unescape(m[1]), []))
        else:
            sections[-1][1].append(m[2])
    return sections


@pytest.mark.parametrize("site", ["built", "unconfigured", "demo", "irregular"])
def test_every_person_appears_exactly_once_on_the_people_page(site, request):
    built = request.getfixturevalue(site)
    if site == "demo":
        built, people = built[0], built[1]["people"]
    else:
        people = IRREGULAR["people"] if site == "irregular" else FIXTURE["people"]
    shown = [i for _, ids in people_sections(built) for i in ids]
    assert sorted(shown) == sorted(p["id"] for p in people)


def fixture_ids(status, role):
    return [p["id"] for p in FIXTURE["people"] if p["status"] == status and p["role"] == role]


def test_people_groups_title_and_order_and_show_each_role_once(built):
    ids = fixture_ids
    assert people_sections(built) == [
        ("Faculty", ids("current", "professor")), ("Research Staff", ids("current", "engineer")),
        ("Phd Student", ids("current", "phd_student")),
        ("Visiting Scholar", ids("current", "visiting_scholar")),
        (MARKDOWN_ROLE, ids("current", MARKDOWN_ROLE)),
        ("Alumni", []), ("Faculty", ids("alumni", "professor")),
        ("Phd Student", ids("alumni", "phd_student")), ("Postdoc", ids("alumni", "postdoc")),
        ("Ms Student", ids("alumni", "ms_student")),
    ]


def test_without_people_groups_each_role_is_titled_from_its_name(unconfigured):
    ids = fixture_ids
    assert people_sections(unconfigured) == [
        ("Professor", ids("current", "professor")), ("Phd Student", ids("current", "phd_student")),
        ("Engineer", ids("current", "engineer")),
        ("Visiting Scholar", ids("current", "visiting_scholar")),
        (MARKDOWN_ROLE, ids("current", MARKDOWN_ROLE)),
        ("Alumni", []), ("Professor", ids("alumni", "professor")),
        ("Phd Student", ids("alumni", "phd_student")), ("Postdoc", ids("alumni", "postdoc")),
        ("Ms Student", ids("alumni", "ms_student")),
    ]


@pytest.mark.parametrize("site", ["built", "unconfigured"])
def test_people_group_titled_from_a_markdown_role_is_text(site, request):
    """A group title is printed where kramdown does not read it: the role's
    Markdown link and emphasis are its heading's text, not markup."""
    text = page(request.getfixturevalue(site), "people")
    assert re.search(r'<h2[^>]*>' + re.escape(MARKDOWN_ROLE) + '</h2>', text)
    assert 'href="javascript:' not in text
    assert "<strong>" not in text


def test_people_with_no_role_or_another_status_are_in_titled_fallback_groups(irregular):
    """A person with no role is in one group, "Other", after the groups of
    their status's roles; a person whose status is neither current nor alumni
    is under "Other Members", after the alumni, grouped by role likewise."""
    def ids(role, statuses):
        return [p["id"] for p in IRREGULAR["people"] if p["role"] == role and p["status"] in statuses]

    sections = people_sections(irregular)
    titles = [t for t, _ in sections]
    assert all(titles)
    alumni, others = titles.index("Alumni"), titles.index("Other Members")
    assert alumni < others
    assert sections[alumni - 1] == ("Other", ids(None, ["current"]))
    assert sections[others - 1] == ("Other", ids(None, ["alumni"]))
    assert sections[-1] == ("Other", ids(None, ["former", None]))
    assert ("Phd Student", ids("phd_student", ["former", None])) in sections[others:]
    assert ("Postdoc", ids("postdoc", ["former", None])) in sections[others:]
    # The groups of the role "other" are titled "Other" too, before the fallback.
    assert ("Other", ids("other", ["current"])) in sections[:alumni - 1]
    assert ("Other", ids("other", ["alumni"])) in sections[alumni:others - 1]


def test_demo_people_page_groups(demo):
    built, document = demo

    def ids(status, role):
        return [p["id"] for p in document["people"] if p["status"] == status and p["role"] == role]

    assert people_sections(built) == [
        ("Principal Investigator", ids("current", "professor")),
        ("PhD Students", ids("current", "phd_student")),
        ("MS Students", ids("current", "ms_student")),
        ("Alumni", []),
        ("Postdocs", ids("alumni", "postdoc")),
        ("PhD Students", ids("alumni", "phd_student")),
        ("MS Students", ids("alumni", "ms_student")),
    ]


class Loads(HTMLParser):
    """URLs the page loads through src, srcset, imagesrcset, poster, <object
    data>, <link href> other than plain references, and CSS url() in style
    attributes and <style> elements; not CSS @import or SVG href."""

    REFERENCES = {"alternate", "canonical", "author", "license", "me"}

    def __init__(self):
        super().__init__()
        self.urls = []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.in_style = tag == "style"
        for name in ("src", "poster"):
            if attrs.get(name):
                self.urls.append(attrs[name])
        for name in ("srcset", "imagesrcset"):
            self.urls += [c.split()[0] for c in (attrs.get(name) or "").split(",") if c.strip()]
        if tag == "object" and attrs.get("data"):
            self.urls.append(attrs["data"])
        if tag == "link" and attrs.get("href") and \
                not set((attrs.get("rel") or "").lower().split()) <= self.REFERENCES:
            self.urls.append(attrs["href"])
        self.css(attrs.get("style") or "")

    def handle_data(self, data):
        if self.in_style:
            self.css(data)

    def handle_endtag(self, tag):
        self.in_style = False

    def css(self, text):
        self.urls += re.findall(r"url\(\s*['\"]?([^'\")]+)", text)


def test_demo_with_theme_loads_nothing_from_another_host(tmp_path):
    """Built with the theme, no demo page fetches a resource from a host other
    than the site's own, and none names an unpinned @latest version."""
    built = build(tmp_path, *demo_data(tmp_path), theme=True)
    pages = sorted(built.rglob("*.html"))
    assert pages
    for p in pages:
        text = p.read_text(encoding="utf-8")
        assert "@latest" not in text, p
        # The heading permalink icon Font Awesome drew is now CSS.
        assert 'class="page__content' not in text or ".header-link .fa-link::before" in text, p
        parser = Loads()
        parser.feed(text)
        foreign = [u for u in parser.urls
                   if urlsplit(u).netloc not in ("", "fixture.invalid")]
        assert foreign == [], p


# A lab name that closes an attribute and opens an element if printed unescaped.
LAB_NAME = """X"><img src=x onerror=alert(2)> 'Lab'"""


class FeedLinks(HTMLParser):
    """The title of each Atom feed <link>, and each <img> src, as parsed."""

    def __init__(self):
        super().__init__()
        self.titles = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("type") == "application/atom+xml":
            self.titles.append(attrs.get("title"))
        if tag == "img":
            self.images.append(attrs.get("src"))


def test_lab_name_is_text_in_the_feed_link_on_every_page(tmp_path):
    """Built with the theme and the config generate_site_config.py writes from
    a lab.yaml whose name holds quotes and angle brackets, every page's feed
    link is titled with the name as text, and no page has an element from it."""
    lab = yaml.safe_load((REPO_ROOT / "demo" / "lab.yaml").read_text(encoding="utf-8"))
    lab["lab"]["name"] = LAB_NAME
    lab["lab"]["description"] = LAB_NAME
    lab_yaml = tmp_path / "lab.yaml"
    lab_yaml.write_text(yaml.safe_dump(lab, allow_unicode=True), encoding="utf-8")
    config = tmp_path / "hostile.yml"
    subprocess.run([sys.executable, "scripts/generate_site_config.py", lab_yaml, config],
                   check=True, cwd=REPO_ROOT)
    data, _ = demo_data(tmp_path)
    built = build(tmp_path, data, theme=True, site_config=config)
    pages = sorted(built.rglob("*.html"))
    assert pages
    for p in pages:
        text = p.read_text(encoding="utf-8")
        parser = FeedLinks()
        parser.feed(text)
        assert parser.titles == [f"{LAB_NAME} Feed"], p
        assert "x" not in parser.images, p
        assert "<img src=x" not in text, p


class AwardsTable(HTMLParser):
    """Each row of a table as (year, award, link target, paper), as text."""

    def __init__(self):
        super().__init__()
        self.rows, self.cell, self.href = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag == "td":
            self.cell = ""
        elif tag == "a" and self.cell is not None:
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag == "td":
            self.rows[-1].append(self.cell)
            if len(self.rows[-1]) == 3:
                self.rows[-1].insert(2, self.href)
            self.cell = self.href = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data


def awards_rows(built):
    table = AwardsTable()
    table.feed(page(built, "awards"))
    return [tuple(r) for r in table.rows if r]


def award_labels(text):
    """The award labels of each work entry in `text`, keyed by the work its title links."""
    labels = {}
    for entry in text.split('<div class="pub-entry"')[1:]:
        bib_id = re.search(r'<a href="/publications/([^"]+)/">', entry)[1]
        labels[bib_id] = [html.unescape(l) for l in
                          re.findall(r'<span class="pub-award[^"]*"[^>]*>(.*?)</span>', entry, re.S)]
    return labels


def test_awards_page_lists_every_award_once_newest_first_linking_its_work(built):
    """Newest first; the undated award last; within a year, in the document's
    works order (SCRIPT before PLAIN, and cote2024pantry before
    brown2024blend, which neither name nor id order gives), then the order of
    the work's `awards`."""
    order = [w["bib_id"] for w in FIXTURE["works"]]
    assert order.index(SCRIPT) < order.index(PLAIN)
    assert order.index("cote2024pantry") < order.index("brown2024blend")
    rows = awards_rows(built)
    assert rows == [
        ("2035", "Test of Time Award", f"/publications/{SCRIPT}/", SCRIPT_TITLE),
        ("2025", AWARD_HOSTILE, f"/publications/{SCRIPT}/", SCRIPT_TITLE),
        ("2025", "Audience Choice Award", f"/publications/{SCRIPT}/", SCRIPT_TITLE),
        ("2025", "A Systems Paper Award", f"/publications/{PLAIN}/", "A plain title"),
        ("2024", "Best Paper Award", "/publications/cote2024pantry/",
         next(w["title"] for w in FIXTURE["works"] if w["bib_id"] == "cote2024pantry")),
        ("2024", "Best Student Paper Award Finalist", "/publications/brown2024blend/",
         next(w["title"] for w in FIXTURE["works"] if w["bib_id"] == "brown2024blend")),
        ("Undated", "Honourable Mention", f"/publications/{MISSING}/", "An input link nobody found"),
    ]
    assert len(rows) == sum(len(w["awards"]) for w in FIXTURE["works"])
    for _, _, href, _ in rows:
        assert (built / href.strip("/") / "index.html").is_file(), href


def test_award_text_is_escaped_and_never_markup(built):
    """The award's name is printed escaped wherever it is shown; its HTML,
    Markdown and Liquid are none of them read (the rows and labels, compared
    after unescaping, show that no typography was applied either)."""
    for path in ["awards", "publications", f"publications/{SCRIPT}"]:
        text = page(built, path)
        assert html.escape(AWARD_HOSTILE) in text, path
    for raw in ["<b>Paper</b>", "<em>Award</em>", 'href="https://award.invalid/']:
        assert raw not in all_html(built), raw


@pytest.mark.parametrize("path", ["publications", "", f"people/{ADA}", f"publications/{SCRIPT}",
                                  f"publications/{MISSING}"])
def test_awards_are_labels_on_work_entries_and_work_pages(built, path):
    """Each award is a label on its work's entry, as text; an award given in
    another year than the work's shows that year."""
    labels = award_labels(page(built, path))
    expected = {SCRIPT: [AWARD_HOSTILE, "Test of Time Award (2035)", "Audience Choice Award"],
                PLAIN: ["A Systems Paper Award"], MISSING: ["Honourable Mention"]}
    shown = {k: v for k, v in labels.items() if k in expected}
    assert shown, path
    for bib_id, names in shown.items():
        assert names == expected[bib_id], (path, bib_id)
    assert all(v == [] for k, v in labels.items()
               if not next(w for w in FIXTURE["works"] if w["bib_id"] == k)["awards"]), path


def test_demo_awards_are_on_the_awards_page_and_their_works(demo):
    built, document = demo
    awarded = [(w, a) for w in document["works"] for a in w["awards"]]
    assert len(awarded) == 2
    rows = awards_rows(built)
    assert rows == [(str(a["year"]), a["name"], f"/publications/{w['bib_id']}/", w["title"])
                    for w, a in awarded]
    for w, a in awarded:
        for path in ["publications", f"publications/{w['bib_id']}"]:
            assert award_labels(page(built, path))[w["bib_id"]] == [a["name"]], (path, w["bib_id"])


def test_navigation_links_the_awards_page_only_when_a_work_has_an_award(tmp_path):
    """Built with the theme, a lab with an award links /awards/ from every
    page's navigation; a lab with none has no Awards page and no link to one."""
    data, people_groups = demo_data(tmp_path)
    with_awards = build(tmp_path / "with", data, people_groups, theme=True)
    document = yaml.safe_load(data)
    for w in document["works"]:
        w["awards"] = []
    without = build(tmp_path / "without", yaml.safe_dump(document, allow_unicode=True),
                    people_groups, theme=True)
    assert (with_awards / "awards" / "index.html").is_file()
    for p in sorted(with_awards.rglob("*.html")):
        nav = re.search(r'<nav id="site-nav".*?</nav>', p.read_text(encoding="utf-8"), re.S)[0]
        assert re.search(r'<a\s+href="/awards/"\s*>Awards</a>', nav), p
    assert not (without / "awards").exists()
    for p in sorted(without.rglob("*")):
        if p.is_file():
            assert "/awards/" not in p.read_text(encoding="utf-8", errors="replace"), p


def bio_paragraphs(text):
    """The bio on a person page, as its paragraphs, each a list of its lines
    as text; None when the page shows no bio."""
    m = re.search(r'<div class="person-bio">(.*?)</div>', text, re.S)
    if m is None:
        return None
    return [[html.unescape(line) for line in p.split("<br>")]
            for p in re.findall(r"<p>(.*?)</p>", m[1], re.S)]


def test_a_bio_renders_as_paragraphs_of_lines(built):
    """Blank lines start a new paragraph, a single line break is a line break,
    and the whitespace around the bio and its lines is dropped."""
    assert bio_paragraphs(page(built, f"people/{ADA}")) == BIO_PARAGRAPHS


def test_bio_text_is_escaped_and_never_markup(built):
    """The bio's HTML, Markdown, Liquid and typography are text on the page."""
    text = page(built, f"people/{ADA}")
    for raw in ["<b>bold</b>", "<script>alert(5)", "<em>stars</em>", 'href="https://bio.invalid/',
                "&amp;amp;"]:
        assert raw not in all_html(built), raw
    for literal in ["&lt;b&gt;bold&lt;/b&gt;, *stars* &amp; [a link](https://bio.invalid/)",
                    "{{ site.title }} {% if true %}liquid{% endif %} -- &quot;quoted&quot;",
                    "&lt;script&gt;alert(5)&lt;/script&gt; Second paragraph."]:
        assert literal in text, literal


@pytest.mark.parametrize("person", [PI, BLANK_BIO_PERSON])
def test_a_null_or_blank_bio_renders_nothing(built, person):
    text = page(built, f"people/{person}")
    assert bio_paragraphs(text) is None
    assert "<p></p>" not in text


@pytest.mark.parametrize("site", ["built", "demo"])
def test_the_people_page_shows_no_bio(site, request):
    built = request.getfixturevalue(site)
    built = built[0] if site == "demo" else built
    text = page(built, "people")
    assert "person-bio" not in text
    assert "Second paragraph" not in text and "fictional PhD student" not in text


# Alumni with each combination of present and missing degree, start_year,
# end_year and current_position, and the line the documented rule gives
# each; None is no line. Blank strings count as missing, and strings are
# trimmed and escaped.
ALUMNI_LINES = [
    ("PhD", 2006, 2012, "Research Scientist at Facebook", "PhD 2012, now Research Scientist at Facebook"),
    ("PhD", 2006, 2012, None, "PhD 2012"),
    ("PhD", 2006, None, "Research Scientist at Facebook", "PhD, now Research Scientist at Facebook"),
    ("PhD", 2006, None, None, "PhD"),
    ("PhD", None, 2012, "Research Scientist at Facebook", "PhD 2012, now Research Scientist at Facebook"),
    ("PhD", None, 2012, None, "PhD 2012"),
    ("PhD", None, None, "Research Scientist at Facebook", "PhD, now Research Scientist at Facebook"),
    ("PhD", None, None, None, "PhD"),
    (None, 2019, 2020, "PhD at Cornell", "2019–2020, now PhD at Cornell"),
    (None, 2019, 2020, None, "2019–2020"),
    (None, 2019, None, "PhD at Cornell", "from 2019, now PhD at Cornell"),
    (None, 2019, None, None, "from 2019"),
    (None, None, 2020, "PhD at Cornell", "until 2020, now PhD at Cornell"),
    (None, None, 2020, None, "until 2020"),
    (None, None, None, "PhD at Cornell", "Now PhD at Cornell"),
    (None, None, None, None, None),
    (None, 2020, 2020, "PhD at Cornell", "2020, now PhD at Cornell"),
    (" ", 2019, 2020, "", "2019–2020"),
    ("  MS ", None, 2021, " Engineer ", "MS 2021, now Engineer"),
    ("<b>MS</b>", None, 2021, "*Engineer* & {{ site.title }}",
     "<b>MS</b> 2021, now *Engineer* & {{ site.title }}"),
]
ALUMNI_IDS = [f"alum{i}" for i in range(len(ALUMNI_LINES))]


# An earlier role whose every field differs from the last role's; the alumni
# line describes the last role only, so it is the same with or without it.
EARLIER_THAN_LAST = {"role": "ms_student", "start_year": 1990, "end_year": 1991, "degree": "MS",
                     "thesis_title": "An Earlier Thesis", "co_advisor": "Early Coe"}


def alumni_document(document):
    """The fixture with an alumnus for each of ALUMNI_LINES, alternately a
    PhD student and a postdoc, whose groups' tables differ, every third one
    with an earlier role, and a current member with every field the line is
    made from."""
    document = copy.deepcopy(document)
    for i, (degree, start, end, position, _) in enumerate(ALUMNI_LINES):
        document["people"].append({**document["people"][0], "id": ALUMNI_IDS[i], "name": f"Alum {i}",
                                   "role": ["phd_student", "postdoc"][i % 2], "status": "alumni",
                                   "degree": degree, "start_year": start, "end_year": end,
                                   "current_position": position, "bio": None, "work_ids": [],
                                   "earlier_roles": [EARLIER_THAN_LAST] if i % 3 == 0 else []})
    document["people"].append({**document["people"][0], "id": "stillhere", "name": "Still Here",
                               "role": "phd_student", "status": "current", "degree": "PhD",
                               "start_year": 2019, "end_year": 2020, "current_position": "Student",
                               "bio": None, "work_ids": []})
    return document


@pytest.fixture(scope="module")
def alumni(tmp_path_factory):
    return build(tmp_path_factory.mktemp("alumni"),
                 yaml.safe_dump(alumni_document(FIXTURE), allow_unicode=True), PEOPLE_GROUPS)


def alumni_lines(built, person_id):
    """The alumni line of `person_id` on the People page and on their own
    page, as text; None where there is none."""
    people = page(built, "people")
    row = re.search(rf'<span id="{re.escape(person_id)}">.*?</td>', people, re.S)[0]
    on_people = re.search(r'<span class="alumni-line">(.*?)</span>', row, re.S)
    on_page = re.search(r'<p class="alumni-line">(.*?)</p>', page(built, f"people/{person_id}"), re.S)
    return [html.unescape(m[1]) if m else None for m in (on_people, on_page)]


@pytest.mark.parametrize("person_id, line", zip(ALUMNI_IDS, [x[-1] for x in ALUMNI_LINES]),
                         ids=ALUMNI_IDS)
def test_alumni_line_follows_the_rule(alumni, person_id, line):
    assert alumni_lines(alumni, person_id) == [line, line]


def test_alumni_lines_are_escaped_and_never_markup(alumni):
    for raw in ["<b>MS</b>", "<em>Engineer</em>"]:
        assert raw not in all_html(alumni), raw


def test_a_current_member_has_no_alumni_line(alumni):
    assert alumni_lines(alumni, "stillhere") == [None, None]


def test_demo_bio_and_alumni_lines(demo):
    built, document = demo
    assert [p["id"] for p in document["people"] if p["bio"]] == [ADA]
    assert bio_paragraphs(page(built, f"people/{ADA}")) == [
        ["Bob Brown is a fictional PhD student in Example Lab, co-advised by Alice Adams and Peggy Park.",
         "He studies shared control for assistive robot arms."],
        ["Before joining the lab, he built kitchen robots that never existed."]]
    assert bio_paragraphs(page(built, f"people/{PI}")) is None
    assert {p["id"]: alumni_lines(built, p["id"]) for p in document["people"]
            if p["status"] == "alumni"} == {
        "hhughes": ["2018–2021, now Assistant Professor, Example State University"] * 2,
        "iingram": ["PhD 2022, now Research Scientist, Example Robotics Inc."] * 2,
        "jjones": ["PhD 2023, now Assistant Professor, Example Institute of Technology"] * 2,
        "nnolan": ["MS 2021, now Software Engineer, Example Automation"] * 2,
    }


def earlier_roles(text):
    """The earlier roles on a person page, each a list of its lines as text,
    in the order shown; None when the page shows no earlier roles."""
    m = re.search(r'<h2>Earlier roles</h2>\s*<ul class="earlier-roles">(.*?)</ul>', text, re.S)
    if m is None:
        assert "Earlier roles" not in text and "earlier-roles" not in text
        return None
    return [[html.unescape(line) for line in li.split("<br>")]
            for li in re.findall(r"<li>(.*?)</li>", m[1], re.S)]


def test_earlier_roles_are_listed_oldest_first_with_years_degree_and_thesis(built):
    """A chain of earlier roles before a professor shows each role, titled from
    its name, with its years, and its degree, thesis and co-advisor where given."""
    assert earlier_roles(page(built, f"people/{PI}")) == PI_EARLIER_SHOWN


def test_earlier_role_text_is_escaped_and_never_markup(built):
    """Every string of an earlier role is text: its HTML, Markdown, Liquid and
    typography are none of them read, and whitespace around it is dropped."""
    text = page(built, f"people/{ADA}")
    assert earlier_roles(text) == ADA_EARLIER_SHOWN
    for raw in ["<b>intern</b>", "<i>MS</i>", "<u>Co</u>", "<em>Thesis</em>", "<em>x</em>",
                'href="https://earlier.invalid/', "&amp;amp;", "&#8211;", "&ldquo;"]:
        assert raw not in all_html(built), raw


def test_no_earlier_roles_shows_nothing(built):
    person = next(p for p in FIXTURE["people"] if p["id"] == NO_EARLIER_PERSON)
    assert person["earlier_roles"] == []
    assert earlier_roles(page(built, f"people/{NO_EARLIER_PERSON}")) is None


@pytest.mark.parametrize("person_id", [i for n, i in enumerate(ALUMNI_IDS) if n % 3 == 0])
def test_earlier_roles_do_not_change_the_alumni_line(alumni, person_id):
    """An alumnus with an earlier role whose degree and years differ has the
    alumni line of their last role, and the earlier role on their page."""
    line = ALUMNI_LINES[ALUMNI_IDS.index(person_id)][-1]
    assert alumni_lines(alumni, person_id) == [line, line]
    assert earlier_roles(page(alumni, f"people/{person_id}")) == [
        ["Ms Student, 1990–1991", "Degree: MS", "Thesis: An Earlier Thesis", "Co-advisor: Early Coe"]]


@pytest.mark.parametrize("site", ["built", "demo"])
def test_the_people_page_lists_a_person_once_with_no_earlier_role(site, request):
    """The People page lists each person under their current or last role only
    and does not mention earlier roles; they are on the person's page."""
    built = request.getfixturevalue(site)
    built, document = built if site == "demo" else (built, FIXTURE)
    text = page(built, "people")
    assert "Earlier" not in text and "earlier" not in text
    for p in document["people"]:
        for r in p["earlier_roles"]:
            assert r["thesis_title"] is None or html.escape(r["thesis_title"]) not in text, p["id"]


def test_demo_earlier_roles(demo):
    """Only Carol Côté has an earlier role in the demo: her MS, with its thesis."""
    built, document = demo
    shown = {p["id"]: earlier_roles(page(built, f"people/{p['id']}")) for p in document["people"]}
    assert {k: v for k, v in shown.items() if v is not None} == {
        "ccote": [["Ms Student, 2020–2022", "Degree: MS",
                   "Thesis: Tactile Sensing for Grasping in Clutter"]]}
