"""Checks on scripts/generate_pages.py that need no Jekyll: the document it
refuses, and that a refused document leaves everything as it was."""

import subprocess
import sys

import pytest
import yaml
from sslabdata.models import SCHEMA_VERSION

from test_site_build import ADA, COLLAB, FIXTURE, PROJECT, REPO_ROOT, SCRIPT

ENTITIES = {"work": ("works", "bib_id", SCRIPT), "person": ("people", "id", ADA),
            "project": ("projects", "id", PROJECT), "co-author": ("collaborators", "key", COLLAB)}


def rename(node, old, new):
    """`node` with every string equal to `old` replaced by `new`, so that an
    id and every reference to it change together."""
    if node == old:
        return new
    if isinstance(node, dict):
        return {k: rename(v, old, new) for k, v in node.items()}
    if isinstance(node, list):
        return [rename(v, old, new) for v in node]
    return node


def generate(tmp_path, document):
    """Run the generator on `document` into an output directory that already
    holds a page; return the result and that directory."""
    data = tmp_path / "lab.yml"
    data.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "site" / "_entities"
    (out / "people").mkdir(parents=True)
    (out / "people" / "old.html").write_text("old", encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/generate_pages.py", data, out],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    return result, out


def assert_nothing_written(tmp_path, out):
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == \
        ["lab.yml", "site", "site/_entities", "site/_entities/people", "site/_entities/people/old.html"]


@pytest.mark.parametrize("id_", ["../../escaped", "a/b", "two words", "Zoë", ".hidden", "_x", "-x", "",
                                 "a..b", "x:path", "a:basename", "Smith:robots", "brown_2025:1", "2025:1",
                                 "a."])
@pytest.mark.parametrize("kind", ENTITIES)
def test_an_id_that_is_not_one_path_segment_is_refused(kind, id_, tmp_path):
    collection, key, old = ENTITIES[kind]
    document = yaml.safe_load(yaml.safe_dump(FIXTURE))
    next(e for e in document[collection] if e[key] == old)[key] = id_
    result, out = generate(tmp_path, document)
    assert result.returncode == 1
    assert f"{kind} id {id_!r} is not one path segment" in result.stderr
    assert "contain no `..` or `:` followed by a letter" in result.stderr
    assert_nothing_written(tmp_path, out)


@pytest.mark.parametrize("kind, collection", [("person", "people"), ("project", "projects")])
def test_an_id_that_is_another_entitys_bib_path_is_refused(kind, collection, tmp_path):
    """A person or project with works has a page at /<section>/<id>/ and its
    .bib at /<section>/<id>.bib; an entity whose id is `<id>.bib` needs that
    path as a directory, which Jekyll cannot write."""
    document = yaml.safe_load(yaml.safe_dump(FIXTURE))
    first, second = document[collection][:2]
    assert first["work_ids"]
    second_id = first["id"] + ".bib"
    document = rename(document, second["id"], second_id)
    result, out = generate(tmp_path, document)
    assert result.returncode == 1
    assert f"{kind} id {second_id!r}" in result.stderr
    assert f"{kind} {first['id']!r}" in result.stderr
    assert_nothing_written(tmp_path, out)


def test_an_id_too_long_to_be_a_file_name_leaves_the_previous_pages(tmp_path):
    """An id the checks accept but the file system cannot hold fails while
    pages are being written; the pages already there stay as they were."""
    result, out = generate(tmp_path, rename(FIXTURE, ADA, "a" * 300))
    assert result.returncode == 1
    assert "File name too long" in result.stderr and "Traceback" not in result.stderr
    assert_nothing_written(tmp_path, out)


def dangle(document, collection, key, id_, field, value="missing"):
    """`document` with `value` added to `field` of the entity whose `key` is `id_`."""
    document = yaml.safe_load(yaml.safe_dump(document))
    entity = next(e for e in document[collection] if e[key] == id_)
    entity[field] = [*(entity.get(field) or []), value]
    return document


def dangle_author(document, field):
    """`document` with the first author of SCRIPT naming no entity in `field`."""
    document = yaml.safe_load(yaml.safe_dump(document))
    author = next(w for w in document["works"] if w["bib_id"] == SCRIPT)["authors"][0]
    author.update({"person_id": None, "collaborator_key": None, field: "missing"})
    return document


@pytest.mark.parametrize("document, names", [
    (lambda: dangle(FIXTURE, "people", "id", ADA, "work_ids"), f"person {ADA!r} names work 'missing'"),
    (lambda: dangle(FIXTURE, "projects", "id", PROJECT, "work_ids"),
     f"project {PROJECT!r} names work 'missing'"),
    (lambda: dangle(FIXTURE, "collaborators", "key", COLLAB, "work_ids"),
     f"co-author {COLLAB!r} names work 'missing'"),
    (lambda: dangle(FIXTURE, "projects", "id", PROJECT, "people_ids"),
     f"project {PROJECT!r} names person 'missing'"),
    (lambda: dangle(FIXTURE, "works", "bib_id", SCRIPT, "project_ids"),
     f"work {SCRIPT!r} names project 'missing'"),
    (lambda: dangle_author(FIXTURE, "person_id"), f"work {SCRIPT!r} names person 'missing'"),
    (lambda: dangle_author(FIXTURE, "collaborator_key"), f"work {SCRIPT!r} names co-author 'missing'"),
], ids=["person-works", "project-works", "coauthor-works", "project-people", "work-projects",
        "author-person", "author-coauthor"])
def test_a_reference_to_no_entity_is_refused(document, names, tmp_path):
    result, out = generate(tmp_path, document())
    assert result.returncode == 1
    assert names in result.stderr and "Traceback" not in result.stderr
    assert_nothing_written(tmp_path, out)


@pytest.mark.parametrize("id_", ["Smith:2020", "B.Brown"])
@pytest.mark.parametrize("kind", ENTITIES)
def test_an_id_jekyll_keeps_as_it_is_is_accepted(kind, id_, tmp_path):
    result, out = generate(tmp_path, rename(FIXTURE, ENTITIES[kind][2], id_))
    assert result.returncode == 0, result.stderr
    section = {"work": "publications", "person": "people", "project": "projects",
               "co-author": "coauthors"}[kind]
    assert (out / section / f"{id_}.html").is_file()


@pytest.mark.parametrize("version", [SCHEMA_VERSION - 1, SCHEMA_VERSION + 1, None])
def test_an_unsupported_schema_version_is_refused(version, tmp_path):
    result, out = generate(tmp_path, {**FIXTURE, "schema_version": version})
    assert result.returncode == 1
    assert f"schema_version {version!r} is not supported" in result.stderr
    assert f"reads schema_version {SCHEMA_VERSION}" in result.stderr
    assert_nothing_written(tmp_path, out)


def test_schema_version_5_is_the_one_read(tmp_path):
    """The pinned sslabdata writes schema_version 5, the version the templates
    read; the fixture, a document it emitted, is accepted."""
    assert SCHEMA_VERSION == 5 and FIXTURE["schema_version"] == 5
    result, out = generate(tmp_path, FIXTURE)
    assert result.returncode == 0, result.stderr
    assert not (out / "people" / "old.html").exists()
    assert sorted(p.name for p in (tmp_path / "site").iterdir()) == ["_entities"]
