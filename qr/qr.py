#!/usr/bin/env python3
# Python 3.8+
# pip install "qrcode[pil]"

import argparse
import math
from pathlib import Path

import qrcode
from qrcode.constants import (
    ERROR_CORRECT_L,
    ERROR_CORRECT_M,
    ERROR_CORRECT_Q,
    ERROR_CORRECT_H,
)
from qrcode.exceptions import DataOverflowError


EC_LEVELS = {
    "L": ERROR_CORRECT_L,
    "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q,
    "H": ERROR_CORRECT_H,
}


def fits_qr(data_chunk, error_correction):
    qr = qrcode.QRCode(
        version=40,
        error_correction=error_correction,
        box_size=1,
        border=0,
    )

    try:
        qr.add_data(data_chunk)
        qr.make(fit=False)
        return True
    except DataOverflowError:
        return False


def find_chunk_size(data, error_correction):
    if not data:
        return 1

    lo = 1
    hi = min(len(data), 5000)
    best = 1

    while lo <= hi:
        mid = (lo + hi) // 2

        if fits_qr(data[:mid], error_correction):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    # небольшой запас, чтобы следующие куски тоже точно поместились
    return max(1, int(best * 0.95))


def save_qr(data_chunk, output_path, error_correction, box_size, border):
    qr = qrcode.QRCode(
        version=40,
        error_correction=error_correction,
        box_size=box_size,
        border=border,
    )

    qr.add_data(data_chunk)
    qr.make(fit=False)

    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Создает один или несколько QR-кодов из содержимого файла."
    )

    parser.add_argument("file", help="Файл, содержимое которого нужно поместить в QR")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="qr_output",
        help="Каталог для PNG-файлов",
    )
    parser.add_argument(
        "-e",
        "--error-correction",
        choices=EC_LEVELS.keys(),
        default="L",
        help="Коррекция ошибок QR: L, M, Q, H. L помещает больше данных.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="Размер части вручную. Если 0, вычисляется автоматически.",
    )
    parser.add_argument("--box-size", type=int, default=10)
    parser.add_argument("--border", type=int, default=4)

    args = parser.parse_args()

    input_path = Path(args.file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = input_path.read_bytes()
    ec = EC_LEVELS[args.error_correction]

    if args.chunk_size > 0:
        chunk_size = args.chunk_size
    else:
        chunk_size = find_chunk_size(data, ec)

    total = max(1, math.ceil(len(data) / chunk_size))

    print("Файл:", input_path)
    print("Размер:", len(data), "bytes")
    print("QR-кодов:", total)
    print("Размер части:", chunk_size, "bytes")

    for index in range(total):
        start = index * chunk_size
        end = start + chunk_size
        chunk = data[start:end]

        output_path = output_dir / (
            f"{input_path.stem}_part_{index + 1:05d}_of_{total:05d}.png"
        )

        save_qr(
            chunk,
            output_path,
            ec,
            args.box_size,
            args.border,
        )

        print("Создан:", output_path)


if __name__ == "__main__":
    main()
    