#!/usr/bin/env python
from pathlib import Path
import json
import os
import sys
from urllib.parse import urlparse

DIR = Path(__file__).parent

def main():
    for i in [
        ["semantics", "manifest.jsonld"],
        ["sparql", "manifest.jsonld"],
        ["turtle", "syntax", "manifest.ttl"],
        ["turtle", "eval", "manifest.ttl"],
        ["nt", "syntax", "manifest.ttl"],
    ]:
        make_html(DIR.joinpath(*i))

def make_html(path: Path):
    dir = path.parent
    html = dir.joinpath(path.stem + '.html')
    manifest = open_manifest(path)
    if manifest is None:
        eprint(f"Don't know how to parse {path}")
        return

    print(html)
    with html.open('w') as out:
        out.write("<!DOCTYPE html>\n")
        out.write('<meta charset="UTF-8">')
        out.write(STYLE)
        out.write(f"<title>{path.stem}</title>\n")
        out.write(f"<h1>{path.stem}</h1>\n")
        out.write(f'<p>Generated from <a href="{path.name}">{path.name}</a></p>')
        if 'comment' in manifest:
            out.write(f"<p>{manifest['comment']}</p>\n")

        include = manifest.get('include')
        if include:
            out.write('<p><strong>Includes:</strong></p>\n<ul class="inclueded">\n')
            for url in include:
                make_html(dir.joinpath(*url.split('/')))
                name = url.replace('.jsonld', '')
                url = url.replace('.jsonld', '.html')
                out.write(f'<li><a href="{url}">{name}</a>\n')
            out.write("</ul>\n")

        entries = manifest.get('entries') or []
        if entries:
            out.write('<p><strong>Entries:</strong></p>\n<ul class="entries">\n')
            for (i, entry) in enumerate(entries):
                eid = entry.get('@id', f"#{path.name}_entry{i}")
                name = entry.get('name', eid[1:])
                approval = entry.get('approval', 'proposed').lower()
                out.write(f'<li class="{approval}"><a href="{eid}">{name}</a>\n')
                # store computed values for the next loop
                entry['@id'] = eid
                entry['name'] = name
                #
            out.write("</ul>\n")

        see_also = manifest.get('seeAlso')
        if see_also:
            out.write('<h2>About this test suite</h2>\n')
            if see_also.startswith('http://') or see_also.startswith('https://'):
                out.write(f'<a href="{see_also}">{see_also}</a>\n')
            else:
                see_also = dir.joinpath(*see_also.split('/'))
                out.write('<pre>\n')
                out.write(see_also.read_text())
                out.write('</pre>\n')

        for entry in entries:
            eid = entry['@id']
            typ = entry['@type']
            name = entry['name']
            approval = entry.get('approval', 'proposed').lower()
            out.write(f'<section id="{eid[1:]}" class="entry {approval} {typ}">\n')
            out.write(f'<h2>{name} <a href="{eid}">🔗</a></h2>\n')
            out.write('<table class="properties">\n')
            out.write(f'<tr class="status"><th>status:</th><td>{approval}</td>\n')
            out.write(f'<tr class="type"><th>type:</th><td>{readable_type(entry)}</td>\n')
            if 'entailmentRegime' in entry:
                out.write(f'<tr class="regime"><th>regime:</th><td>{entry["entailmentRegime"]}</td>\n')
            recognized = entry.get('recognizedDatatypes')
            if recognized:
                out.write(f'<tr class="recognized"><th>recognizing:</th><td>{" ".join(recognized)}</td>\n')
            unrecognized = entry.get('unrecognizedDatatypes')
            if unrecognized:
                out.write(f'<tr class="unrecognized"><th>ignoring:</th><td>{" ".join(unrecognized)}</td>\n')
            out.write("</table>\n")

            write_file(out, entry['action'], dir)
            out.write(f"<div>{result_message(entry)}</div>\n")
            result = entry.get('result')
            if result is False:
                out.write("<div>a contradiction</div>")
            elif result:
                write_file(out, entry['result'], dir, cls="result")
            if 'comment' in entry:
                out.write(f"<p>{entry['comment']}</p>\n")
            out.write("</section>")


