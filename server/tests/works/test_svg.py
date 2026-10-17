import xml.etree.ElementTree as ET

import pytest

from simile.works.svg import SVG, BadSvg, checked

from .conftest import svg


def check(text: str, chars: int = 60_000, elements: int = 2_000) -> str:
    return checked(text, 288, 262, chars=chars, elements=elements, tolerance=0.1)


def test_a_clean_svg_is_sized_to_the_wall_and_cropped_to_fill_it() -> None:
    root = ET.fromstring(check(svg(300, 262)))

    assert root.tag == f"{{{SVG}}}svg"
    assert (root.get("width"), root.get("height")) == ("288", "262")
    assert root.get("preserveAspectRatio") == "xMidYMid slice"
    assert [child.tag.rpartition("}")[2] for child in root] == ["rect", "circle"]


def test_keeps_local_references_and_drops_comments() -> None:
    inside = (
        '<!-- a note --><defs><linearGradient id="g"><stop offset="0" stop-color="red"/>'
        '</linearGradient><path id="p" d="M0 0L9 9"/></defs>'
        '<rect width="9" height="9" fill="url(#g)" style="stroke: url( \'#g\' )"/>'
        '<use href="#p"/><use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#p"/>'
    )

    cleaned = check(svg(inside=inside))

    assert "a note" not in cleaned
    assert cleaned.count("<use") == 2


def test_adds_the_svg_namespace_when_it_is_missing() -> None:
    cleaned = check('<svg viewBox="0 0 288 262"><rect width="9" height="9"/></svg>')

    assert all(e.tag.startswith(f"{{{SVG}}}") for e in ET.fromstring(cleaned).iter())


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (svg(inside="<script>alert(1)</script>"), "<script> isn't allowed"),
        (svg(inside="<foreignObject><p>hi</p></foreignObject>"), "<foreignObject>"),
        (svg(inside='<image href="cat.png"/>'), "<image> isn't allowed"),
        (svg(inside='<a href="#x"><rect/></a>'), "<a> isn't allowed"),
        (svg(inside='<rect onclick="go()"/>'), "event handlers like onclick"),
        (svg(inside='<use href="other.svg#x"/>'), "points outside the SVG"),
        (
            svg(inside='<use xmlns:x="http://www.w3.org/1999/xlink" x:href="http://e.com/a"/>'),
            "points outside the SVG",
        ),
        (svg(inside='<rect fill="url(http://e.com/p.svg#g)"/>'), "refers to something outside"),
        (svg(inside="<rect style=\"fill: url('data:x')\"/>"), "refers to something outside"),
        (svg(inside="<style>@import 'x.css';</style>"), "<style> loads something"),
        (svg(inside="<style>rect { fill: url(x.svg#g) }</style>"), "<style> loads something"),
        (svg(inside='<m:x xmlns:m="http://www.w3.org/1998/Math/MathML"/>'), "<x> isn't allowed"),
        (
            '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]>' + svg(inside="&a;"),
            "DOCTYPE or ENTITY",
        ),
        ("<svg viewBox='0 0 288 262'><rect></svg>", "isn't well-formed XML"),
        ('<g viewBox="0 0 288 262"/>', "root element isn't <svg>"),
        ('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>', 'needs viewBox="0 0 288 262"'),
        (svg(100, 262), "not the wall's shape"),
        (svg(288, 0), "no area"),
        (
            svg(inside='<g id="a"><use href="#b"/></g><g id="b"/><use href="#a"/>'),
            "refers to something with another <use>",
        ),
    ],
)
def test_rejects_what_could_run_load_or_break_something(text: str, reason: str) -> None:
    with pytest.raises(BadSvg, match=reason):
        check(text)


def test_rejects_an_svg_too_long_or_with_too_many_elements() -> None:
    many = svg(inside="<rect/>" * 20)

    with pytest.raises(BadSvg, match="characters long, and the most is 100"):
        check(many, chars=100)
    with pytest.raises(BadSvg, match="23 elements, and the most is 10"):
        check(many, elements=10)
