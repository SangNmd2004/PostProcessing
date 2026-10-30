"""
Choice and order of the d modulated (punctured / later shortened) positions D of a mother code.

Blind reconciliation starts with all d positions of D punctured (LLR 0) and converts them one by one into
shortened positions (value revealed). Which positions form D, and in which order they are revealed, matters a lot
when many positions are punctured on a high-rate code (r56: 307 punctured nodes on 512 checks).

Random choice (old behaviour): checks with >= 2 punctured neighbours give no information on them, so many punctured
nodes cannot be recovered in the first iterations.

Grouping & sorting style greedy (Ha et al. 2006, used by Zhu et al. JLT 2022), adapted to a fixed d:
  * a punctured node u is 1-step recoverable (1-SR) while it has a "surviving" check: a neighbour check whose
    only punctured neighbour is u. surv(u) = number of such checks.
  * phase 1: add the node v that becomes 1-SR (has a check with no punctured neighbour) without taking the last
    surviving check of an already punctured node. Among those: most clean checks (reliable recovery, "reliable"
    variant, default) or fewest clean checks ("compact" variant: every one of the 307 nodes stays 1-SR, but each
    is recovered from a single check), then fewest checks taken from other punctured nodes, then lowest degree.
  * phase 2 (no 1-SR candidate left): add the node with the most checks whose punctured neighbours stay 1-SR
    through another check (v is then 2-SR), without breaking any 1-SR node.
  * phase 3: least damage.
Selection order = "best punctured first". Reveal (shortening) order is the reverse: the hardest-to-recover
punctured nodes are revealed first, the best ones stay punctured longest.

pos_d returned by order() is in REVEAL order (index 0 is revealed first), i.e. what dyn_ir / the firmware stream.

Measured (results/exp_punct.txt, 200 frames, step 16): "reliable" beats random and "compact" on every code,
e.g. r34 @ 2 %: f 1.48 -> 1.32, attempts 8.5 -> 4.4; r56 @ 0.5 %: f 2.18 -> 1.76, attempts 5.3 -> 2.0.
The number of 1-SR nodes is NOT the right figure of merit here: a node recovered from several clean checks
gets a much more reliable message than one recovered from a single check.
"""
import json
import os

import numpy as np

import ir_model as m

HERE = os.path.dirname(os.path.abspath(__file__))
PUNCT_JSON = os.path.join(HERE, "punct.json")


def graph(base, zc):
    """Adjacency of the lifted code: var_chk[v] = list of checks, chk_var[c] = list of vars."""
    n = m.NCOL * zc
    var_chk = [[] for _ in range(n)]
    chk_var = [[] for _ in range(len(base) * zc)]
    for l, row in enumerate(base):
        for c, s in enumerate(row):
            if s < 0:
                continue
            for j in range(zc):
                v = c * zc + (j + s) % zc
                ch = l * zc + j
                var_chk[v].append(ch)
                chk_var[ch].append(v)
    return var_chk, chk_var


def recovery_steps(var_chk, chk_var, punct):
    """Step at which every punctured node is recovered by the 'all other neighbours known' rule (0: unpunctured,
    -1: never)."""
    n = len(var_chk)
    step = np.where(punct, -1, 0)
    k = 0
    while True:
        k += 1
        new = []
        for v in np.nonzero(step == -1)[0]:
            for ch in var_chk[v]:
                if all(step[u] >= 0 and step[u] < k for u in chk_var[ch] if u != v):
                    new.append(v)
                    break
        if not new:
            break
        step[new] = k
    return step


