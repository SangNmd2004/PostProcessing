"""
Cycle model of the decoder layer schedule (rtl/ldpc/ldpc_ir_decoder.v) and the per-layer gaps stored in the ROM.

One edge (non-zero circulant) is issued per cycle, in ROM order (ascending column inside a layer). Times are issue
cycles of the RTL `issue_e` counter.

Schedule "overlap" (RTL; APP / C2V RAMs with output register since 2026-10-24):
  * read phase of layer k: edges issued at T_0 .. T_last; r1b of the last edge at T_last + 5 starts the write
    phase, first write issue S_0 = T_last + RD_TO_WR (6). calc_en (r2 of the last edge) registers min1/min2/rsgn
    exactly when w0 of the first write needs them.
  * next layer (k < mb-1) starts reading at S_last + gap_k without waiting for the write pipeline to drain.
    A write of column X issued at S lands in the APP RAM at the end of S + 8 (w0 w1 w2 w2b w2c w2d, APP write
    register); a read issued at T samples the RAM at the end of T + 1, so the read sees stale data when
    1 <= T - S <= HAZ (7). gap_k = the smallest value >= MIN_GAP (2: a read in r0 and a write in w1 never need
    the shared shifter control in the same cycle) for which no column shared by layers k and k+1 conflicts.
    gap_k goes into the ROM (gen_rom.py); there is no stall logic. The RTL simulation asserts the property.
  * last layer of the iteration: wait until its last APP write and the sign-change flag landed (S_LEND), next
    iteration's first read at S_last + LAST_GAP (11).
Schedule "overlap10" (2026-10-11 .. 10-23, latency-1 RAMs): RD_TO_WR 5, HAZ 5, gap 2, LAST_GAP 9.
Schedule "serial" (2026-10-10): 2 deg + 12 cycles per layer (S_CALC and S_LEND states, full drain).
"""
import ir_model as m

PARAMS = {
    "overlap":   dict(RD_TO_WR=6, HAZ=7, MIN_GAP=2, LAST_GAP=11),
    "overlap10": dict(RD_TO_WR=5, HAZ=5, MIN_GAP=2, LAST_GAP=9),
}
GAP_W = 4                         # ROM field width of layer_gap


def layer_cols(base):
    return [[c for c, s in enumerate(row) if s >= 0] for row in base]


def layer_gaps(base, schedule="overlap"):
    """gap_k for every layer k (the value of the last layer is unused: it drains)."""
    p = PARAMS[schedule]
    cols = layer_cols(base)
    gaps = []
    for k, cl in enumerate(cols):
        if k == len(cols) - 1:
            gaps.append(p["MIN_GAP"])
            continue
        d = len(cl)
        pos = {c: i for i, c in enumerate(cl)}
        need = p["MIN_GAP"]
        for i, c in enumerate(cols[k + 1]):
            if c in pos:
                # read of c at S_last + gap + i, its write at S_last - (d - 1 - pos[c]): T - S >= HAZ + 1
                need = max(need, p["HAZ"] + 1 - i - (d - 1 - pos[c]))
        gaps.append(need)
    return gaps


def iteration_cycles(base, schedule="overlap"):
    """Cycles of one decoding iteration in steady state."""
    cols = layer_cols(base)
    if schedule == "serial":
        return sum(2 * len(c) + 12 for c in cols)
    p = PARAMS[schedule]
    gaps = layer_gaps(base, schedule)
    # per layer: d reads, last read -> first write RD_TO_WR, d writes, last write -> next read (gap / LAST_GAP)
    return (sum(2 * len(c) - 2 + p["RD_TO_WR"] for c in cols) + sum(gaps[:-1]) + p["LAST_GAP"])


def margin(base, schedule="overlap"):
    """min over shared columns of (read issue - write issue) - HAZ with the ROM gaps; >= 1 means no conflict."""
    p = PARAMS[schedule]
    cols = layer_cols(base)
    gaps = layer_gaps(base, schedule)
    t, worst = 0, 99
    last_writes = {}
    for k, cl in enumerate(cols):
        for i, c in enumerate(cl):
            if c in last_writes:
                worst = min(worst, (t + i) - last_writes[c] - p["HAZ"])
        s0 = t + len(cl) - 1 + p["RD_TO_WR"]
        last_writes = {c: s0 + q for q, c in enumerate(cl)}
        t = s0 + len(cl) - 1 + (gaps[k] if k < len(cols) - 1 else p["LAST_GAP"])
    return worst


if __name__ == "__main__":
    codes = m.load_codes(128)
    print(f"{'code':5} {'E':>3} {'serial':>7} {'10-11':>6} {'10-24':>6} {'margin':>7}  gaps")
    for n in m.CODE_ORDER:
        b = codes[n]
        print(f"{n:5} {m.edge_list(b)[1]:3d} {iteration_cycles(b, 'serial'):7d} {iteration_cycles(b, 'overlap10'):6d} "
              f"{iteration_cycles(b):6d} {margin(b):7d}  {layer_gaps(b)[:-1]}")
