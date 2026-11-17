"""measure_scale.py - find the real pixel size of scaled-up pixel art.

Pixel art for the web is usually drawn small and enlarged by a whole number
(nearest-neighbor scaling): every art pixel becomes an N x N block of
identical screen pixels. To convert it for the NES, the first step is to find
N and shrink the image back to its true size.

Method: run-length analysis. Walk along each row and count runs of identical
pixels (a run is a stretch of the same color). Every run is a whole number
of blocks long, so N divides every run length, and N is the greatest common
divisor (GCD) of them all. Same for columns, which gives the vertical scale.

Runs that touch the image's edge are skipped: if the art doesn't start
exactly on a block boundary, the edge runs are cut short and would wreck
the GCD.

Usage: .venv/bin/python tools/measure_scale.py art/*.png
"""

import sys
from math import gcd

from PIL import Image


def run_lengths(line):
    """Yield the length of each run of identical values in a sequence,
    except the first and last runs, which touch the edge."""
    runs = []
    length = 1
    for previous, current in zip(line, line[1:]):
        if current == previous:
            length += 1
        else:
            runs.append(length)
            length = 1
    runs.append(length)
    return runs[1:-1]


def scale_of(lines):
    """The GCD of every interior run length across all the lines."""
    result = 0                          # gcd(0, n) == n, so 0 is a neutral start
    for line in lines:
        for length in run_lengths(line):
            result = gcd(result, length)
    return result


def measure(path):
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    pixels = image.load()

    rows = [[pixels[x, y] for x in range(width)] for y in range(height)]
    columns = [[pixels[x, y] for y in range(height)] for x in range(width)]
    scale_x = scale_of(rows)
    scale_y = scale_of(columns)

    # Fully transparent pixels count as one color whatever RGB they hold.
    colors = {p if p[3] else (0, 0, 0, 0) for p in image.get_flattened_data()}

    print(f"{path}")
    print(f"  size on disk : {width} x {height}")
    print(f"  block size   : {scale_x} x {scale_y}")
    if scale_x and scale_y:
        print(f"  true size    : {width / scale_x:g} x {height / scale_y:g}")
    print(f"  colors      : {len(colors)}")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        measure(path)