def gs_select(base, zc, d, seed=1, compact=False):
    """Greedy grouping & sorting selection of d positions. Returns the selection order (best first)."""
    rng = np.random.default_rng(seed)
    var_chk, chk_var = graph(base, zc)
    n = len(var_chk)
    tie = rng.random(n)                       # random tie-break so the pattern does not follow the QC structure
    cnt = np.zeros(len(chk_var), dtype=np.int64)
    pl = [[] for _ in range(len(chk_var))]    # punctured neighbours per check
    punct = np.zeros(n, dtype=bool)
    surv = np.zeros(n, dtype=np.int64)
    order = []
    while len(order) < d:
        best, best_key = -1, None
        for v in range(n):
            if punct[v]:
                continue
            chks = var_chk[v]
            clean = 0
            taken = 0
            breaks = 0
            via2 = 0
            for ch in chks:
                k = cnt[ch]
                if k == 0:
                    clean += 1
                elif k == 1:
                    u = pl[ch][0]
                    taken += 1
                    if surv[u] <= 1:
                        breaks += 1
                    elif surv[u] >= 2:
                        via2 += 1             # u stays 1-SR through another check -> v recoverable at step 2 via ch
            if clean > 0 and breaks == 0:
                # compact: take as few clean checks as possible (more nodes can stay 1-SR); else most clean checks
                key = (3, -clean if compact else clean, -taken, -len(chks), tie[v])
            elif breaks == 0 and via2 > 0:
                key = (2, via2, -taken, -len(chks), tie[v])
            else:
                key = (1, -breaks, -taken, -len(chks), tie[v])
            if best_key is None or key > best_key:
                best, best_key = v, key
        v = best
        punct[v] = True
        order.append(v)
        for ch in var_chk[v]:
            if cnt[ch] == 1:
                surv[pl[ch][0]] -= 1
            cnt[ch] += 1
            pl[ch].append(v)
            if cnt[ch] == 1:
                surv[v] += 1
    return order


def order(name, base, zc, d, regenerate=False):
    """Positions of D in reveal order for code `name` (cached in punct.json, shared with gen_vectors / firmware)."""
    allp = {}
    if os.path.exists(PUNCT_JSON):
        with open(PUNCT_JSON) as fh:
            allp = json.load(fh)
    key = f"{zc}/{d}/{name}"
    if regenerate or key not in allp:
        sel = gs_select(base, zc, d)
        allp[key] = sel[::-1]
        with open(PUNCT_JSON, "w") as fh:
            json.dump(allp, fh)
    return np.array(allp[key], dtype=np.int64)


def write_header(path, zc=128, delta=0.10):
    """firmware/qkd_punct_tables.h: D positions of every code in reveal order (same data as punct.json)."""
    n = m.NCOL * zc
    d = int(round(delta * n))
    codes = m.load_codes(zc)
    L = ["/* AUTO-GENERATED by model/puncture.py from model/punct.json - do not edit by hand.",
         f" * Modulated positions D (d = {d} of n = {n}) per mother code, in REVEAL order: index 0 is revealed first.",
         " * Bob streams symbol 2 (punctured) at these positions; Alice fills them with private random bits and",
         " * reveals them in this order. Chosen by grouping & sorting ('reliable' variant, model/puncture.py). */",
         "#ifndef QKD_PUNCT_TABLES_H", "#define QKD_PUNCT_TABLES_H", "#include <stdint.h>", "",
         f"#define QKD_PUNCT_D {d}u", "",
         f"static const uint16_t qkd_punct_pos[{len(m.CODE_ORDER)}][{d}] = {{"]
    for name in m.CODE_ORDER:
        pos = order(name, codes[name], zc, d)
        L.append(f"    /* {name} */ {{")
        for i in range(0, d, 16):
            L.append("        " + ", ".join(f"{int(p):4d}" for p in pos[i:i + 16]) + ",")
        L.append("    },")
    L += ["};", "", "#endif", ""]
    with open(path, "w", newline="\n") as fh:
        fh.write("\n".join(L))


def report(base, zc, pos):
    var_chk, chk_var = graph(base, zc)
    punct = np.zeros(m.NCOL * zc, dtype=bool)
    punct[pos] = True
    st = recovery_steps(var_chk, chk_var, punct)[pos]
    return {k: int((st == k).sum()) for k in sorted(set(st.tolist()))}


if __name__ == "__main__":
    import time
    zc = 128
    d = int(round(0.10 * m.NCOL * zc))
    codes = m.load_codes(zc)
    rng = np.random.default_rng(0)
    for name in m.CODE_ORDER:
        t = time.time()
        p = order(name, codes[name], zc, d, regenerate=True)
        print(f"{name}: GS steps {report(codes[name], zc, p)}  random {report(codes[name], zc, rng.choice(m.NCOL * zc, d, replace=False))}"
              f"  ({time.time() - t:.0f} s)", flush=True)
    write_header(os.path.join(HERE, "..", "firmware", "qkd_punct_tables.h"), zc)
    print("wrote firmware/qkd_punct_tables.h")
