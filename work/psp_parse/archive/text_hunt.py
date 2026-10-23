"""Locate Chinese text inside 3rd.pkg by counting high-frequency character bigrams in 3 encodings."""
import collections
import os
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864

COMMON = "的了是我你他不在人有这中大为上个国以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严龙飞"

BIGRAMS = ["的", "了", "我", "你", "是", "不", "在", "有", "他", "这"]


def encs():
    out = {}
    for ch in BIGRAMS:
        out.setdefault("gbk", []).append(ch.encode("gbk"))
        out.setdefault("utf-8", []).append(ch.encode("utf-8"))
        out.setdefault("utf-16-le", []).append(ch.encode("utf-16-le"))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    E = encs()
    totals = collections.Counter()
    where = {k: collections.Counter() for k in E}
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos, left = 0, PKG_SIZE
        CH = 1 << 22
        carry = b""
        keep = 8
        while left > 0:
            chunk = f.read(min(CH, left))
            if not chunk:
                break
            left -= len(chunk)
            buf = carry + chunk
            base = pos - len(carry)
            for enc, pats in E.items():
                for p in pats:
                    i = 0
                    while True:
                        i = buf.find(p, i)
                        if i < 0:
                            break
                        totals[enc] += 1
                        where[enc][(base + i) // (4 << 20)] += 1
                        i += 1
            carry = buf[-keep:]
            pos += len(chunk)
    print("hit counts by encoding:", dict(totals))
    for enc in E:
        if not where[enc]:
            continue
        top = where[enc].most_common(6)
        print(f"  {enc:10} windows(4MiB)->hits: " +
              ", ".join(f"{w * 4}MiB:{n}" for w, n in top))


if __name__ == "__main__":
    main()
