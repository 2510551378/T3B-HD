"""Per-file encoding detection across all SEDB files: which codec yields common Chinese chars."""
import collections
import glob
import os
import sys

SEQ = os.path.join(os.path.dirname(__file__), "extract", "sedb")
COMMON = "的一是我不了人你在有他这中大来上国个到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都然没日于起还发成事只作当想看文无开手十用主行方又如前所本见经头面公同三已老从动两长知民样现分将外但身些与高意进把法此实回二理美点月明其种声全工己话儿者向情部正名定女问力机给等几很业最间新什打便位因重被走电四第门相次东政海口使教西再平真听世气信北少关并内加化由却代军产入先山五太水万市眼体别处总才场师书比住员九笑性通目华报立马命张活难神数件安表原车白应路期叫死常提感金何更反合放做系计或司利受光王果亲界及今京务制解各任至清物台象记边共风战干接它许八特觉望直服毛林题建南度统色字请交爱让认算论百吃义科怎元社术结六功指思非流每青管夫连远资队跟带花快条院变联言权往展该领传近留红治决周保达办运武半候七必城父强步完革深区即求品士转量空甚众技轻程告江语英基派满式李息写呢识极令黄德收脸钱党倒未持取设始版双历越史商千片容研像找友孩站广改议形委早房音火际则首单据导影失拿网香似斯专石若兵弟谁校读志飞观争究包组造落视济喜离虽坐集编宝谈府拉黑且随格尽剑讲布杀微怕母调局根曾准团段终乐切级克精哪官示冷域吗即吧啊"

CODECS = ["gbk", "gb18030", "big5", "shift_jis", "utf-16-le", "utf-16-be", "utf-8"]


def patterns(codec, chars=COMMON[:30]):
    out = []
    for ch in chars:
        try:
            out.append(ch.encode(codec))
        except Exception:
            pass
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = sorted(glob.glob(os.path.join(SEQ, "sedb_*.bin")))
    pats = {c: patterns(c) for c in CODECS}
    rows = []
    for p in files:
        with open(p, "rb") as f:
            blob = f.read()
        row = {"file": os.path.basename(p), "size": len(blob)}
        for c in CODECS:
            n = 0
            for pat in pats[c]:
                n += blob.count(pat)
            row[c] = n
        rows.append(row)
    tot = {c: sum(r[c] for r in rows) for c in CODECS}
    print("total hits over 245 SEDB files:", tot)
    print()
    best = sorted(rows, key=lambda r: -max(r[c] for c in CODECS))[:12]
    hdr = f"{'file':>34} {'size':>9} " + " ".join(f"{c[:9]:>9}" for c in CODECS)
    print(hdr)
    for r in best:
        print(f"{r['file']:>34} {r['size']:>9,} " +
              " ".join(f"{r[c]:>9}" for c in CODECS))


if __name__ == "__main__":
    main()
