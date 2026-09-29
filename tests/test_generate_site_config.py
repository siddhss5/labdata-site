"""Tests for scripts/generate_site_config.py and the demo config it reads."""

import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

from test_site_build import build, demo_data


REPO_ROOT = Path(__file__).parent.parent
DEMO_CONFIG = "demo/lab.yaml"


class TestGenerateSiteConfig:
    def _run(self, lab_yaml, tmp_path):
        out = tmp_path / "_config.generated.yml"
        result = subprocess.run(
            [sys.executable, "scripts/generate_site_config.py", str(lab_yaml), str(out)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        with open(out, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_demo(self, tmp_path):
        with open(REPO_ROOT / DEMO_CONFIG, 'r', encoding='utf-8') as f:
            lab_config = yaml.safe_load(f)
        config = self._run(DEMO_CONFIG, tmp_path)
        assert config["title"] == "Example Lab"
        assert config["description"] == lab_config["lab"]["description"]
        assert config["url"] == lab_config["site"]["url"]
        assert config["baseurl"] == lab_config["site"]["baseurl"]

    def test_values_follow_lab_yaml(self, tmp_path):
        lab_yaml = tmp_path / "lab.yaml"
        lab_yaml.write_text(yaml.safe_dump({
            "lab": {"name": "Other Lab", "description": "Something else"},
            "site": {"url": "https://other.example.org", "baseurl": "/other"},
            "bib_dir": "bib",
            "bib_files": [],
        }))
        config = self._run(lab_yaml, tmp_path)
        assert config == {
            "title": "Other Lab",
            "description": "Something else",
            "url": "https://other.example.org",
            "baseurl": "/other",
        }

    def test_without_site_section(self, tmp_path):
        lab_yaml = tmp_path / "lab.yaml"
        lab_yaml.write_text(yaml.safe_dump({
            "lab": {"name": "Root Lab"},
            "bib_dir": "bib",
            "bib_files": [],
        }))
        config = self._run(lab_yaml, tmp_path)
        assert config == {"title": "Root Lab", "baseurl": ""}

    def test_people_groups(self, tmp_path):
        groups = [{"title": "Faculty", "roles": ["professor"]},
                  {"title": "Research Staff", "roles": ["research_scientist", "engineer"]}]
        lab_yaml = tmp_path / "lab.yaml"
        lab_yaml.write_text(yaml.safe_dump({"site": {"people_groups": groups}}))
        assert self._run(lab_yaml, tmp_path)["people_groups"] == groups


# The theme prints the url unescaped as a link in every page's footer, so a url
# that could leave the attribute or is not an http or https origin is refused.
@pytest.mark.parametrize("url", [
    'https://x.example.org"><img src=x onerror=alert(1)>',
    "javascript:alert(1)//x.example.org",
    "https://user@x.example.org",
    "https://x.example.org/path?q=1",
    "https://x.example.org/path/",
    "https://x.example.org//",
    "https://x.example.org/?q=1",
])
def test_unsafe_url_is_refused(tmp_path, url):
    lab_yaml = tmp_path / "lab.yaml"
    lab_yaml.write_text(yaml.safe_dump({"lab": {"name": "Lab"}, "site": {"url": url}}))
    out = tmp_path / "_config.generated.yml"
    result = subprocess.run(
        [sys.executable, "scripts/generate_site_config.py", str(lab_yaml), str(out)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert "site.url" in result.stderr
    assert not out.exists()


def test_url_trailing_slash_is_dropped(tmp_path):
    """Jekyll joins url and baseurl as they are, so the slash would double."""
    lab_yaml = tmp_path / "lab.yaml"
    lab_yaml.write_text(yaml.safe_dump({"site": {"url": "https://x.example.org/",
                                                 "baseurl": "/lab"}}))
    config = TestGenerateSiteConfig()._run(lab_yaml, tmp_path)
    assert config["url"] + config["baseurl"] == "https://x.example.org/lab"


class Links(HTMLParser):
    """Every href and src on a page."""

    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls += [v for k, v in attrs if k in ("href", "src") and v]


def test_demo_links_resolve_under_the_configured_baseurl(tmp_path):
    """Built with the theme and the config generate_site_config.py writes from
    the demo's lab.yaml moved to another url and baseurl, every link on every
    page to the site itself is under the baseurl and names a file of the build.
    The build is left in tmp_path/_site."""
    url, baseurl = "https://lab.invalid", "/deep/base"
    lab = yaml.safe_load((REPO_ROOT / DEMO_CONFIG).read_text(encoding="utf-8"))
    lab["site"].update({"url": url, "baseurl": baseurl})
    lab_yaml = tmp_path / "lab.yaml"
    lab_yaml.write_text(yaml.safe_dump(lab, allow_unicode=True), encoding="utf-8")
    config = tmp_path / "moved.yml"
    subprocess.run([sys.executable, "scripts/generate_site_config.py", lab_yaml, config],
                   check=True, cwd=REPO_ROOT)
    data, people_groups = demo_data(tmp_path)
    built = build(tmp_path, data, people_groups, theme=True, site_config=config)
    checked, broken = 0, []
    for page in sorted(built.rglob("*.html")):
        parser = Links()
        parser.feed(page.read_text(encoding="utf-8"))
        for link in parser.urls:
            parts = urlsplit(link)
            internal = parts.scheme in ("", "http", "https") and parts.netloc in ("", urlsplit(url).netloc)
            if not internal or not parts.path:
                continue
            checked += 1
            path = unquote(parts.path)
            target = built / path.removeprefix(baseurl + "/")
            if target.is_dir():
                target = target / "index.html"
            if not path.startswith(baseurl + "/") or not target.is_file():
                broken.append((str(page.relative_to(built)), link))
    assert checked > 100
    assert broken == []
