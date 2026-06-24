#!/usr/bin/env python3

import sys
import base45

if len(sys.argv) != 2 or sys.argv[1] not in ("enc", "dec"):
    print("Usage: b45tool.py enc|dec", file=sys.stderr)
    sys.exit(1)

data = sys.stdin.buffer.read()

if sys.argv[1] == "enc":
    sys.stdout.buffer.write(base45.b45encode(data))
else:
    sys.stdout.buffer.write(base45.b45decode(data))
