"""Check the works filter on /publications/.

The demo is built once, with the stub layout test_site_build.py uses. Without
JavaScript the page lists every work and hides only the filter form.

The filtering is checked by running, under node, the built works-filter.js
that the page's <script> names. Node has no DOM, so STUB gives the script
the few calls it makes, and throws on any other selector: one element per
`.pub-entry` and per section, read from the built page, the form's fields, and
`location` and `history` over a URL. The expected works are read from the data file.

Skipped when Bundler, the pinned Jekyll or node is not installed.
"""

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from urllib.parse import urlencode

import pytest
import yaml

from test_site_build import build, demo_data, missing_tool


STUB = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const entries = input.entries.map(a => ({hidden: false, getAttribute: n => a[n] ?? null}));
const only = (s, want, v) => { if (s !== want) throw new Error(s); return v; };
const sections = input.sections.map(ids => ({hidden: false,
  querySelectorAll: s => only(s, '.pub-entry', ids.map(i => entries[i]))}));
const elements = Object.fromEntries(input.fields.map(n => [n, {value: ''}]));
const listeners = {};
const form = {hidden: true, elements, addEventListener: (t, f) => { listeners[t] = f; }};
const count = {textContent: ''};
const url = new URL(input.url);
globalThis.location = url;
globalThis.history = {replaceState: (s, t, u) => { url.href = new URL(u, url).href; }};
globalThis.document = {
  getElementById: id => ({'works-filter': form, 'works-filter-count': count})[id],
  querySelectorAll: s => s === '.pub-entry' ? entries
    : only(s, '.pub-year-section, .pub-category-section', sections),
};
const state = () => ({
  shown: entries.flatMap((e, i) => e.hidden ? [] : [i]),
  hiddenSections: sections.flatMap((s, i) => s.hidden ? [i] : []),
  values: Object.fromEntries(input.fields.map(n => [n, elements[n].value])),
  formHidden: form.hidden, count: count.textContent, url: url.pathname + url.search,
});
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const out = [state()];
if (input.set) {
  for (const [n, v] of Object.entries(input.set)) elements[n].value = v;
  listeners.input();
  out.push(state());
}
console.log(JSON.stringify(out));
"""


class WorksPage(HTMLParser):
    """The works list as built: each entry's attributes and the work its
    title link names, the entries in each section, the form's fields, the
    page's script sources and the elements marked hidden."""

    def __init__(self):
        super().__init__()
        self.entries, self.sections, self.fields, self.scripts, self.hidden = [], [], [], [], []
        self.open = []  # per open <div>: a section's index, "entry" or None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "script":
            self.scripts.append(attrs.get("src"))
        if "hidden" in attrs:
            self.hidden.append(tag)
        if tag in ("select", "input") and attrs.get("name"):
            self.fields.append(attrs["name"])
        if tag == "a" and "entry" in self.open:
            if m := re.fullmatch(r"/publications/([^/]+)/", attrs.get("href") or ""):
                self.entries[-1]["bib_id"] = m[1]
        if tag != "div":
            return
        if "pub-entry" in classes:
            for s in self.open:
                if isinstance(s, int):
                    self.sections[s].append(len(self.entries))
            self.entries.append({"attrs": attrs})
            self.open.append("entry")
        elif {"pub-year-section", "pub-category-section"} & set(classes):
            self.sections.append([])
            self.open.append(len(self.sections) - 1)
        else:
            self.open.append(None)

    def handle_endtag(self, tag):
        if tag == "div":
            self.open.pop()


def parse(built):
    text = (built / "publications" / "index.html").read_text(encoding="utf-8")
    page = WorksPage()
    page.feed(text)
    page.root = built
    return page, text


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """The demo's built /publications/ page, parsed, and its data file."""
    tmp = tmp_path_factory.mktemp("works")
    data, people_groups = demo_data(tmp)
    return parse(build(tmp, data, people_groups))[0], yaml.safe_load(data)


