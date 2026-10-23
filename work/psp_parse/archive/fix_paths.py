"""One-off: rewrite stale paths inside docs/解析报告.md after the reorganisation."""
import io
import re

P = r"C:\Users\25105\Documents\寄生前夜第四日\work\psp_parse\docs\解析报告.md"

SUBS = [
    ("work/psp_parse/psp_pack.py", "work/psp_parse/tools/psp_pack.py"),
    ("work/psp_parse/pack_export.py", "work/psp_parse/tools/pack_export.py"),
    ("work/psp_parse/pack_tex.py", "work/psp_parse/tools/pack_tex.py"),
    ("work/psp_parse/pack_bundle.py", "work/psp_parse/tools/pack_bundle.py"),
    ("work/psp_parse/解析报告.md", "work/psp_parse/docs/解析报告.md"),
    ("work/psp_parse/export/", "work/psp_parse/out/meshes/"),
    ("work/psp_parse/tex/", "work/psp_parse/out/textures/"),
    ("work/psp_parse/runs/", "work/psp_parse/out/runs/"),
    ("work/psp_parse/bundle", "work/psp_parse/out/bundle"),
    ("extract/packs/", "raw/packs/"),
    ("extract/packs", "raw/packs"),
    ("extract/sedb", "raw/sedb"),
    ("extract/3rd.pkg", "raw/3rd.pkg"),
    ("extract/`", "raw/`"),
    ("extract/", "raw/"),
    ("`extract`", "`raw`"),
]

s = io.open(P, encoding="utf-8").read()
n = 0
for a, b in SUBS:
    c = s.count(a)
    if c:
        s = s.replace(a, b)
        n += c
io.open(P, "w", encoding="utf-8").write(s)
print("replacements:", n)
left = sorted(set(m.group(0) for m in re.finditer(r"[^\s`()]*extract/[^\s`()]*", s)))
print("remaining extract refs:", left[:10])
