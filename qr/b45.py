#!/usr/bin/env python3

import sys
import base45

if sys.argv[1] == "enc":
    sys.stdout.buffer.write(
        base45.b45encode(sys.stdin.buffer.read())
    )
elif sys.argv[1] == "dec":
    sys.stdout.buffer.write(
        base45.b45decode(sys.stdin.buffer.read())
    )
    