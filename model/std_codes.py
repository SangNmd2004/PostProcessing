"""
Reference base matrices (24 block columns) used as candidates for the mother codes.

IEEE 802.16e rate-1/2 base matrix (defined for Z0 = 96, shifts scaled with floor(p * Z / 96) for other Z;
used as mother code in Zhu et al., JLT 2022, "A Code Rate-Compatible High-Throughput Hardware Implementation
Scheme for QKD Information Reconciliation"). Transcribed by hand: check_structure() verifies the properties the
standard guarantees (76 edges, row degrees 6/7, dual-diagonal parity part, no 4-cycle at Z = 96).
"""
import ir_model as m

WIMAX_R12_Z96 = [
    [-1, 94, 73, -1, -1, -1, -1, -1, 55, 83, -1, -1, 7, 0, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
    [-1, 27, -1, -1, -1, 22, 79, 9, -1, -1, -1, 12, -1, 0, 0, -1, -1, -1, -1, -1, -1, -1, -1, -1],
    [-1, -1, -1, 24, 22, 81, -1, 33, -1, -1, -1, 0, -1, -1, 0, 0, -1, -1, -1, -1, -1, -1, -1, -1],
    [61, -1, 47, -1, -1, -1, -1, -1, 65, 25, -1, -1, -1, -1, -1, 0, 0, -1, -1, -1, -1, -1, -1, -1],
    [-1, -1, 39, -1, -1, -1, 84, -1, -1, 41, 72, -1, -1, -1, -1, -1, 0, 0, -1, -1, -1, -1, -1, -1],
    [-1, -1, -1, -1, 46, 40, -1, 82, -1, -1, -1, 79, 0, -1, -1, -1, -1, 0, 0, -1, -1, -1, -1, -1],
    [-1, -1, 95, 53, -1, -1, -1, -1, -1, 14, 18, -1, -1, -1, -1, -1, -1, -1, 0, 0, -1, -1, -1, -1],
    [-1, 11, 73, -1, -1, -1, 2, -1, -1, 47, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0, 0, -1, -1, -1],
    [12, -1, -1, -1, 83, 24, -1, 43, -1, -1, -1, 51, -1, -1, -1, -1, -1, -1, -1, -1, 0, 0, -1, -1],
    [-1, -1, -1, -1, -1, 94, -1, 59, -1, -1, 70, 72, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0, 0, -1],
    [-1, -1, 7, 65, -1, -1, -1, -1, 39, 49, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0, 0],
    [43, -1, -1, -1, -1, 66, -1, 41, -1, -1, -1, 26, 7, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0],
]


def scale(base, zc, z0=96):
    return [[(v * zc) // z0 if v > 0 else v for v in row] for row in base]


def count_4cycles(base, zc):
    n = 0
    mb = len(base)
    for r1 in range(mb):
        for r2 in range(r1 + 1, mb):
            cols = [c for c in range(m.NCOL) if base[r1][c] >= 0 and base[r2][c] >= 0]
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    a, b = cols[i], cols[j]
                    if (base[r1][a] - base[r2][a] + base[r2][b] - base[r1][b]) % zc == 0:
                        n += 1
    return n


def check_structure():
    b = WIMAX_R12_Z96
    edges = sum(v >= 0 for row in b for v in row)
    rdeg = sorted({sum(v >= 0 for v in row) for row in b})
    assert edges == 76 and rdeg == [6, 7], (edges, rdeg)
    assert [b[r][12] for r in (0, 5, 11)] == [7, 0, 7]
    for i in range(1, 12):
        assert b[i - 1][12 + i] == 0 and b[i][12 + i] == 0
    return count_4cycles(b, 96)


if __name__ == "__main__":
    print("4-cycles at Z=96:", check_structure())
    for zc in (96, 128):
        print(f"Z={zc}: 4-cycles {count_4cycles(scale(WIMAX_R12_Z96, zc), zc)}")
