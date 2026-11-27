# ruff: noqa: E501  (frozen prompt strings are kept on one line each)
"""Build the frozen chat evaluation set v1 (text and image items with answer keys).

Text items are hand-authored below. Image items are synthetic: every picture is drawn from
an explicit specification with the standard library only (zlib PNG encoder and a built-in
5x7 pixel font), so each answer key follows from how the image was constructed rather than
from anyone's reading of it. Output is byte-for-byte deterministic; a test rebuilds it and
compares against the committed files.

The set is evaluation-only. Never train on it, and never edit it after inspecting model
output: changes require a new version (chat_eval_v2).

    python scripts/build_chat_eval_v1.py data/eval/chat_eval_v1
"""

import hashlib
import json
import random
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

WIDTH, HEIGHT = 640, 480
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
COLORS = {
    "red": (220, 40, 40),
    "blue": (40, 90, 220),
    "green": (40, 160, 60),
    "yellow": (240, 200, 30),
    "orange": (245, 140, 20),
    "gray": (120, 120, 120),
}

# 5x7 glyphs, top row first.
FONT = {
    "A": ".###. #...# #...# ##### #...# #...# #...#",
    "B": "####. #...# #...# ####. #...# #...# ####.",
    "C": ".###. #...# #.... #.... #.... #...# .###.",
    "D": "####. #...# #...# #...# #...# #...# ####.",
    "E": "##### #.... #.... ####. #.... #.... #####",
    "F": "##### #.... #.... ####. #.... #.... #....",
    "G": ".###. #...# #.... #.### #...# #...# .####",
    "H": "#...# #...# #...# ##### #...# #...# #...#",
    "I": ".###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.",
    "J": "..### ...#. ...#. ...#. ...#. #..#. .##..",
    "K": "#...# #..#. #.#.. ##... #.#.. #..#. #...#",
    "L": "#.... #.... #.... #.... #.... #.... #####",
    "M": "#...# ##.## #.#.# #.#.# #...# #...# #...#",
    "N": "#...# #...# ##..# #.#.# #..## #...# #...#",
    "O": ".###. #...# #...# #...# #...# #...# .###.",
    "P": "####. #...# #...# ####. #.... #.... #....",
    "Q": ".###. #...# #...# #...# #.#.# #..#. .##.#",
    "R": "####. #...# #...# ####. #.#.. #..#. #...#",
    "S": ".#### #.... #.... .###. ....# ....# ####.",
    "T": "##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..",
    "U": "#...# #...# #...# #...# #...# #...# .###.",
    "V": "#...# #...# #...# #...# #...# .#.#. ..#..",
    "W": "#...# #...# #...# #.#.# #.#.# #.#.# .#.#.",
    "X": "#...# #...# .#.#. ..#.. .#.#. #...# #...#",
    "Y": "#...# #...# .#.#. ..#.. ..#.. ..#.. ..#..",
    "Z": "##### ....# ...#. ..#.. .#... #.... #####",
    "0": ".###. #...# #..## #.#.# ##..# #...# .###.",
    "1": "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
    "2": ".###. #...# ....# ...#. ..#.. .#... #####",
    "3": "####. ....# ....# .###. ....# ....# ####.",
    "4": "...#. ..##. .#.#. #..#. ##### ...#. ...#.",
    "5": "##### #.... ####. ....# ....# #...# .###.",
    "6": ".###. #.... #.... ####. #...# #...# .###.",
    "7": "##### ....# ...#. ..#.. .#... .#... .#...",
    "8": ".###. #...# #...# .###. #...# #...# .###.",
    "9": ".###. #...# #...# .#### ....# ....# .###.",
    " ": "..... ..... ..... ..... ..... ..... .....",
    "-": "..... ..... ..... ##### ..... ..... .....",
    ":": "..... .##.. .##.. ..... .##.. .##.. .....",
    ".": "..... ..... ..... ..... ..... .##.. .##..",
}


