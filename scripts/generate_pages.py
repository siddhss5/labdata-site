"""Write one Jekyll page per work, person, project and co-author, the
co-author graph, the Awards page when a work has an award, and a .bib file of
each person's and project's works.

Reads the document sslabdata emits and writes a page for each entity into the
output directory, replacing what was there. The pages are written into a
temporary directory beside it, which replaces it only once every page has been
written; if a write fails, the previous pages are kept. A page's front matter holds the
entity and the entities it links to; every relationship is read from the
document, and this only joins them. The templates in site/_includes/*_page.html
lay the pages out.

An entity id becomes a file name and a URL path segment as it is, so the
generator refuses any id outside ID, and any reference to an entity the
document does not hold, before it writes anything.

Usage: generate_pages.py site/_data/lab.yml site/_entities
"""

import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

# The document version the templates read. It is this renderer's, not the
# installed sslabdata's: a document of another version is refused rather than
# rendered by templates that were not written for it.
SUPPORTED_SCHEMA_VERSION = 6

# An id that Jekyll writes where its links point: no separator, no leading
# `.` or `_` that would make Jekyll skip the file, nothing a URL would need to
# escape, no `..`, which Jekyll turns into a separator, no `:` followed by a
# letter, which Jekyll reads as a permalink placeholder such as `:path`, and
# no trailing `.`, which Jekyll drops from the page's path and which makes the
# .bib permalink hold `..`. Jekyll escapes a file name with a `:` as a URI, so
# the text before the first `:` must be a URI scheme, a letter then letters,
# digits, `.` or `-` (`Smith:2020`, not `2025:1` or `brown_2025:1`), or the
# build stops.
ID = re.compile(r"(?!.*\.\.)(?!.*:[A-Za-z])(?!.*\.$)(?![0-9][^:]*:)(?![^:]*_[^:]*:)"
                r"[A-Za-z0-9][A-Za-z0-9._:-]*")
ID_RULE = ("an id must match [A-Za-z0-9][A-Za-z0-9._:-]* and contain no `..` or `:` followed by a letter, "
           "must not end in `.`, and, if it holds a `:`, must start with a letter and have no `_` "
           "before its first `:`")


def literal(s):
    """`s` as a page title: the theme reads a title as Markdown and does not
    escape it, so every character but letters, digits and spaces is written as
    an HTML character reference, which Markdown and HTML both show as text."""
    return "".join(c if c.isalnum() or c == " " else f"&#{ord(c)};" for c in s)


