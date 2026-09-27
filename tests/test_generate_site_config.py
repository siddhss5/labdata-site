"""Tests for scripts/generate_site_config.py and the demo config it reads."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


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
        # Where the demo is deployed.
        assert config["url"] + config["baseurl"] == "https://siddhss5.github.io/sslabdata-site"

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