class Canvas:
    def __init__(self, width: int = WIDTH, height: int = HEIGHT) -> None:
        self.width, self.height = width, height
        self.pixels = bytearray(bytes(WHITE) * (width * height))

    def put(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            index = 3 * (y * self.width + x)
            self.pixels[index : index + 3] = bytes(color)

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        for y in range(max(0, y0), min(self.height, y1)):
            start = 3 * (y * self.width + max(0, x0))
            end = 3 * (y * self.width + min(self.width, x1))
            self.pixels[start:end] = bytes(color) * ((end - start) // 3)

    def circle(self, cx: int, cy: int, r: int, color: tuple[int, int, int]) -> None:
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.put(x, y, color)

    def triangle(self, cx: int, cy: int, r: int, color: tuple[int, int, int]) -> None:
        """Upward isosceles triangle inscribed in the box of half-size r."""
        for y in range(cy - r, cy + r + 1):
            half = (y - (cy - r)) / 2
            for x in range(int(cx - half), int(cx + half) + 1):
                self.put(x, y, color)

    def shape(self, kind: str, cx: int, cy: int, r: int, color: tuple[int, int, int]) -> None:
        if kind == "circle":
            self.circle(cx, cy, r, color)
        elif kind == "square":
            self.rect(cx - r, cy - r, cx + r + 1, cy + r + 1, color)
        elif kind == "triangle":
            self.triangle(cx, cy, r, color)
        else:
            raise ValueError(kind)

    def text(self, x: int, y: int, value: str, scale: int, color=BLACK) -> None:
        for offset, char in enumerate(value):
            rows = FONT[char].split()
            for row, bits in enumerate(rows):
                for column, bit in enumerate(bits):
                    if bit == "#":
                        left = x + (offset * 6 + column) * scale
                        top = y + row * scale
                        self.rect(left, top, left + scale, top + scale, color)

    def text_width(self, value: str, scale: int) -> int:
        return (len(value) * 6 - 1) * scale

    def centered_text(self, y: int, value: str, scale: int, color=BLACK) -> None:
        self.text((self.width - self.text_width(value, scale)) // 2, y, value, scale, color)

    def png(self) -> bytes:
        def chunk(kind: bytes, body: bytes) -> bytes:
            return (
                struct.pack(">I", len(body))
                + kind
                + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
            )

        stride = 3 * self.width
        raw = b"".join(
            b"\x00" + bytes(self.pixels[y * stride : (y + 1) * stride]) for y in range(self.height)
        )
        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )


def scatter(canvas: Canvas, shapes: list[tuple[str, str]], seed: int, r: int = 34) -> None:
    """Place shapes at random non-overlapping positions, reproducibly."""
    rng = random.Random(seed)
    placed: list[tuple[int, int]] = []
    for kind, color in shapes:
        for _ in range(10_000):
            x, y = rng.randint(r + 20, WIDTH - r - 20), rng.randint(r + 20, HEIGHT - r - 20)
            if all((x - px) ** 2 + (y - py) ** 2 > (2 * r + 30) ** 2 for px, py in placed):
                break
        else:
            raise RuntimeError("Could not place shapes")
        placed.append((x, y))
        canvas.shape(kind, x, y, r, COLORS[color])


def counting(shapes: list[tuple[str, str]], seed: int) -> Canvas:
    canvas = Canvas()
    scatter(canvas, shapes, seed)
    return canvas


def single(kind: str, color: str) -> Canvas:
    canvas = Canvas()
    canvas.shape(kind, WIDTH // 2, HEIGHT // 2, 110, COLORS[color])
    return canvas


def pair(first: tuple[str, str, int, int, int], second: tuple[str, str, int, int, int]) -> Canvas:
    canvas = Canvas()
    for kind, color, x, y, r in (first, second):
        canvas.shape(kind, x, y, r, COLORS[color])
    return canvas


def sign(lines: list[str], scale: int) -> Canvas:
    canvas = Canvas()
    height = len(lines) * 7 * scale + (len(lines) - 1) * 4 * scale
    top = (HEIGHT - height) // 2
    for index, line in enumerate(lines):
        canvas.centered_text(top + index * 11 * scale, line, scale)
    return canvas


def bars(values: dict[str, int]) -> Canvas:
    canvas = Canvas()
    base, width, gap = 420, 90, 50
    left = (WIDTH - len(values) * width - (len(values) - 1) * gap) // 2
    canvas.rect(left - 20, base, WIDTH - left + 20, base + 4, BLACK)
    for index, (label, value) in enumerate(values.items()):
        x = left + index * (width + gap)
        canvas.rect(x, base - value, x + width, base, COLORS["blue"])
        canvas.text(x + (width - canvas.text_width(label, 5)) // 2, base + 14, label, 5)
    return canvas


TEXT_ITEMS: list[dict[str, Any]] = [
    # Arithmetic.
    {"id": "math-mul", "category": "arithmetic", "prompt": "What is 47 * 23? Reply with only the number.", "answers": ["1081"]},
    {"id": "math-sub", "category": "arithmetic", "prompt": "What is 1000 - 387? Reply with only the number.", "answers": ["613"]},
    {"id": "math-div", "category": "arithmetic", "prompt": "What is 156 divided by 12? Reply with only the number.", "answers": ["13"]},
    {"id": "math-percent", "category": "arithmetic", "prompt": "What is 15% of 80? Reply with only the number.", "answers": ["12"]},
    {"id": "math-power", "category": "arithmetic", "prompt": "What is 2 to the power of 10? Reply with only the number.", "answers": ["1024"]},
    {"id": "math-order", "category": "arithmetic", "prompt": "What is 3 * (4 + 5) - 6? Reply with only the number.", "answers": ["21"]},
    # Word problems.
    {"id": "word-train", "category": "word_problem", "prompt": "A train leaves at 14:20 and the trip takes 95 minutes. At what time does it arrive? Reply with only the time in HH:MM format.", "answers": ["15:55"]},
    {"id": "word-apples", "category": "word_problem", "prompt": "Anna has 3 boxes with 12 apples in each box. She gives away 7 apples. How many apples does she have left? Reply with only the number.", "answers": ["29"]},
    {"id": "word-area", "category": "word_problem", "prompt": "A rectangle is 8 cm long and 5 cm wide. What is its area in square centimetres? Reply with only the number.", "answers": ["40"]},
    {"id": "word-weekday", "category": "word_problem", "prompt": "Today is Wednesday. What day of the week will it be in 10 days? Reply with only the day.", "answers": ["Saturday"]},
    {"id": "word-sum", "category": "word_problem", "prompt": "What is the sum of all whole numbers from 1 to 20? Reply with only the number.", "answers": ["210"]},
    {"id": "word-discount", "category": "word_problem", "prompt": "A jacket costs 250 kronor. It is sold with a 20% discount. What is the new price in kronor? Reply with only the number.", "answers": ["200"]},
    # Factual recall.
    {"id": "fact-australia", "category": "facts", "prompt": "What is the capital of Australia? Reply with only the city name.", "answers": ["Canberra"]},
    {"id": "fact-gold", "category": "facts", "prompt": "What is the chemical symbol for gold? Reply with only the symbol.", "answers": ["Au"]},
    {"id": "fact-planet", "category": "facts", "prompt": "Which is the largest planet in our solar system? Reply with only its name.", "answers": ["Jupiter"]},
    {"id": "fact-romeo", "category": "facts", "prompt": "Who wrote the play Romeo and Juliet? Reply with only the author's name.", "answers": ["William Shakespeare", "Shakespeare"]},
    {"id": "fact-boiling", "category": "facts", "prompt": "At sea level, at what temperature in degrees Celsius does water boil? Reply with only the number.", "answers": ["100"]},
    {"id": "fact-berlin", "category": "facts", "prompt": "In which year did the Berlin Wall fall? Reply with only the year.", "answers": ["1989"]},
    # Swedish.
    {"id": "sv-norway", "category": "swedish", "prompt": "Vad är huvudstaden i Norge? Svara med endast stadens namn.", "answers": ["Oslo"]},
    {"id": "sv-apple", "category": "swedish", "prompt": "Översätt det engelska ordet \"apple\" till svenska. Svara med endast ordet.", "answers": ["äpple", "ett äpple"]},
    {"id": "sv-opposite", "category": "swedish", "prompt": "Vad är motsatsen till ordet \"varm\"? Svara med endast ett ord.", "answers": ["kall"]},
    {"id": "sv-february", "category": "swedish", "prompt": "Hur många dagar har februari under ett skottår? Svara med endast siffran.", "answers": ["29"]},
    {"id": "sv-lake", "category": "swedish", "prompt": "Vad heter Sveriges största sjö? Svara med endast namnet.", "answers": ["Vänern"]},
    {"id": "sv-translate", "category": "swedish", "prompt": "Översätt meningen \"Jag gillar kaffe\" till engelska. Svara med endast översättningen.", "answers": ["I like coffee"]},
    # Reading Python code.
    {"id": "code-len", "category": "code", "prompt": "What does this Python code print? Reply with only the output.\n\nprint(len(\"oakgpt\"))", "answers": ["6"]},
    {"id": "code-sorted", "category": "code", "prompt": "What does this Python code print? Reply with only the output.\n\nprint(sorted([3, 1, 2])[-1])", "answers": ["3"]},
    {"id": "code-squares", "category": "code", "prompt": "What does this Python code print? Reply with only the output.\n\nx = [1, 2, 3]\nprint(sum(i * i for i in x))", "answers": ["14"]},
    {"id": "code-repeat", "category": "code", "prompt": "What does this Python code print? Reply with only the output.\n\nprint(\"ab\" * 3)", "answers": ["ababab"]},
    {"id": "code-divmod", "category": "code", "prompt": "What does this Python code print? Reply with only the output.\n\nprint(7 // 2, 7 % 2)", "answers": ["3 1"]},
    {"id": "code-factorial", "category": "code", "prompt": "What does this Python code print? Reply with only the output.\n\ndef f(n):\n    return 1 if n < 2 else n * f(n - 1)\n\nprint(f(5))", "answers": ["120"]},
    {"id": "code-keyword", "category": "code", "prompt": "Which Python keyword starts a function definition? Reply with only the keyword.", "answers": ["def"]},
    # Following explicit instructions about the form of the answer.
    {"id": "inst-reverse", "category": "instructions", "prompt": "Write the word \"stone\" backwards. Reply with only the result.", "answers": ["enots"]},
    {"id": "inst-sort", "category": "instructions", "prompt": "Sort these words alphabetically: pear, apple, mango. Reply with only the sorted words, separated by commas.", "answers": ["apple, mango, pear"]},
    {"id": "inst-odd", "category": "instructions", "prompt": "Which word does not belong with the others: dog, cat, carrot, horse? Reply with only the word.", "answers": ["carrot"]},
    {"id": "inst-letters", "category": "instructions", "prompt": "How many letters are in the word \"Mälardalen\"? Reply with only the number.", "answers": ["10"]},
    {"id": "inst-first", "category": "instructions", "prompt": "What is the first letter of the word \"oak\"? Reply with only the letter.", "answers": ["o"]},
    # Reading comprehension of a short passage given in the prompt.
    {"id": "read-pets", "category": "reading", "prompt": "Read the text and answer the question.\n\nText: Lina has a cat called Moss. Her brother Erik has a dog called Pepper. Pepper is two years older than Moss.\n\nQuestion: What is the name of Erik's dog? Reply with only the name.", "answers": ["Pepper"]},
    {"id": "read-pets-age", "category": "reading", "prompt": "Read the text and answer the question.\n\nText: Lina has a cat called Moss. Her brother Erik has a dog called Pepper. Pepper is two years older than Moss. Moss is three years old.\n\nQuestion: How old is Pepper? Reply with only the number.", "answers": ["5"]},
    {"id": "read-meeting", "category": "reading", "prompt": "Read the text and answer the question.\n\nText: The project meeting was moved from Monday to Thursday because the room was booked. It starts at 10:00 and ends at 11:30.\n\nQuestion: On which day is the meeting now? Reply with only the day.", "answers": ["Thursday"]},
    {"id": "read-meeting-length", "category": "reading", "prompt": "Read the text and answer the question.\n\nText: The project meeting was moved from Monday to Thursday because the room was booked. It starts at 10:00 and ends at 11:30.\n\nQuestion: How many minutes does the meeting last? Reply with only the number.", "answers": ["90"]},
]  # fmt: skip

LR = "Reply with only one word: left or right."
TB = "Reply with only one word: top or bottom."
NUMBER = "Reply with only the number."
WORD = "Reply with only one word."


def image_items() -> list[tuple[dict[str, Any], list[Canvas]]]:
    """Each entry pairs an item (without image hashes) with the canvases it shows."""
    count = "count"
    items: list[tuple[dict[str, Any], list[Canvas]]] = []

    def add(id_: str, category: str, prompt: str, answers: list[str], *canvases: Canvas) -> None:
        items.append(
            (
                {"id": id_, "category": category, "prompt": prompt, "answers": answers},
                list(canvases),
            )
        )

    add(
        "count-circles-3",
        count,
        f"How many circles are in the image? {NUMBER}",
        ["3", "three"],
        counting([("circle", "blue")] * 3, 11),
    )
    add(
        "count-circles-5",
        count,
        f"How many circles are in the image? {NUMBER}",
        ["5", "five"],
        counting([("circle", "red")] * 5, 12),
    )
    add(
        "count-squares-4",
        count,
        f"How many squares are in the image? {NUMBER}",
        ["4", "four"],
        counting([("square", "green")] * 4, 13),
    )
    add(
        "count-circles-7",
        count,
        f"How many circles are in the image? {NUMBER}",
        ["7", "seven"],
        counting([("circle", "orange")] * 7, 14),
    )
    add(
        "count-triangles-mixed",
        count,
        f"How many triangles are in the image? {NUMBER}",
        ["3", "three"],
        counting([("triangle", "blue")] * 3 + [("circle", "blue")] * 4, 15),
    )
    add(
        "color-square",
        "color",
        f"What color is the square? {WORD}",
        ["red"],
        single("square", "red"),
    )
    add(
        "color-circle",
        "color",
        f"What color is the circle? {WORD}",
        ["blue"],
        single("circle", "blue"),
    )
    add(
        "color-triangle",
        "color",
        f"What color is the triangle? {WORD}",
        ["green"],
        single("triangle", "green"),
    )
    add(
        "color-yellow",
        "color",
        f"What color is the circle? {WORD}",
        ["yellow"],
        single("circle", "yellow"),
    )
    add(
        "shape-circle",
        "shape",
        f"What shape is shown in the image? {WORD}",
        ["circle"],
        single("circle", "gray"),
    )
    add(
        "shape-triangle",
        "shape",
        f"What shape is shown in the image? {WORD}",
        ["triangle"],
        single("triangle", "gray"),
    )
    add(
        "shape-square",
        "shape",
        f"What shape is shown in the image? {WORD}",
        ["square"],
        single("square", "gray"),
    )
    add(
        "pos-left",
        "position",
        f"Is the red circle on the left or the right side of the image? {LR}",
        ["left"],
        pair(("circle", "red", 150, 240, 70), ("square", "blue", 490, 240, 70)),
    )
    add(
        "pos-right",
        "position",
        f"Is the red circle on the left or the right side of the image? {LR}",
        ["right"],
        pair(("square", "blue", 150, 240, 70), ("circle", "red", 490, 240, 70)),
    )
    add(
        "pos-top",
        "position",
        f"Is the green triangle at the top or the bottom of the image? {TB}",
        ["top"],
        pair(("triangle", "green", 320, 110, 70), ("circle", "orange", 320, 370, 70)),
    )
    add(
        "pos-bottom",
        "position",
        f"Is the green triangle at the top or the bottom of the image? {TB}",
        ["bottom"],
        pair(("circle", "orange", 320, 110, 70), ("triangle", "green", 320, 370, 70)),
    )
    add(
        "size-red",
        "size",
        f"Which circle is larger, the red one or the blue one? {WORD}",
        ["red"],
        pair(("circle", "red", 200, 240, 120), ("circle", "blue", 480, 240, 50)),
    )
    add(
        "size-orange",
        "size",
        f"Which square is larger, the green one or the orange one? {WORD}",
        ["orange"],
        pair(("square", "green", 180, 240, 45), ("square", "orange", 440, 240, 115)),
    )
    add(
        "chart-tallest",
        "chart",
        "The image is a bar chart with bars labelled A, B, C and D. Which bar is the tallest? Reply with only its letter.",
        ["C"],
        bars({"A": 120, "B": 200, "C": 310, "D": 160}),
    )
    add(
        "chart-shortest",
        "chart",
        "The image is a bar chart with bars labelled A, B, C and D. Which bar is the shortest? Reply with only its letter.",
        ["B"],
        bars({"A": 260, "B": 70, "C": 180, "D": 300}),
    )
    add(
        "ocr-sign",
        "ocr",
        "What does the sign say? Reply with only the text on the sign.",
        ["OPEN 24 HOURS"],
        sign(["OPEN 24 HOURS"], 7),
    )
    add(
        "ocr-code",
        "ocr",
        "What code is shown in the image? Reply with only the code.",
        ["K7Q-29X"],
        sign(["K7Q-29X"], 10),
    )
    add(
        "ocr-receipt",
        "ocr",
        f"The image shows a receipt. What is the total amount? {NUMBER}",
        ["60"],
        sign(["COFFEE 32", "BUN 28", "TOTAL 60"], 6),
    )
    add(
        "ocr-departure",
        "ocr",
        "At what time does the train depart? Reply with only the time in HH:MM format.",
        ["15:40"],
        sign(["PLATFORM 7", "DEPARTS 15:40"], 6),
    )
    add(
        "ocr-speed",
        "ocr",
        f"What speed limit is written in the image? {NUMBER}",
        ["50"],
        sign(["MAX SPEED 50"], 7),
    )
    add(
        "multi-more",
        "multi_image",
        "Which image contains more squares, the first or the second? Reply with only one word: first or second.",
        ["second"],
        counting([("square", "blue")] * 3, 21),
        counting([("square", "blue")] * 5, 22),
    )
    add(
        "multi-shape",
        "multi_image",
        f"What shape is shown in the second image? {WORD}",
        ["triangle"],
        single("circle", "red"),
        single("triangle", "blue"),
    )
    return items  # fmt: skip


def build(out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Refusing to overwrite {out}; frozen sets get a new version")
    images = out / "images"
    images.mkdir(parents=True)
    records = [{"modality": "text", "images": [], **item} for item in TEXT_ITEMS]
    for item, canvases in image_items():
        refs = []
        for index, canvas in enumerate(canvases):
            data = canvas.png()
            name = f"{item['id']}.png" if len(canvases) == 1 else f"{item['id']}-{index + 1}.png"
            (images / name).write_bytes(data)
            refs.append({"file": f"images/{name}", "sha256": hashlib.sha256(data).hexdigest()})
        records.append({"modality": "image", "images": refs, **item})
    ordered = [
        {key: record[key] for key in ("id", "modality", "category", "prompt", "images", "answers")}
        for record in records
    ]
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in ordered)
    (out / "items.jsonl").write_bytes(lines.encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(Path(sys.argv[1]))
