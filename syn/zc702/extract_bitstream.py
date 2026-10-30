"""Use the bitstream embedded by Vivado as the canonical external artifact."""
from pathlib import Path
from zipfile import ZipFile
import sys

xsa, destination = map(Path, sys.argv[1:3])
with ZipFile(xsa) as z:
    if z.testzip() is not None:
        raise SystemExit('XSA ZIP integrity check failed')
    names = [n for n in z.namelist() if n.endswith('.bit')]
    if len(names) != 1:
        raise SystemExit('Expected exactly one embedded bitstream')
    destination.write_bytes(z.read(names[0]))
print('XSA_BITSTREAM_EXTRACTED', destination)
