# sslabdata-site

A demo Jekyll renderer for the document that
[sslabdata](https://github.com/siddhss5/sslabdata) emits.

sslabdata compiles BibTeX and a little YAML into one schema-specified document.
This repository is one **optional downstream consumer** of that document: a
set of Jekyll templates (Minimal Mistakes theme) that render it as
works, people and projects pages. It is not part of sslabdata and not
part of what sslabdata promises; sslabdata does not depend on it.

It renders the fictional **Example Lab** in [`demo/`](demo/), deployed at
<https://siddhss5.github.io/sslabdata-site/>.

It is a worked example, not a polished template for other labs to adopt
(that is [sslabdata#37](https://github.com/siddhss5/sslabdata/issues/37)), and it
is not the owner's real lab site.

## Layout

| Path | What it is |
|------|------------|
| [`site/`](site/) | The Jekyll site: `_config.yml`, `_pages/`, `_includes/`, `_data/navigation.yml`, `assets/js/works-filter.js`, `feed.xml` (an Atom feed of the works that have a year, where the theme's footer and head link), and the `Gemfile` / `Gemfile.lock` that pin Jekyll; `_includes/head.html` is a copy of the theme's without its Font Awesome CDN load and with the lab's name escaped in the feed link; re-check it when upgrading the theme |
| [`demo/`](demo/) | Example Lab's `lab.yaml`, `people.yaml`, `projects.yaml`, `collaborators.yaml` and `bib/` |
| [`scripts/generate_site_config.py`](scripts/generate_site_config.py) | Writes the Jekyll settings that come from `lab.yaml` to `site/_config.generated.yml` |
| [`scripts/generate_pages.py`](scripts/generate_pages.py) | Writes a page for every work, person, project and co-author in the data file to `site/_entities/`, each linking to the others it names, the co-author graph page, and a `.bib` of each person's and project's works, their `bibtex` fields unchanged |
| [`tests/`](tests/) | Tests for `generate_site_config.py`, checks on the HTML Jekyll builds from a fixture data file, the works filter script run under node on the built demo, and structural checks (headings, `alt`, `lang`, `<title>`, link names) on every page of the demo built with the theme |
| [`.github/workflows/`](.github/workflows/) | `build.yml` (the build), `pages.yml` (build on PRs, deploy from `main`), `release-gate.yml` (build against a candidate sslabdata) |

`scripts/generate_site_config.py` reads the optional `site:` section of
`lab.yaml` (`url`, `baseurl` and `people_groups`) and writes it, with the lab name and
description, into `site/_config.generated.yml`. sslabdata itself ignores that
section.

## Rendering rules

- **Nobody is left off the People page.** Its groups come from the roles in
  the data file, current members first, then alumni. `site.people_groups` in
  `lab.yaml` optionally titles and orders them, e.g.
  `- {title: "Faculty", roles: [professor]}`; a role it does not name gets a
  group of its own, titled from the role (`visiting_scholar` becomes
  "Visiting Scholar").
- **Every string is text.** Every string taken from the data file is escaped
  where it is printed, `note` included; none is read as HTML or Markdown.
  A template that prints anything unescaped names it, with the reason, in an
  "Unescaped outputs." comment; only values the templates make themselves
  (counts, literal paths, HTML built by `work_link.html`, URLs from
  `safe_url.html`) are listed, never a data field.
- **Only http, https and mailto links.** A URL from the data file becomes a
  link only through [`site/_includes/safe_url.html`](site/_includes/safe_url.html),
  which drops any other scheme and any relative path.
- **Photos and images from the site or http(s).** A person's `photo` is
  shown on their page and on the People page, with their name as its `alt`,
  and a project's `image` on its page and as a thumbnail on the Projects page,
  with its title as its `alt`, through
  [`site/_includes/photo_url.html`](site/_includes/photo_url.html): an
  absolute URL only if it is http or https, a relative path as a file of the
  site, under its `baseurl`. Any other value is not shown.
- **Links that are not guesses.** A work's link is shown when it is written in
  the input (`origin: input`), when its `verification.status` is `verified`,
  or when sslabdata built it from an identifier the entry declares: the
  `derived` links of kind `doi` (from `doi`) and `arxiv` (from `eprint`),
  which are shown. Any other `derived` link, such as the PDF link
  guessed from `pdf_base_url` and the citation key, is not shown until it is
  verified; nor is a link of another origin (`sidecar`, `enrichment`,
  `inferred` or one added later). An input link is shown as it is, whatever
  its verification. See
  [`site/_includes/work_link.html`](site/_includes/work_link.html), which
  names the identifier kinds in an explicit list.
- **The works list is complete without JavaScript.** `/publications/` lists
  every work in its HTML. [`works-filter.js`](site/assets/js/works-filter.js),
  a plain script with no library, reveals a form that filters the list by
  year, type (the work's `category`), project (`project_ids`), person (an
  author's `person_id`) and text, and keeps the filters in the URL
  (`?year=2021&person=hhughes`), so a filtered view can be shared. Works with
  no year are listed last, under "Undated", which the year filter does not offer.
- **An id is a path segment as it is.** Each page's path is its entity's id,
  unchanged, so `generate_pages.py` refuses a document with an id that does
  not match `[A-Za-z0-9][A-Za-z0-9._:-]*` or that contains `..` or a `:`
  followed by a letter (Jekyll turns `..` into a separator and reads `:name`
  as a permalink placeholder), or whose `schema_version` is not the one the
  pinned sslabdata writes (5), before it writes anything.
- **The co-author graph is a picture of its table.** `/coauthor-graph/` draws
  a line between each lab member and each co-author who share a work, as SVG
  with no script, and lists the same pairs, with the number of works they
  share, in a table. Nodes sit on a circle in a fixed order (co-authors by
  key, then lab members by id), so every build draws the same picture.

## The sslabdata pin

sslabdata has no package release, so this repository installs it from an
immutable git tag or commit. The pin is authored in one place: the `sslabdata`
dependency in [`pyproject.toml`](pyproject.toml). `uv.lock` is its generated
resolution, recording the exact commit; do not edit it by hand.

To bump the pin, run the release gate (below) against the new sslabdata tag,
then change the tag in the `sslabdata` dependency in `pyproject.toml`, run
`uv lock`, and commit both files. The build uses `uv sync --locked`, so a pin
changed without regenerating `uv.lock` fails rather than building the old
commit.

## Build locally

You need [uv](https://docs.astral.sh/uv/) and Ruby with Bundler. Run from the
repository root, where `demo/lab.yaml`'s relative paths point:

```bash
uv sync --locked
uv run --frozen pytest
uv run --frozen sslabdata --config demo/lab.yaml --validate
uv run --frozen sslabdata --config demo/lab.yaml --output site/_data/lab.yml
uv run --frozen python scripts/generate_site_config.py demo/lab.yaml site/_config.generated.yml
uv run --frozen python scripts/generate_pages.py site/_data/lab.yml site/_entities
cd site
bundle install
bundle exec jekyll serve --config _config.yml,_config.generated.yml
```

The site is served under `/sslabdata-site/`, the demo's `baseurl`.

## Deployment

[`pages.yml`](.github/workflows/pages.yml) builds the demo on every pull
request and on push to `main`, and deploys it to GitHub Pages on push to
`main` or when run by hand. Pull requests build but never deploy.

## Release gate

[`release-gate.yml`](.github/workflows/release-gate.yml) builds this site
against a candidate sslabdata git ref — a tag, branch or commit — before that
ref is tagged or pinned here. It runs the same build as `pages.yml` (tests,
`--validate`, data and config generation, Jekyll build) and never deploys.
Leaving the ref empty builds against the pin.

From the Actions tab, choose **Release gate**, then **Run workflow**, and
enter the ref. Or with the GitHub CLI:

```bash
gh workflow run release-gate.yml -R siddhss5/sslabdata-site -f sslabdata_ref=<ref>
gh run watch -R siddhss5/sslabdata-site
```

The log's "Show sslabdata version" step prints the commit that was built.
