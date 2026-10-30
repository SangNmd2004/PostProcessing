"""Embed existing golden vectors; do not regenerate or change the QKD model."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/tb'
OUT = Path(__file__).resolve().with_name('smoke_vectors.h')

def read(name):
    return [int(s, 16) for s in (DATA / name).read_text().split()]

lines = ['/* Generated from golden hex files in data/tb. Public synthetic test data only. */',
         '#ifndef QKD_SMOKE_VECTORS_H', '#define QKD_SMOKE_VECTORS_H', '#include <stdint.h>',
         'typedef struct {',
         '    uint32_t cfg, cfg2, pre, attempts, syn_words, errcnt;',
         '    const uint32_t *ch, *syn, *reveal, *expected, *counts;',
         '    const uint64_t *key;',
         '} smoke_vector_t;']
manifest = hashlib.sha256()

def array(name, values, bits=32):
    typ = 'uint32_t' if bits == 32 else 'uint64_t'
    suffix = 'u' if bits == 32 else 'ull'
    if not values:
        values = [0]
    lines.append(f'static const {typ} {name}[] __attribute__((aligned(64))) = {{')
    for k in range(0, len(values), 4):
        lines.append('    ' + ', '.join(f'0x{x:0{bits//4}x}{suffix}' for x in values[k:k+4]) + ',')
    lines.append('};')

count = read('nblk.hex')[0]
records = []
for b in range(count):
    meta = read(f'blk_{b}.hex')
    cfg, cfg2, pre, attempts = meta[:4]
    syn = read(f'syn_{b}.hex')
    for kind, bits in [('ch', 32), ('syn', 32), ('rev', 32), ('key', 64)]:
        path = DATA / f'{kind}_{b}.hex'
        manifest.update(path.name.encode() + b'\0' + path.read_bytes())
        array(f'{kind}_{b}', read(path.name), bits)
    manifest.update((DATA / f'blk_{b}.hex').read_bytes())
    array(f'expected_{b}', meta[4:4+attempts*2:2])
    array(f'counts_{b}', meta[5:4+attempts*2:2])
    records.append(f'    {{0x{cfg:08x}u, 0x{cfg2:08x}u, {pre}u, {attempts}u, {len(syn)}u, '
                   f'{meta[4+attempts*2]}u, ch_{b}, syn_{b}, rev_{b}, expected_{b}, counts_{b}, key_{b}}},')
lines.extend(['static const smoke_vector_t smoke_vectors[] = {', *records, '};',
              f'#define SMOKE_BLOCKS {count}u'])
for name, bits in [('pa_x',32), ('pa_seed',32), ('pa_y',64)]:
    manifest.update((DATA / (name + '.hex')).read_bytes())
    array(name, read(name + '.hex'), bits)
lines.extend([f'#define SMOKE_PA_WORDS {read("pa_n.hex")[0]}u',
              f'#define SMOKE_VECTOR_SHA256 "{manifest.hexdigest()}"', '#endif'])
OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'{OUT}: {count} IR blocks + PA, vector SHA256={manifest.hexdigest()}')
