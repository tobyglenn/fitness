"""Minimal stdlib HTML DOM: parse, query and re-serialize report HTML.

Only what ingest_reports.py needs — no third-party dependencies, so the
ingest step runs anywhere python3 does (DGX pipeline, GitHub Actions).
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
RAW_TEXT = {"script", "style"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict | None = None, parent: "Node | None" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []
        self.parent = parent

    # ---- queries -----------------------------------------------------------
    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def has_class(self, name: str) -> bool:
        return name in self.classes

    def elements(self):
        return [c for c in self.children if isinstance(c, Node)]

    def iter(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def find_all(self, tag: str | tuple | None = None, cls: str | None = None):
        tags = (tag,) if isinstance(tag, str) else tag
        return [
            n for n in self.iter()
            if (tags is None or n.tag in tags) and (cls is None or n.has_class(cls))
        ]

    def find(self, tag=None, cls=None):
        found = self.find_all(tag, cls)
        return found[0] if found else None

    def text(self) -> str:
        out = []
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            elif c.tag not in RAW_TEXT:
                out.append(c.text())
        return "".join(out)

    def remove(self) -> None:
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None

    # ---- serialization -----------------------------------------------------
    def inner_html(self) -> str:
        return "".join(serialize(c) for c in self.children)

    def outer_html(self) -> str:
        return serialize(self)


def serialize(node) -> str:
    if isinstance(node, str):
        return escape(node, quote=False)
    attrs = "".join(
        f' {k}' if v is None else f' {k}="{escape(v, quote=True)}"'
        for k, v in node.attrs.items()
    )
    if node.tag in VOID:
        return f"<{node.tag}{attrs}>"
    inner = "".join(
        c if isinstance(c, str) and node.tag in RAW_TEXT else serialize(c)
        for c in node.children
    )
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(node)

    def handle_endtag(self, tag):
        # Pop to the nearest matching open element; ignore stray end tags.
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if data:
            self.cur.children.append(data)


def parse(html: str) -> Node:
    b = _Builder()
    b.feed(html)
    b.close()
    return b.root
