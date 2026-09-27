---
title: "People"
permalink: /people/
layout: single
classes: wide
---

{%- comment -%}
Unescaped outputs. Every output not listed here is escaped.
- `collaborators.size`: a count Liquid computes, not a string from the data file.
- `photo`: a URL captured from photo_url.html, which escapes it.
- `'/people/' | relative_url`: the site path is a literal in this template; relative_url only prefixes the baseurl from _config.yml.
- `'/coauthors/' | relative_url`: the site path is a literal in this template; relative_url only prefixes the baseurl from _config.yml.
{%- endcomment -%}

{% assign people = site.data.lab.people %}
{% assign collaborators = site.data.lab.collaborators %}

{% comment %}
Groups come from the roles in the data file, so nobody is left out. The
optional `site.people_groups` in lab.yaml titles and orders them; each role goes to
the first group that names it, and any other role gets a group of its own,
titled from its name.
{% endcomment %}
{% assign roles = people | map: "role" | uniq %}
{% assign group_titles = "" | split: "" %}
{% assign group_roles = "" | split: "" %}
{% assign claimed = "" | split: "" %}
{% for g in site.people_groups %}
  {% assign rs = "" | split: "" %}
  {% for r in g.roles %}{% if roles contains r %}{% unless claimed contains r %}
    {% assign rs = rs | push: r %}{% assign claimed = claimed | push: r %}
  {% endunless %}{% endif %}{% endfor %}
  {% if rs.size > 0 %}{% assign group_titles = group_titles | push: g.title %}{% assign group_roles = group_roles | push: rs %}{% endif %}
{% endfor %}
{% for r in roles %}{% unless claimed contains r %}
  {% assign words = r | split: "_" %}{% assign title = "" %}
  {% for w in words %}{% assign first = w | slice: 0 | upcase %}{% assign rest = w | slice: 1, w.size %}{% assign title = title | append: " " | append: first | append: rest %}{% endfor %}
  {% assign title = title | strip | default: r %}{% assign rs = "" | split: "" | push: r %}
  {% assign group_titles = group_titles | push: title %}{% assign group_roles = group_roles | push: rs %}
{% endunless %}{% endfor %}

{% assign statuses = "current,alumni" | split: "," %}
{% for status in statuses %}
{% assign members = people | where: "status", status %}
{% if members.size > 0 %}
{% if status == "alumni" %}
## Alumni
{% endif %}
{% for title in group_titles %}
{% assign rs = group_roles[forloop.index0] %}
{% assign group = "" | split: "" %}
{% for r in rs %}{% assign with_role = members | where: "role", r %}{% assign group = group | concat: with_role %}{% endfor %}
{% if group.size > 0 %}
{% comment %}The title comes from the data, so the heading is HTML: kramdown would read a
Markdown heading's escaped text as Markdown.{% endcomment %}
{% if status == "alumni" %}
<h3 id="alumni-{{ title | slugify | escape }}">{{ title | escape }}</h3>
{% else %}
<h2 id="{{ title | slugify | escape }}">{{ title | escape }}</h2>
{% endif %}

{% if status == "current" and rs contains "professor" %}
{% for p in group %}{% capture photo %}{% include photo_url.html photo=p.photo %}{% endcapture %}<p>{% if photo != "" %}<img src="{{ photo }}" alt="{{ p.name | escape }}" width="48" style="vertical-align: middle; margin-right: 0.5em;">{% endif %}<span id="{{ p.id | escape }}"><a href="{{ '/people/' | relative_url }}{{ p.id | escape }}/">{{ p.name | escape }}</a></span></p>
{% endfor %}
{% elsif status == "current" %}
<table>
<thead><tr><th>Name</th><th>Co-advisor</th><th>Thesis</th><th>Started</th></tr></thead>
<tbody>
{% for p in group %}{% capture photo %}{% include photo_url.html photo=p.photo %}{% endcapture %}<tr><td>{% if photo != "" %}<img src="{{ photo }}" alt="{{ p.name | escape }}" width="48" style="vertical-align: middle; margin-right: 0.5em;">{% endif %}<span id="{{ p.id | escape }}"><a href="{{ '/people/' | relative_url }}{{ p.id | escape }}/">{{ p.name | escape }}</a></span></td><td>{{ p.co_advisor | escape }}</td><td>{{ p.thesis_title | escape }}</td><td>{{ p.start_year | escape }}</td></tr>
{% endfor %}</tbody>
</table>
{% elsif rs contains "postdoc" %}
<table>
<thead><tr><th>Name</th><th>Period</th><th>Current Position</th></tr></thead>
<tbody>
{% for p in group %}{% capture photo %}{% include photo_url.html photo=p.photo %}{% endcapture %}<tr><td>{% if photo != "" %}<img src="{{ photo }}" alt="{{ p.name | escape }}" width="48" style="vertical-align: middle; margin-right: 0.5em;">{% endif %}<span id="{{ p.id | escape }}"><a href="{{ '/people/' | relative_url }}{{ p.id | escape }}/">{{ p.name | escape }}</a></span></td><td>{{ p.start_year | escape }}–{{ p.end_year | escape }}</td><td>{{ p.current_position | escape }}</td></tr>
{% endfor %}</tbody>
</table>
{% else %}
<table>
<thead><tr><th>Name</th><th>Co-advisor</th><th>Thesis</th><th>Period</th><th>Current Position</th></tr></thead>
<tbody>
{% for p in group %}{% capture photo %}{% include photo_url.html photo=p.photo %}{% endcapture %}<tr><td>{% if photo != "" %}<img src="{{ photo }}" alt="{{ p.name | escape }}" width="48" style="vertical-align: middle; margin-right: 0.5em;">{% endif %}<span id="{{ p.id | escape }}"><a href="{{ '/people/' | relative_url }}{{ p.id | escape }}/">{{ p.name | escape }}</a></span></td><td>{{ p.co_advisor | escape }}</td><td>{{ p.thesis_title | escape }}</td><td>{{ p.start_year | escape }}–{{ p.end_year | escape }}</td><td>{{ p.current_position | escape }}</td></tr>
{% endfor %}</tbody>
</table>
{% endif %}
{% endif %}
{% endfor %}
{% endif %}
{% endfor %}

{% if collaborators.size > 0 %}
## Collaborators

<details>
<summary style="cursor: pointer; font-size: 1.17em; font-weight: bold; margin-bottom: 0.5em;">{{ collaborators.size }} co-authors</summary>
<div style="margin-top: 0.8em; display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.3em 2em;">
{% for c in collaborators %}<div style="font-size: 0.9em;"><a href="{{ '/coauthors/' | relative_url }}{{ c.key | escape }}/">{{ c.name | escape }}</a></div>
{% endfor %}
</div>
</details>
{% endif %}