def main(data_file, out_dir):
    doc = yaml.safe_load(Path(data_file).read_text(encoding="utf-8"))
    if doc.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        sys.exit(f"{data_file}: schema_version {doc.get('schema_version')!r} is not supported; "
                 f"this renderer reads schema_version {SUPPORTED_SCHEMA_VERSION}")
    works = {w["bib_id"]: w for w in doc.get("works") or []}
    people = doc.get("people") or []
    projects = doc.get("projects") or []
    coauthors = doc.get("collaborators") or []
    for kind, key, entities in [("work", "bib_id", works.values()), ("person", "id", people),
                                ("project", "id", projects), ("co-author", "key", coauthors)]:
        for e in entities:
            if not (isinstance(e[key], str) and ID.fullmatch(e[key])):
                sys.exit(f"{data_file}: {kind} id {e[key]!r} is not one path segment; "
                         f"{ID_RULE}")
    # A person or project with works has its .bib at /<section>/<id>.bib; an
    # entity of the same section whose id is `<id>.bib` would need that path
    # as the directory of its page.
    for kind, entities in [("person", people), ("project", projects)]:
        bib_owner = {f"{e['id']}.bib": e["id"] for e in entities if e.get("work_ids")}
        for e in entities:
            if e["id"] in bib_owner:
                sys.exit(f"{data_file}: {kind} id {e['id']!r} is the path of the .bib file of "
                         f"{kind} {bib_owner[e['id']]!r}")
    # Every reference names an entity of the document.
    held = {"work": set(works), "person": {p["id"] for p in people},
            "project": {x["id"] for x in projects}, "co-author": {c["key"] for c in coauthors}}
    references = [("person", p["id"], "work", p.get("work_ids")) for p in people]
    references += [("project", x["id"], "work", x.get("work_ids")) for x in projects]
    references += [("project", x["id"], "person", x.get("people_ids")) for x in projects]
    references += [("co-author", c["key"], "work", c.get("work_ids")) for c in coauthors]
    references += [("work", w["bib_id"], "project", w.get("project_ids")) for w in works.values()]
    references += [("work", w["bib_id"], target, [a[field] for a in w.get("authors") or [] if a.get(field)])
                   for w in works.values()
                   for target, field in [("person", "person_id"), ("co-author", "collaborator_key")]]
    for kind, id_, target, ids in references:
        for i in ids or []:
            if i not in held[target]:
                sys.exit(f"{data_file}: {kind} {id_!r} names {target} {i!r}, "
                         f"which is not in the document")

    def works_of(entity):
        return [works[i] for i in entity.get("work_ids") or []]

    def authors(ws, field):
        return {a[field] for w in ws for a in w.get("authors") or [] if a.get(field)}

    def names(entities, key, ids):
        return [{key: e[key], "name": e.get("name") or e.get("title")} for e in entities if e[key] in ids]

    pages = [("publications", w["bib_id"], "work", w["title"], {"work": w}) for w in works.values()]
    for p in people:
        in_projects = [x["id"] for x in projects if p["id"] in (x.get("people_ids") or [])]
        pages.append(("people", p["id"], "person", p["name"], {
            "person": p, "works": works_of(p),
            "projects": names(projects, "id", in_projects),
            "coauthors": names(coauthors, "key", authors(works_of(p), "collaborator_key"))}))
    for x in projects:
        pages.append(("projects", x["id"], "project", x["title"], {
            "project": x, "works": works_of(x),
            "people": names(people, "id", x.get("people_ids") or [])}))
    for c in coauthors:
        pages.append(("coauthors", c["key"], "coauthor", c["name"], {
            "coauthor": c, "works": works_of(c),
            "also_written_as": [v for v in c.get("name_variants") or [] if v != c["name"]],
            "people": names(people, "id", authors(works_of(c), "person_id"))}))

    # Co-author graph: an edge joins a lab member and a co-author who share a
    # work. Nodes sit on a circle in a fixed order, co-authors by key, then
    # lab members by id, so the layout is the same on every build.
    shared = {}
    for w in works.values():
        for a in w.get("authors") or []:
            for b in w.get("authors") or []:
                if a.get("person_id") and b.get("collaborator_key"):
                    shared.setdefault((a["person_id"], b["collaborator_key"]), set()).add(w["bib_id"])
    order = sorted({("person", p) for p, _ in shared} | {("coauthor", c) for _, c in shared})
    name = {**{("person", p["id"]): p["name"] for p in people},
            **{("coauthor", c["key"]): c["name"] for c in coauthors}}
    at = {n: (round(200 * math.sin(2 * math.pi * i / len(order)), 1),
              round(-200 * math.cos(2 * math.pi * i / len(order)), 1)) for i, n in enumerate(order)}
    graph = {"nodes": [{"kind": k, "id": i, "name": name[k, i], "x": at[k, i][0], "y": at[k, i][1],
                        "anchor": "start" if at[k, i][0] >= 0 else "end"} for k, i in order],
             "edges": [{"person": p, "person_name": name["person", p], "coauthor": c,
                        "coauthor_name": name["coauthor", c], "works": len(shared[p, c]),
                        "x1": at["person", p][0], "y1": at["person", p][1],
                        "x2": at["coauthor", c][0], "y2": at["coauthor", c][1]}
                       for p, c in sorted(shared)]}

    # Awards page: one row per award, newest first, awards with no year last.
    # Within a year the rows keep the document's works order (year
    # descending, then read order) and each work's `awards` order; the sort
    # is stable, so it only moves rows between years.
    awards = sorted(({"year": a["year"], "name": a["name"], "bib_id": w["bib_id"], "title": w["title"]}
                     for w in works.values() for a in w.get("awards") or []),
                    key=lambda r: (r["year"] is None, -(r["year"] or 0)))

    out = Path(out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    discard = True
    try:
        write_pages(work / "new", pages, graph, awards)
        if out.exists() or out.is_symlink():
            os.rename(out, work / "old")
            try:
                os.rename(work / "new", out)
            except OSError:
                # Put the previous pages back; if that fails too, they stay
                # in `work` rather than being removed with it.
                discard = False
                os.rename(work / "old", out)
                discard = True
                raise
        else:
            os.rename(work / "new", out)
    except OSError as e:
        kept = "the previous pages are kept" if discard else f"the previous pages are in {work / 'old'}"
        sys.exit(f"{out_dir}: not replaced ({kept}): {e}")
    finally:
        if discard:
            shutil.rmtree(work, ignore_errors=True)


def write_pages(root, pages, graph, awards):
    """Write `pages`, the co-author `graph` and, if there are any `awards`,
    the Awards page into the new directory `root`."""
    root.mkdir()
    for section, id_, kind, title, data in pages:
        path = root / section / f"{id_}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        front = {"title": literal(title), "permalink": f"/{section}/{id_}/", **data}
        path.write_text("---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
                        + f"---\n{{% include {kind}_page.html %}}\n", encoding="utf-8")
        # The works' BibTeX as the data file carries it, one entry after
        # another. Liquid prints a front matter value without reading it as
        # Liquid, so the file holds the entries byte for byte.
        if kind in ("person", "project") and data["works"]:
            bib = {"layout": None, "permalink": f"/{section}/{id_}.bib",
                   "bibtex": "\n\n".join(w["bibtex"] for w in data["works"] if w.get("bibtex"))}
            (root / section / f"{id_}.bib").write_text(
                "---\n" + yaml.safe_dump(bib, allow_unicode=True, sort_keys=False)
                + "---\n{{ page.bibtex }}\n", encoding="utf-8")
    front = {"title": "Co-author graph", "permalink": "/coauthor-graph/", **graph}
    (root / "coauthor-graph.html").write_text(
        "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
        + "---\n{% include coauthor_graph.html %}\n", encoding="utf-8")
    # No award, no page; the navigation shows only entries whose page exists.
    if awards:
        front = {"title": "Awards", "permalink": "/awards/", "awards": awards}
        (root / "awards.html").write_text(
            "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
            + "---\n{% include awards_page.html %}\n", encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
