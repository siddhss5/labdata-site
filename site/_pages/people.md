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
- `alumni_line`: text captured from alumni_line.html, which escapes it.
- `'/people/' | relative_url`: the site path is a literal in this template; relative_url only prefixes the baseurl from _config.yml.
- `'/coauthors/' | relative_url`: the site path is a literal in this template; relative_url only prefixes the baseurl from _config.yml.
{%- endcomment -%}

{% assign people = site.data.lab.people %}
{% assign collaborators = site.data.lab.collaborators %}

{% comment %}
Groups come from the roles in the data file, so nobody is left out. The
optional `site.people_groups` in lab.yaml titles and orders them; each role goes to
the first group that names it, and any other role gets a group of its own,
titled from its name by role_title.html. People with no role come last, in a group titled
"Other", which is the only group with no roles.
{% endcomment %}
{% assign roles = people | map: "role" | compact | uniq %}
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
  {% include role_title.html role=r %}{% assign title = role_title %}{% assign rs = "" | split: "" | push: r %}
  {% assign group_titles = group_titles | push: title %}{% assign group_roles = group_roles | push: rs %}
{% endunless %}{% endfor %}
{% assign rs = "" | split: "" %}
{% assign group_titles = group_titles | push: "Other" %}{% assign group_roles = group_roles | push: rs %}

{% comment %}
Current members come first, then alumni, then, under "Other Members", people
with any other status. Ids made from a title are its slug, which starts with a
letter or digit, so the ids of the fallback groups start with "_".
{% endcomment %}
{% assign other_members = "" | split: "" %}
{% for p in people %}{% unless p.status == "current" or p.status == "alumni" %}{% assign other_members = other_members | push: p %}{% endunless %}{% endfor %}
{% assign statuses = "current,alumni,_other" | split: "," %}
{% for status in statuses %}
{% if status == "_other" %}{% assign members = other_members %}{% else %}{% assign members = people | where: "status", status %}{% endif %}
{% if members.size > 0 %}
{% if status == "alumni" %}
## Alumni
{% elsif status == "_other" %}
<h2 id="_other-members">Other Members</h2>
{% endif %}
{% for title in group_titles %}
{% assign rs = group_roles[forloop.index0] %}
{% if rs.size == 0 %}
{% assign group = members | where_exp: "p", "p.role == nil" %}{% assign slug = "_other" %}
{% else %}
{% assign group = "" | split: "" %}
{% for r in rs %}{% assign with_role = members | where: "role", r %}{% assign group = group | concat: with_role %}{% endfor %}
{% assign slug = title | slugify %}
{% endif %}
{% if group.size > 0 %}
{% comment %}The title comes from the data, so the heading is HTML: kramdown would read a
Markdown heading's escaped text as Markdown.{% endcomment %}
{% if status == "alumni" %}
<h3 id="alumni-{{ slug | escape }}">{{ title | escape }}</h3>
{% elsif status == "_other" %}
<h3 id="_other-members-{{ slug | escape }}">{{ title | escape }}</h3>
{% else %}
<h2 id="{{ slug | escape }}">{{ title | escape }}</h2>
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
<thead><tr><th>Name</th></tr></thead>
<tbody>
{% for p in group %}{% capture photo %}{% include photo_url.html photo=p.photo %}{% endcapture %}<tr><td>{% if photo != "" %}<img src="{{ photo }}" alt="{{ p.name | escape }}" width="48" style="vertical-align: middle; margin-right: 0.5em;">{% endif %}<span id="{{ p.id | escape }}"><a href="{{ '/people/' | relative_url }}{{ p.id | escape }}/">{{ p.name | escape }}</a></span>{% capture alumni_line %}{% include alumni_line.html person=p %}{% endcapture %}{% if alumni_line != "" %}<br><span class="alumni-line">{{ alumni_line }}</span>{% endif %}</td></tr>
{% endfor %}</tbody>
</table>
{% else %}
<table>
<thead><tr><th>Name</th><th>Co-advisor</th><th>Thesis</th></tr></thead>
<tbody>
{% for p in group %}{% capture photo %}{% include photo_url.html photo=p.photo %}{% endcapture %}<tr><td>{% if photo != "" %}<img src="{{ photo }}" alt="{{ p.name | escape }}" width="48" style="vertical-align: middle; margin-right: 0.5em;">{% endif %}<span id="{{ p.id | escape }}"><a href="{{ '/people/' | relative_url }}{{ p.id | escape }}/">{{ p.name | escape }}</a></span>{% capture alumni_line %}{% include alumni_line.html person=p %}{% endcapture %}{% if alumni_line != "" %}<br><span class="alumni-line">{{ alumni_line }}</span>{% endif %}</td><td>{{ p.co_advisor | escape }}</td><td>{{ p.thesis_title | escape }}</td></tr>
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
