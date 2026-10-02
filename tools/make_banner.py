#!/usr/bin/env python3
"""make_banner.py — rebuild docs/assets/psxdecomp-banner{,-dark}.svg: the pixel D (spine and bowl: red, yellow, teal,
blue) and the Exo 2 wordmark converted to outlines. Not installed into game repos; not stdlib.

    pip install fonttools uharfbuzz
    curl -sSL -o .run/Exo2-Italic.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/exo2/Exo2-Italic%5Bwght%5D.ttf"
    python3 tools/make_banner.py docs/assets [.run/Exo2-Italic.ttf]

PNGs (2x) come from any SVG renderer, e.g. `pip install resvg-py` and resvg_py.svg_to_bytes(svg_path=..., zoom=2).
"""
import sys, pathlib
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

FONT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".run/Exo2-Italic.ttf")
RED, YEL, TEAL, BLUE, GREY = "#e8202a", "#f7c600", "#00a79d", "#2f6fd6", "#c9ced6"
CELLS = [(0,0),(0,1),(0,2),(1,0),(1,3),(2,0),(2,1),(2,3),(3,0),(3,3),(4,0),(4,1),(4,2)]

def colour(r, c):
    if (r, c) == (2, 1): return GREY
    if c == 0: return RED
    if r == 0: return YEL
    if c == 3: return TEAL
    return BLUE

blob = FONT.read_bytes()
def run(text, wght, size, x, y):
    """(svg path d, advance end x, bounds) for text at weight wght, size px, pen at (x, baseline y)."""
    face = hb.Face(blob); font = hb.Font(face); font.set_variations({"wght": wght})
    upem = face.upem
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})
    tt = instantiateVariableFont(TTFont(str(FONT)), {"wght": wght})
    gs = tt.getGlyphSet(); order = tt.getGlyphOrder()
    k = size / upem
    pen = SVGPathPen(gs); bpen = BoundsPen(gs)
    cx = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = order[info.codepoint]
        t = (k, 0, 0, -k, x + (cx + pos.x_offset) * k, y - pos.y_offset * k)
        gs[name].draw(TransformPen(pen, t)); gs[name].draw(TransformPen(bpen, t))
        cx += pos.x_advance
    return pen.getCommands(), x + cx * k, bpen.bounds

def build(ink):
    size, base = 118, 194
    d1, x1, b1 = run("PSX", 900, size, 300, base)
    d2, x2, b2 = run("Decomp", 400, size, x1 + 2, base)
    right = max(b1[2], b2[2]) + 36
    rects = "".join('<rect x="%d" y="%d" width="36" height="36" rx="6" fill="%s"/>' % (70 + 42 * c, 48 + 42 * r, colour(r, c))
                    for r, c in CELLS)
    w = round(right)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="20 20 %d 260" width="%d" height="260" role="img" '
            'aria-label="PSXDecomp">\n<title>PSXDecomp</title>\n'
            '<g transform="translate(150 150) skewX(-10) translate(-150 -150)">%s</g>\n'
            '<path fill="%s" d="%s"/>\n<path fill="%s" d="%s"/>\n</svg>\n') % (w - 20, w - 20, rects, ink, d1, RED, d2)

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
(out / "psxdecomp-banner.svg").write_text(build("#14161c"))
(out / "psxdecomp-banner-dark.svg").write_text(build("#f2f4f7"))
print("written", out)
