"""Rebuild static/fonts/materialsymbols-outlined-subset.woff2 with only the icons the site uses.

The full Material Symbols font is 1.1 MB; the subset (~90 KB) keeps every icon name that
appears anywhere in templates/, static/js/, app.py or seo_engine.py. Run it after using a
new icon name, otherwise that icon shows as plain text.

Needs fontTools + brotli (dev only, not in requirements.txt):
    python -m pip install fonttools brotli
    python subset_icon_font.py --write
"""
import glob, re, sys
from fontTools.ttLib import TTFont

SRC = "static/fonts/materialsymbols-outlined.woff2"
font = TTFont(SRC)
cmap = font.getBestCmap()
glyph_char = {g: chr(c) for c, g in cmap.items()}

# ligature name -> glyph
ligs = {}
for lookup in font["GSUB"].table.LookupList.Lookup:
    for st in lookup.SubTable:
        if st.LookupType == 7:
            st = st.ExtSubTable
        if getattr(st, "LookupType", None) != 4:
            continue
        for first, seqs in st.ligatures.items():
            for lig in seqs:
                comps = [first] + list(lig.Component)
                name = "".join(glyph_char.get(g, "?") for g in comps)
                ligs.setdefault(name, lig.LigGlyph)

# every word-like token in templates / js / python that render icons
words = set()
files = glob.glob("templates/**/*.html", recursive=True) + glob.glob("static/js/**/*.js", recursive=True) + ["app.py", "seo_engine.py"]
for f in files:
    words |= set(re.findall(r"[a-z0-9_]{2,}", open(f, encoding="utf-8", errors="ignore").read()))
used = sorted(n for n in ligs if n in words)
print("ligatures in font:", len(ligs), "| used candidates:", len(used))
print(" ".join(used))

if "--write" in sys.argv:
    from fontTools import subset
    keep = set(used)
    wanted_glyphs = {ligs[n] for n in keep}
    # Drop every ligature we do not use, so the subsetter's closure keeps only ours.
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            if st.LookupType == 7:
                st = st.ExtSubTable
            if getattr(st, "LookupType", None) != 4:
                continue
            for first in list(st.ligatures):
                st.ligatures[first] = [l for l in st.ligatures[first] if l.LigGlyph in wanted_glyphs]
                if not st.ligatures[first]:
                    del st.ligatures[first]
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    chars = set("".join(keep)) | set("abcdefghijklmnopqrstuvwxyz0123456789_ ")
    sub.populate(text="".join(sorted(chars)), glyphs=sorted(wanted_glyphs))
    sub.subset(font)
    font.flavor = "woff2"
    out = "static/fonts/materialsymbols-outlined-subset.woff2"
    font.save(out)
    import os
    print("wrote", out, os.path.getsize(out), "bytes (was", os.path.getsize(SRC), ")")
