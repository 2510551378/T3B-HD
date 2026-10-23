"""Build the asset-library manifest: per-pack geometry stats + texture count + bundles."""
import csv
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out")
MESH = os.path.join(OUT, "meshes")
TEX = os.path.join(OUT, "textures")


def bbox(path):
    mn = [1e9] * 3
    mx = [-1e9] * 3
    n = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()
                v = (float(x), float(y), float(z))
                for i in range(3):
                    if v[i] < mn[i]:
                        mn[i] = v[i]
                    if v[i] > mx[i]:
                        mx[i] = v[i]
                n += 1
    return mn, mx, n


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    idx = {r["pack"]: r for r in csv.DictReader(open(os.path.join(MESH, "index.csv"), encoding="utf-8"))}
    tex = {}
    for p in glob.glob(os.path.join(TEX, "*.png")):
        base = os.path.basename(p)
        key = "0x" + base[1:9]
        tex[key] = tex.get(key, 0) + 1

    rows = []
    for pack, meta in sorted(idx.items()):
        obj = os.path.join(MESH, meta["obj"])
        if not os.path.exists(obj):
            continue
        mn, mx, n = bbox(obj)
        rows.append({
            "pack": pack,
            "type": meta["type"],
            "verts": int(meta["verts"]),
            "tris": int(meta["tris"]),
            "runs": int(meta["runs"]),
            "dx": round(mx[0] - mn[0], 2),
            "dy": round(mx[1] - mn[1], 2),
            "dz": round(mx[2] - mn[2], 2),
            "floor_y": round(mn[1], 2),
            "ceil_y": round(mx[1], 2),
            "textures": tex.get(pack, 0),
            "obj": meta["obj"],
        })
    rows.sort(key=lambda r: -r["tris"])

    csv_path = os.path.join(OUT, "assets.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    tot_v = sum(r["verts"] for r in rows)
    tot_t = sum(r["tris"] for r in rows)
    tot_x = sum(r["textures"] for r in rows)
    md = []
    md.append("# 素材库清单（The 3rd Birthday / ULJM-05798）\n")
    md.append(f"- 容器 **{len(rows)}** 个（全部 type 8）")
    md.append(f"- 顶点 **{tot_v:,}**，三角面 **{tot_t:,}**")
    md.append(f"- 贴图 **{tot_x:,}** 张（4bpp 调色板，几乎全灰阶 = 细节图）")
    md.append("- 单位：米（`raw / 32768 × 3.125`）。Y 是上。\n")
    md.append("## 怎么用\n")
    md.append("```")
    md.append("out/blend/packs_all.blend     91 个容器，网格排列，顶点色已接进材质")
    md.append("out/blend/packs_sample.blend  4 个容器，先试手")
    md.append("out/blend/room_inside.blend   单房间 + 屋内相机")
    md.append("out/blend/room_split.blend    单房间按 floor/wall/prop/slab 拆开")
    md.append("out/blend/bind_444e5000.blend 37 个对象 + 21 张贴图材质槽（手绑）")
    md.append("out/blend/auto_444e5000.blend 顶点色 × 灰阶细节图（自动近似）")
    md.append("out/meshes/*.obj              逐容器 OBJ（仅位置 + 面）")
    md.append("out/textures/*.png            逐容器贴图")
    md.append("```\n")
    md.append("## 按面数排序（前 20）\n")
    md.append("| pack | 面数 | 顶点 | 尺寸 (m) | 层高 y | 贴图 |")
    md.append("|---|---|---|---|---|---|")
    for r in rows[:20]:
        md.append(f"| `{r['pack']}` | {r['tris']:,} | {r['verts']:,} | "
                  f"{r['dx']}×{r['dy']}×{r['dz']} | {r['floor_y']}..{r['ceil_y']} | {r['textures']} |")
    md.append("\n## 最小的 10 个（可能是走廊 / 单个道具）\n")
    md.append("| pack | 面数 | 顶点 | 尺寸 (m) |")
    md.append("|---|---|---|---|")
    for r in sorted(rows, key=lambda x: x["tris"])[:10]:
        md.append(f"| `{r['pack']}` | {r['tris']:,} | {r['verts']:,} | {r['dx']}×{r['dy']}×{r['dz']} |")
    md.append("\n## 尺寸分布\n")
    hs = sorted(r["dy"] for r in rows)
    md.append(f"- 层高：min {hs[0]} / 中位 {hs[len(hs)//2]} / max {hs[-1]} m")
    ws = sorted(max(r["dx"], r["dz"]) for r in rows)
    md.append(f"- 平面尺寸：min {ws[0]} / 中位 {ws[len(ws)//2]} / max {ws[-1]} m")
    md.append(f"\n完整逐包数据见 `out/assets.csv`（{len(rows)} 行）。")

    md_path = os.path.join(OUT, "ASSET_LIBRARY.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print(f"{len(rows)} packs -> {csv_path}")
    print(f"-> {md_path}")
    print(f"verts {tot_v:,} tris {tot_t:,} textures {tot_x:,}")


if __name__ == "__main__":
    main()
