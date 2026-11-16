"""OutreachPilot final mark: "One of Many".
A grid of companies (the directory); one of them becomes a sealed letter: the one company you
write to, personally.  python brand/logo/build_final.py  ->  brand/logo/final/*.svg

Three cuts, one idea:
  full   4 x 4 grid   symbol at 48 px and up
  small  3 x 3 grid   nav/footer tiles (about 17 to 32 px)
  icon   2 x 2 grid   favicon (16 px) and app icons
The letter's fold is a real hole (fill-rule evenodd), so one-colour versions stay correct.
"""
from pathlib import Path

D = Path(__file__).parent / "final"
D.mkdir(exist_ok=True)
MOSS, INK, LIGHT, SAND, NIGHT = "#607037", "#3D4A1C", "#A9BC72", "#F0EDE3", "#07080B"


def f(x):
    return f"{x:.2f}".rstrip("0").rstrip(".")


def circ(cx, cy, r):
    return f"M{f(cx - r)} {f(cy)} a{f(r)} {f(r)} 0 1 0 {f(2 * r)} 0 a{f(r)} {f(r)} 0 1 0 {f(-2 * r)} 0 Z"


def rrect(x, y, w, h, r):
    return (f"M{f(x + r)} {f(y)} H{f(x + w - r)} A{f(r)} {f(r)} 0 0 1 {f(x + w)} {f(y + r)} V{f(y + h - r)} "
            f"A{f(r)} {f(r)} 0 0 1 {f(x + w - r)} {f(y + h)} H{f(x + r)} A{f(r)} {f(r)} 0 0 1 {f(x)} {f(y + h - r)} "
            f"V{f(y + r)} A{f(r)} {f(r)} 0 0 1 {f(x + r)} {f(y)} Z")


def letter(cx, cy, w, h):
    """A sealed letter centred on (cx, cy): rounded body with the flap fold cut out as a chevron."""
    x0, y0 = cx - w / 2, cy - h / 2
    r = w * 0.18
    a, b, t = w * 0.16, h * 0.18, h * 0.15          # chevron inset, top offset, thickness
    mid = y0 + b + (w / 2 - a)                      # exact 45 degree flap
    chevron = (f"M{f(x0 + a)} {f(y0 + b)} L{f(cx)} {f(mid)} L{f(x0 + w - a)} {f(y0 + b)} "
               f"L{f(x0 + w - a)} {f(y0 + b + t)} L{f(cx)} {f(mid + t)} L{f(x0 + a)} {f(y0 + b + t)} Z")
    return rrect(x0, y0, w, h, r) + " " + chevron


def grid(n, chosen, margin, dot_r, letter_w, letter_h):
    """n x n grid of dots on a 256 canvas; the cell `chosen` (col, row) is the letter."""
    step = (256 - 2 * margin) / (n - 1)
    # If the letter sits on an edge it overhangs the dots; shift the grid so the whole mark is centred.
    over_x, over_y = (letter_w / 2 - dot_r) / 2, (letter_h / 2 - dot_r) / 2
    dx = -over_x if chosen[0] == n - 1 else (over_x if chosen[0] == 0 else 0)
    dy = -over_y if chosen[1] == n - 1 else (over_y if chosen[1] == 0 else 0)
    px = lambda i: margin + i * step + dx
    py = lambda j: margin + j * step + dy
    dots = " ".join(circ(px(i), py(j), dot_r) for i in range(n) for j in range(n) if (i, j) != chosen)
    return dots, letter(px(chosen[0]), py(chosen[1]), letter_w, letter_h)


CUTS = {
    "full": grid(4, (2, 1), 40, 13, 62, 56),
    "small": grid(3, (2, 1), 48, 19, 84, 76),
    "icon": grid(2, (1, 0), 72, 30, 104, 94),
}


def svg(body, title, view="0 0 256 256"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" aria-label="{title}">'
            f"<title>{title}</title>{body}</svg>\n")


def two_tone(cut, dot_col, letter_col):
    dots, let = CUTS[cut]
    return f'<path fill="{dot_col}" d="{dots}"/><path fill="{letter_col}" fill-rule="evenodd" d="{let}"/>'


def on_tile(cut, bg=MOSS, fg="#FFFFFF", radius=56):
    dots, let = CUTS[cut]
    # The mark sits at 78 % of the tile so it has room to breathe inside the rounded square.
    return (f'<path fill="{bg}" d="{rrect(0, 0, 256, 256, radius)}"/>'
            f'<g transform="translate(128 128) scale(.78) translate(-128 -128)">'
            f'<path fill="{fg}" fill-opacity=".5" d="{dots}"/><path fill="{fg}" fill-rule="evenodd" d="{let}"/></g>')


T = "OutreachPilot"
files = {
    # Symbols for light and dark backgrounds
    "op-symbol.svg": two_tone("full", LIGHT, MOSS),
    "op-symbol-dark.svg": two_tone("full", "#4A5629", LIGHT),
    "op-symbol-small.svg": two_tone("small", LIGHT, MOSS),
    # One-colour
    "op-symbol-black.svg": two_tone("full", "#000000", "#000000").replace('fill="#000000" d', 'fill="#000000" fill-opacity=".45" d', 1),
    "op-symbol-white.svg": two_tone("full", "#FFFFFF", "#FFFFFF").replace('fill="#FFFFFF" d', 'fill="#FFFFFF" fill-opacity=".5" d', 1),
    # App icon and favicon tiles
    "op-app-icon.svg": on_tile("small"),
    "op-favicon.svg": on_tile("icon", radius=60),
    # iOS rounds the corners itself, so the touch icon is a full-bleed square
    "op-apple-touch.svg": on_tile("small", radius=0),
}
for name, body in files.items():
    (D / name).write_text(svg(body, T), encoding="utf-8")

# The shared site icon (symbol #logo-plane in templates/partials/icons.html): the small cut in
# currentColor, dots at half strength, the letter's fold a real hole so the tile shows through.
dots, let = CUTS["small"]
sprite = (f'<symbol id="logo-plane" viewBox="0 0 256 256"><path fill="currentColor" fill-opacity=".5" d="{dots}"/>'
          f'<path fill="currentColor" fill-rule="evenodd" d="{let}"/></symbol>')
(D / "sprite-symbol.txt").write_text(sprite, encoding="utf-8")
print("wrote", len(files), "SVGs + sprite symbol")