def readable_type(entry: dict) -> str:
    typ = entry['@type']
    return {
        'PositiveEntailmentTest': 'positive entailment test',
        'NegativeEntailmentTest': 'negative entailment test',
    }.get(typ, typ)

def write_file(out, relative_url, current_dir, cls=None):
    out.write(f'<div><code><a href="{relative_url}">{relative_url}</a></code></div>\n')
    try:
        with current_dir.joinpath(*relative_url.split('/')).open() as f:
            out.write("<pre")
            if cls is not None:
                out.write(f" class=\"{cls}\"")
            out.write(">\n")
            quoted = f.read().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            out.write(quoted)
    except Exception as e:
        msg = "(problem rendering file) %s\n" % e
        out.write(msg)
        print(f"{relative_url}:", msg)
    finally:
        out.write("</pre>\n")

def result_message(entry: dict) -> str:
    typ = entry['@type']
    msg = {
        'PositiveEntailmentTest': 'MUST entail',
        'NegativeEntailmentTest': 'MUST NOT entail',
        'PositiveSyntaxTest': 'MUST be accepted',
        'NegativeSyntaxTest': 'MUST be rejected',
        'TestTurtlePositiveSyntax': 'MUST be accepted',
        'TestTurtleNegativeSyntax': 'MUST be rejected',
    }.get(typ)
    if msg is None:
        if typ.startswith('Netagitve'):
            msg = 'MUST NOT result into'
        else:
            msg = 'MUST result into'
    return msg

def open_manifest(path: Path) -> dict:
    if path.suffix == ".jsonld":
        with path.open() as f:
            return json.load(f)
    if path.suffix == ".ttl":
        return rdf_to_json("turtle", path)

def rdf_to_json(format, path: Path) -> dict:
    try:
        import rdflib
        from pyld import jsonld
    except ImportError:
        eprint("In order to process TTL manifests, you need RDFlib and PyLD:") 
        eprint("  python -m pip install rdflib PyLD") 
        return None
    g = rdflib.Graph()
    with path.open() as f:
        g.load(f, format=format)
    nq = g.serialize(format="ntriples").decode("utf-8")

    extended = jsonld.from_rdf(nq)
    with DIR.joinpath("manifest-context.jsonld").open() as f:
        frame = json.load(f)
    manifest = jsonld.frame(extended, frame)

    # ugly hack to "relativize" IRIs
    manifest = json.dumps(manifest)
    manifest = manifest.replace(f'file://{path.absolute()}#', "#")
    manifest = manifest.replace(f'file://{path.parent.absolute()}/', "")
    manifest = json.loads(manifest)

    return manifest

def eprint(*args, **kw):
    kw.setdefault('file', sys.stderr)
    print(*args, **kw)

STYLE = '''
<style>
    .included a, .entries a {
        text-decoration: none;
    }

    .included a:hover, .entries a:hover {
        text-decoration: underline;
    }

    .entries .rejected {
        text-decoration: line-through red;
    }

    .entries .approved::after {
        content: "✓";
    }

    .entry h2 a {
        text-decoration: none;
    }

    .approved tr.status td {
        color: darkGreen;
    }

    .proposed tr.status td {
        color: orange;
    }

    .rejected tr.status td {
        color: red;
    }

    tr.recognized td, tr.unrecognized td {
        font-family: monospace;
    }

    pre {
        border: thin solid black;
        background-color: lightYellow;
        padding: .6em 1em;
    }

    .TestTurtleNegativeSyntax pre, .NegativeSyntaxTest pre, .NegativeEntailmentTest pre.result {
        background-color: lightPink;
    }
</style>
''' 

main()
