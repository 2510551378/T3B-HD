"""Try single-byte XOR / nibble-swap / 16-bit transforms on SEDB payload to reveal GBK or UTF-8 text."""
import glob
import os
import sys

SEQ = os.path.join(os.path.dirname(__file__), "extract", "sedb")
COMMON = set("的一是我不了人你在有他这中大来上国个到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都然没日于起还发成事只作当想看文无开手十用主行方又如前所本见经头面公同三已老从动两长知民样现分将外但身些与高意进把法此实回二理美点月明其种声全工己话儿者向情部正名定女问力机给等几很业最间新什打便位因重被走电四第门相次东政海口使教西再平真听世气信北少关并内加化由却代军产入先山五太水万市眼体别处总才场师书比住员九笑性通目华报立马命张活难神数件安表原车白应路期叫死常提感金何更反合放做系计或司利受光王果亲界及今京务制解各任至清物台象记边共风战干接它许八特觉望直服毛林题建南度统色字请交爱让认算论百吃义科怎元社术结六功指思非流每青管夫连远资队跟带花快条院变联言权往展该领传近留红治决周保达办运武半候七必城父强步完革深区即求品士转量空甚众技轻程告江语英基派满式李息写呢识极令黄德收脸钱党倒未持取设始版双历越史商千片容研像找友孩站广改议形委早房音火际则首单据导影失拿网香似斯专石若兵弟谁校读志飞观争究包组造落视济喜离虽坐集编宝谈府拉黑且随格尽剑讲布杀微怕母调局根曾准团段终乐切级克精哪官示冷域吗即吧啊")


def gbk_score(blob):
    """Count of decodable common CJK chars, greedy 2-byte decode."""
    score = 0
    i = 0
    n = len(blob)
    while i + 1 < n:
        b = blob[i]
        if 0x81 <= b <= 0xFE and 0x40 <= blob[i + 1] <= 0xFE and blob[i + 1] != 0x7F:
            try:
                ch = bytes(blob[i:i + 2]).decode("gbk")
            except Exception:
                i += 1
                continue
            if ch in COMMON:
                score += 1
            i += 2
        else:
            i += 1
    return score


def utf8_score(blob):
    score = 0
    i = 0
    n = len(blob)
    while i + 2 < n:
        b = blob[i]
        if 0xE4 <= b <= 0xE9 and 0x80 <= blob[i + 1] <= 0xBF and 0x80 <= blob[i + 2] <= 0xBF:
            try:
                ch = bytes(blob[i:i + 3]).decode("utf-8")
            except Exception:
                i += 1
                continue
            if ch in COMMON:
                score += 1
            i += 3
        else:
            i += 1
    return score


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = sorted(glob.glob(os.path.join(SEQ, "sedb_*.bin")))
    print(f"{len(files)} files")
    best = []
    for p in files[:80]:
        with open(p, "rb") as f:
            blob = f.read()[0xC0:]
        base_g = gbk_score(blob)
        base_u = utf8_score(blob)
        for key in range(1, 256):
            x = bytes(b ^ key for b in blob[:200000])
            g = gbk_score(x)
            if g > 200:
                best.append((g, "xor%02x" % key, os.path.basename(p), base_g))
        if base_u > 50:
            best.append((base_u, "utf8-plain", os.path.basename(p), base_u))
        best.append((base_g, "gbk-plain", os.path.basename(p), base_g))
    best.sort(reverse=True)
    print("top candidates (score, transform, file):")
    for b in best[:12]:
        print(f"  {b[0]:>6}  {b[1]:>12}  {b[2]}")


if __name__ == "__main__":
    main()