def run_filter(page, query, inputs=None):
    """Run the shipped script on `page` at /publications/?`query`; if `inputs`
    is given, then fill in those form fields as a reader would. The script run
    is the built file the page's one <script> names. Returns the state after
    load, and after the input if there was one."""
    if shutil.which("node") is None:
        missing_tool("node is not available")
    payload = {"url": "https://fixture.invalid/publications/" + (f"?{query}" if query else ""),
               "fields": page.fields, "entries": [e["attrs"] for e in page.entries],
               "sections": page.sections, "set": inputs}
    [src] = page.scripts
    result = subprocess.run(["node", "-e", STUB, str(page.root / src.lstrip("/"))], input=json.dumps(payload),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    states = json.loads(result.stdout)
    for s in states:
        s["works"] = {page.entries[i]["bib_id"] for i in s["shown"]}
        # A section is hidden exactly when none of its works is shown.
        assert s["hiddenSections"] == [i for i, ids in enumerate(page.sections)
                                       if not set(ids) & set(s["shown"])], s
        assert s["count"] == f"Showing {len(s['shown'])} of {len(page.entries)} works"
        assert s["formHidden"] is False
    return states


def matching(document, year=None, type=None, project=None, person=None, q=None):
    """The bib_ids of the works in the data file matching every given filter;
    `q` is matched against the title only."""
    return {w["bib_id"] for w in document["works"]
            if (year is None or str(w["year"]) == year)
            and (type is None or w["category"] == type)
            and (project is None or project in w["project_ids"])
            and (person is None or person in [a["person_id"] for a in w["authors"]])
            and (q is None or q.strip().lower() in w["title"].lower())}


def test_without_javascript_every_work_is_listed_and_only_the_form_hidden(demo):
    page, document = demo
    assert sorted(e["bib_id"] for e in page.entries) == sorted(w["bib_id"] for w in document["works"])
    assert page.hidden == ["form"]
    assert not any("display: none" in (e["attrs"].get("style") or "") for e in page.entries)
    assert page.scripts == ["/assets/js/works-filter.js"]


@pytest.mark.parametrize("filters", [
    {},
    {"year": "2021"},
    {"type": "Journal Papers"},
    {"project": "legged"},
    {"person": "aadams"},
    {"q": "  TIDY "},
    {"year": "2025", "type": "Journal Papers", "project": "homebot", "person": "ccote"},
])
def test_url_filters_show_exactly_the_matching_works(demo, filters):
    page, document = demo
    [state] = run_filter(page, urlencode(filters))
    assert state["works"] == matching(document, **filters)
    assert state["works"]
    # The form shows the filters the URL names.
    assert {n: v for n, v in state["values"].items() if v} == {n: v.strip() for n, v in filters.items()}


def test_unknown_value_matches_nothing(demo):
    page, _ = demo
    [state] = run_filter(page, "person=nobody")
    assert state["works"] == set()


def test_changing_the_form_writes_the_state_to_the_url(demo):
    page, document = demo
    before, after = run_filter(page, "year=2025&person=bbrown",
                          inputs={"year": "2021", "type": "Journal Papers", "person": ""})
    assert before["works"] == matching(document, year="2025", person="bbrown")
    assert after["url"] == "/publications/?" + urlencode({"year": "2021", "type": "Journal Papers"})
    assert after["works"] == matching(document, year="2021", type="Journal Papers")
    # The written URL, loaded afresh, shows the same works.
    [reloaded] = run_filter(page, after["url"].split("?", 1)[1])
    assert reloaded["works"] == after["works"]


def test_undated_works_come_last_and_only_without_a_year_filter(tmp_path):
    document = yaml.safe_load(demo_data(tmp_path)[0])
    document["works"][0]["year"] = None
    page, text = parse(build(tmp_path, yaml.safe_dump(document, allow_unicode=True)))
    assert re.findall(r"<h2>(.*?)</h2>", text)[-1] == "Undated"
    assert page.entries[-1]["bib_id"] == document["works"][0]["bib_id"]
    years = re.search(r'<select name="year".*?</select>', text)[0]
    assert all(re.fullmatch(r"\d*", v) for v in re.findall(r'value="([^"]*)"', years))
    [state] = run_filter(page, "")
    assert state["works"] == matching(document)
    [state] = run_filter(page, "year=2025")
    assert state["works"] == matching(document, year="2025")
