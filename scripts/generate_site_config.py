#!/usr/bin/env python3
"""
Write the Jekyll settings that come from lab.yaml to a separate config file.

The site title and description come from `lab.name` and `lab.description`;
`url`, `baseurl` and `people_groups` (which titles and orders the groups on
the People page) come from the optional `site` section. A `url` that is not
an http or https origin is refused, and nothing is written. Build with both
files so these values override site/_config.yml:

    python scripts/generate_site_config.py lab.yaml site/_config.generated.yml
    cd site && bundle exec jekyll build --config _config.yml,_config.generated.yml
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

# The theme prints `url` unescaped as the footer's link, on every page, so it
# must be a value that needs no escaping and is a web address: an http or
# https origin (scheme, host and optional port, nothing else). `baseurl` is
# printed only through relative_url and absolute_url, which percent-encode it.
HOST = re.compile(r"[A-Za-z0-9.-]+")


class ConfigError(ValueError):
    """A lab.yaml value this site cannot use."""


def check_url(url) -> None:
    if not isinstance(url, str):
        raise ConfigError(f"site.url must be a string, not {url!r}")
    parts = urlsplit(url)
    try:
        parts.port
    except ValueError:
        raise ConfigError(f"site.url has an invalid port: {url!r}") from None
    if (parts.scheme not in ("http", "https") or parts.username is not None
            or parts.password is not None or not HOST.fullmatch(parts.hostname or "")
            or parts.path or parts.query or parts.fragment
            or url != f"{parts.scheme}://{parts.netloc}"):
        raise ConfigError(f"site.url must be an http or https origin such as "
                          f"https://example.org, not {url!r}")


def site_config(lab_config: dict) -> dict:
    """Map a parsed lab.yaml to Jekyll config values."""
    lab = lab_config.get('lab') or {}
    site = lab_config.get('site') or {}
    config = {}
    if lab.get('name'):
        config['title'] = lab['name']
    if lab.get('description'):
        config['description'] = lab['description']
    if site.get('url'):
        check_url(site['url'])
        config['url'] = site['url']
    config['baseurl'] = site.get('baseurl', '')
    if site.get('people_groups'):
        config['people_groups'] = site['people_groups']
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('lab_yaml', help='Path to lab.yaml')
    parser.add_argument('output', help='Path of the Jekyll config file to write')
    args = parser.parse_args()

    with open(args.lab_yaml, 'r', encoding='utf-8') as f:
        lab_config = yaml.safe_load(f) or {}
    try:
        config = site_config(lab_config)
    except ConfigError as e:
        sys.exit(f"{args.lab_yaml}: {e}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        f.write(f"# Generated from {args.lab_yaml} by scripts/generate_site_config.py. Do not edit.\n")
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
