# ruff: noqa: E501
"""Build the C2 self-distillation prompt set v1 (deterministic, standard library only).

The prompts cover the same skills as ``chat_eval_v1`` with *new* items. Answer keys are
computed by the generator (arithmetic, dates, code output via the Python interpreter,
string operations, templated stories) or written by hand (facts, Swedish). Open-ended
prompts have no key. The teacher answers come later, from the model's own reasoning
mode (``oakgpt c2-distill``); keys are only used to filter those answers.

Contamination guard against the frozen evaluation set: every generated prompt is
rejected if its normalized text equals an evaluation prompt, if its content (the prompt
without the shared answer-format sentence) equals an evaluation item's content, if it
contains a term reserved by an evaluation item, or if it shares any 8-word sequence with
an evaluation prompt outside the shared format sentences. The guard statistics are
written to ``contamination.json``.

    python scripts/build_c2_prompts_v1.py data/finetune/c2_distill_v1
"""

import contextlib
import io
import json
import random
import re
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

VERSION = "c2_distill_v1"
EVAL = Path(__file__).resolve().parent.parent / "data" / "eval" / "chat_eval_v1" / "items.jsonl"
DEV_FRACTION = 0.1

# Terms tied to individual evaluation items. A prompt containing one is rejected, so no
# training item shares an evaluation item's specific subject.
RESERVED = [
    "Australia",
    "gold",
    "Jupiter",
    "Romeo",
    "Juliet",
    "boil",
    "Berlin",
    "Norge",
    "Norway",
    "apple",
    "äpple",
    "varm",
    "februari",
    "skottår",
    "Vänern",
    "kaffe",
    "coffee",
    "stone",
    "Mälardalen",
    "oak",
    "pear",
    "mango",
    "carrot",
    "Lina",
    "Moss",
    "Erik",
    "Pepper",
    "Anna",
    "oakgpt",
    "jacket",
]
# Sentences that only state the answer format; shared with the evaluation set on purpose.
FORMAT = re.compile(
    r"(Reply with only[^.?]*[.?]|Svara med endast[^.?]*[.?]|Read the text and answer the question\.|What does this Python code print\?)"
)

NAMES = [
    "Oskar",
    "Maja",
    "Leo",
    "Elsa",
    "Noah",
    "Saga",
    "Hugo",
    "Alva",
    "Liam",
    "Ella",
    "Nils",
    "Wilma",
    "Axel",
    "Freja",
    "Viktor",
    "Ebba",
    "Jonas",
    "Tilda",
    "Omar",
    "Sara",
]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def content(prompt: str) -> str:
    return norm(FORMAT.sub(" ", prompt))


Item = tuple[str, str, list[str]]  # (category, prompt, answers)


# ---------------------------------------------------------------- arithmetic


def arithmetic(rng: random.Random, n: int) -> list[Item]:
    out: list[Item] = []
    asks = [
        "What is {e}? Reply with only the number.",
        "Calculate {e}. Reply with only the number.",
    ]
    while len(out) < n:
        kind = rng.choice(["mul", "add", "sub", "div", "pct", "pow", "ops"])
        if kind == "mul":
            a, b = rng.randint(12, 99), rng.randint(11, 99)
            e, v = f"{a} * {b}", a * b
        elif kind == "add":
            a, b = rng.randint(100, 9999), rng.randint(100, 9999)
            e, v = f"{a} + {b}", a + b
        elif kind == "sub":
            a = rng.choice([100, 500, 1000, 2000, rng.randint(200, 9999)])
            b = rng.randint(11, a - 1)
            e, v = f"{a} - {b}", a - b
        elif kind == "div":
            b, q = rng.randint(3, 25), rng.randint(3, 40)
            e, v = f"{b * q} divided by {b}", q
        elif kind == "pct":
            p = rng.choice([5, 10, 20, 25, 30, 40, 50, 75])
            base = rng.choice([20, 40, 60, 120, 200, 240, 300, 400, 600, 1000])
            if p * base % 100:
                continue
            e, v = f"{p}% of {base}", p * base // 100
        elif kind == "pow":
            base = rng.randint(2, 9)
            exp = rng.randint(2, 4 if base > 4 else 8)
            e, v = f"{base} to the power of {exp}", base**exp
        else:
            a, b, c, d = (rng.randint(2, 12) for _ in range(4))
            form = rng.choice(
                [
                    "{a} * ({b} + {c}) - {d}",
                    "({a} + {b}) * {c}",
                    "{a} + {b} * {c}",
                    "{a} * {b} - {c} * {d}",
                    "({a} + {b}) * ({c} - {d})",
                ]
            )
            e = form.format(a=a, b=b, c=c, d=d)
            v = eval(e)  # our own arithmetic expression built above
        out.append(("arithmetic", rng.choice(asks).format(e=e), [str(v)]))
    return out


# ------------------------------------------------------------- word problems


def word_problems(rng: random.Random, n: int) -> list[Item]:
    out: list[Item] = []
    containers = [
        ("bags", "oranges"),
        ("crates", "bottles"),
        ("shelves", "books"),
        ("boxes", "pencils"),
        ("packs", "cards"),
        ("baskets", "eggs"),
    ]
    while len(out) < n:
        kind = rng.randrange(10)
        name = rng.choice(NAMES)
        if kind == 0:
            h, m, d = rng.randint(6, 20), rng.choice(range(0, 60, 5)), rng.choice(range(25, 200, 5))
            total = h * 60 + m + d
            if total >= 24 * 60:
                continue
            what = rng.choice(
                [
                    "A train leaves",
                    "A bus leaves",
                    "A film starts",
                    "A concert starts",
                    "A flight departs",
                ]
            )
            verb = "trip takes" if "leaves" in what or "departs" in what else "event lasts"
            end = "arrive" if verb == "trip takes" else "end"
            subject = "it"
            out.append(
                (
                    "word_problem",
                    f"{what} at {h:02d}:{m:02d} and the {verb.split()[0]} {verb.split()[1]} {d} minutes. At what time does {subject} {end}? Reply with only the time in HH:MM format.",
                    [f"{total // 60:02d}:{total % 60:02d}"],
                )
            )
        elif kind == 1:
            box, thing = rng.choice(containers)
            a, b = rng.randint(2, 9), rng.randint(4, 15)
            c = rng.randint(1, a * b - 1)
            out.append(
                (
                    "word_problem",
                    f"{name} has {a} {box} with {b} {thing} in each. {name} gives away {c} {thing}. How many {thing} does {name} have left? Reply with only the number.",
                    [str(a * b - c)],
                )
            )
        elif kind == 2:
            w, h = rng.randint(2, 20), rng.randint(2, 20)
            if rng.random() < 0.5:
                out.append(
                    (
                        "word_problem",
                        f"A rectangle is {w} m long and {h} m wide. What is its area in square metres? Reply with only the number.",
                        [str(w * h)],
                    )
                )
            else:
                out.append(
                    (
                        "word_problem",
                        f"A rectangle is {w} cm long and {h} cm wide. What is its perimeter in centimetres? Reply with only the number.",
                        [str(2 * (w + h))],
                    )
                )
        elif kind == 3:
            start, step = rng.randrange(7), rng.randint(2, 30)
            out.append(
                (
                    "word_problem",
                    f"Today is {DAYS[start]}. What day of the week will it be in {step} days? Reply with only the day.",
                    [DAYS[(start + step) % 7]],
                )
            )
        elif kind == 4:
            top = rng.randint(5, 50)
            out.append(
                (
                    "word_problem",
                    f"What is the sum of all whole numbers from 1 to {top}? Reply with only the number.",
                    [str(top * (top + 1) // 2)],
                )
            )
        elif kind == 5:
            price, p = rng.choice(range(100, 1000, 50)), rng.choice([10, 20, 25, 50])
            if price * p % 100:
                continue
            item = rng.choice(
                ["A lamp", "A bicycle helmet", "A pair of shoes", "A backpack", "A board game"]
            )
            out.append(
                (
                    "word_problem",
                    f"{item} costs {price} kronor. It is sold with a {p}% discount. What is the new price in kronor? Reply with only the number.",
                    [str(price - price * p // 100)],
                )
            )
        elif kind == 6:
            v, t = rng.choice(range(30, 130, 10)), rng.randint(2, 6)
            out.append(
                (
                    "word_problem",
                    f"A car drives at {v} km/h for {t} hours. How many kilometres does it travel? Reply with only the number.",
                    [str(v * t)],
                )
            )
        elif kind == 7:
            cost = rng.randint(12, 95)
            paid = rng.choice([100, 200, 500])
            if cost >= paid:
                continue
            out.append(
                (
                    "word_problem",
                    f"{name} buys a sandwich for {cost} kronor and pays with a {paid}-kronor note. How much change does {name} get? Reply with only the number.",
                    [str(paid - cost)],
                )
            )
        elif kind == 8:
            age, diff = rng.randint(6, 40), rng.randint(2, 30)
            other = rng.choice([x for x in NAMES if x != name])
            out.append(
                (
                    "word_problem",
                    f"{name} is {age} years old. {other} is {diff} years older than {name}. How old will {other} be in 3 years? Reply with only the number.",
                    [str(age + diff + 3)],
                )
            )
        else:
            people, each = rng.randint(3, 12), rng.randint(2, 9)
            out.append(
                (
                    "word_problem",
                    f"There are {people * each} sweets shared equally among {people} children. How many sweets does each child get? Reply with only the number.",
                    [str(each)],
                )
            )
    return out


# ------------------------------------------------------------------- facts

FACTS: list[tuple[str, list[str]]] = (
    [
        (f"What is the capital of {c}? Reply with only the city name.", a)
        for c, a in [
            ("France", ["Paris"]),
            ("Japan", ["Tokyo"]),
            ("Canada", ["Ottawa"]),
            ("Brazil", ["Brasília", "Brasilia"]),
            ("Egypt", ["Cairo"]),
            ("Kenya", ["Nairobi"]),
            ("Italy", ["Rome"]),
            ("Spain", ["Madrid"]),
            ("Finland", ["Helsinki"]),
            ("Denmark", ["Copenhagen"]),
            ("Iceland", ["Reykjavik", "Reykjavík"]),
            ("Poland", ["Warsaw"]),
            ("Portugal", ["Lisbon"]),
            ("Greece", ["Athens"]),
            ("Turkey", ["Ankara"]),
            ("India", ["New Delhi"]),
            ("China", ["Beijing"]),
            ("South Korea", ["Seoul"]),
            ("Argentina", ["Buenos Aires"]),
            ("Peru", ["Lima"]),
            ("New Zealand", ["Wellington"]),
            ("Ireland", ["Dublin"]),
            ("Austria", ["Vienna"]),
            ("Hungary", ["Budapest"]),
            ("the Czech Republic", ["Prague"]),
            ("Russia", ["Moscow"]),
            ("Thailand", ["Bangkok"]),
            ("Vietnam", ["Hanoi"]),
            ("Estonia", ["Tallinn"]),
            ("Latvia", ["Riga"]),
            ("Lithuania", ["Vilnius"]),
            ("Belgium", ["Brussels"]),
            ("Switzerland", ["Bern"]),
        ]
    ]
    + [
        (f"What is the chemical symbol for {e}? Reply with only the symbol.", [s])
        for e, s in [
            ("silver", "Ag"),
            ("iron", "Fe"),
            ("sodium", "Na"),
            ("potassium", "K"),
            ("oxygen", "O"),
            ("hydrogen", "H"),
            ("carbon", "C"),
            ("copper", "Cu"),
            ("lead", "Pb"),
            ("helium", "He"),
            ("nitrogen", "N"),
            ("calcium", "Ca"),
            ("tin", "Sn"),
            ("mercury", "Hg"),
        ]
    ]
    + [
        (
            "Which is the largest ocean on Earth? Reply with only its name.",
            ["Pacific", "Pacific Ocean", "the Pacific Ocean"],
        ),
        ("Which planet is closest to the Sun? Reply with only its name.", ["Mercury"]),
        ("Which planet is known as the Red Planet? Reply with only its name.", ["Mars"]),
        (
            "Who wrote the novel Pride and Prejudice? Reply with only the author's name.",
            ["Jane Austen", "Austen"],
        ),
        (
            "Who wrote the novel Nineteen Eighty-Four? Reply with only the author's name.",
            ["George Orwell", "Orwell"],
        ),
        (
            "Who painted the Mona Lisa? Reply with only the artist's name.",
            ["Leonardo da Vinci", "da Vinci", "Leonardo"],
        ),
        (
            "At sea level, at what temperature in degrees Celsius does water freeze? Reply with only the number.",
            ["0"],
        ),
        (
            "How many continents are there on Earth by the most common count? Reply with only the number.",
            ["7"],
        ),
        ("How many legs does a spider have? Reply with only the number.", ["8"]),
        ("How many legs does an insect have? Reply with only the number.", ["6"]),
        ("In which year did humans first land on the Moon? Reply with only the year.", ["1969"]),
        ("In which year did the Second World War end? Reply with only the year.", ["1945"]),
        (
            "What is the highest mountain on Earth above sea level? Reply with only its name.",
            ["Mount Everest", "Everest"],
        ),
        (
            "What is the largest animal on Earth? Reply with only its name.",
            ["blue whale", "the blue whale"],
        ),
        (
            "Which gas do plants absorb from the air for photosynthesis? Reply with only its name.",
            ["carbon dioxide", "CO2"],
        ),
        ("What is the currency of Japan? Reply with only its name.", ["yen", "Japanese yen"]),
        (
            "Which language is most widely spoken in Brazil? Reply with only its name.",
            ["Portuguese"],
        ),
        ("How many sides does a hexagon have? Reply with only the number.", ["6"]),
        (
            "Who developed the theory of relativity? Reply with only the scientist's name.",
            ["Albert Einstein", "Einstein"],
        ),
    ]
)


# ------------------------------------------------------------------ Swedish

SV_CAPITALS = [
    ("Finland", ["Helsingfors", "Helsinki"]),
    ("Danmark", ["Köpenhamn"]),
    ("Island", ["Reykjavik", "Reykjavík"]),
    ("Frankrike", ["Paris"]),
    ("Spanien", ["Madrid"]),
    ("Italien", ["Rom"]),
    ("Polen", ["Warszawa"]),
    ("Estland", ["Tallinn"]),
    ("Japan", ["Tokyo"]),
    ("Grekland", ["Aten"]),
    ("Portugal", ["Lissabon"]),
    ("Ungern", ["Budapest"]),
    ("Österrike", ["Wien"]),
    ("Nederländerna", ["Amsterdam"]),
]
EN_SV = [
    ("dog", ["hund", "en hund"]),
    ("cat", ["katt", "en katt"]),
    ("house", ["hus", "ett hus"]),
    ("book", ["bok", "en bok"]),
    ("water", ["vatten"]),
    ("tree", ["träd", "ett träd"]),
    ("car", ["bil", "en bil"]),
    ("bread", ["bröd"]),
    ("milk", ["mjölk"]),
    ("sun", ["sol", "solen"]),
    ("moon", ["måne", "månen"]),
    ("star", ["stjärna", "en stjärna"]),
    ("horse", ["häst", "en häst"]),
    ("fish", ["fisk", "en fisk"]),
    ("bird", ["fågel", "en fågel"]),
    ("chair", ["stol", "en stol"]),
    ("table", ["bord", "ett bord"]),
    ("window", ["fönster", "ett fönster"]),
    ("door", ["dörr", "en dörr"]),
    ("school", ["skola", "en skola"]),
    ("friend", ["vän", "en vän", "kompis"]),
    ("flower", ["blomma", "en blomma"]),
    ("snow", ["snö"]),
    ("rain", ["regn"]),
    ("cheese", ["ost"]),
    ("egg", ["ägg", "ett ägg"]),
    ("red", ["röd"]),
    ("green", ["grön"]),
    ("blue", ["blå"]),
    ("yellow", ["gul"]),
    ("big", ["stor"]),
    ("small", ["liten"]),
    ("night", ["natt", "en natt"]),
    ("forest", ["skog", "en skog"]),
    ("island", ["ö", "en ö"]),
    ("summer", ["sommar"]),
    ("winter", ["vinter"]),
    ("mountain", ["berg", "ett berg"]),
    ("knife", ["kniv", "en kniv"]),
    ("bridge", ["bro", "en bro"]),
]
OPPOSITES = [
    ("stor", ["liten"]),
    ("lång", ["kort"]),
    ("ny", ["gammal"]),
    ("glad", ["ledsen"]),
    ("ljus", ["mörk"]),
    ("snabb", ["långsam"]),
    ("tung", ["lätt"]),
    ("öppen", ["stängd"]),
    ("rik", ["fattig"]),
    ("full", ["tom"]),
    ("ung", ["gammal"]),
    ("dag", ["natt"]),
    ("upp", ["ner", "ned"]),
    ("svart", ["vit"]),
    ("bred", ["smal"]),
]
SV_FACTS = [
    ("Hur många dagar har en vecka? Svara med endast siffran.", ["7"]),
    ("Hur många månader har ett år? Svara med endast siffran.", ["12"]),
    ("Hur många dagar har januari? Svara med endast siffran.", ["31"]),
    ("Hur många dagar har april? Svara med endast siffran.", ["30"]),
    ("Hur många timmar har ett dygn? Svara med endast siffran.", ["24"]),
    ("Vilken månad kommer efter mars? Svara med endast månadens namn.", ["april"]),
    ("Vilken månad kommer före december? Svara med endast månadens namn.", ["november"]),
    ("Vilken veckodag kommer efter måndag? Svara med endast dagens namn.", ["tisdag"]),
    ("Vilken veckodag kommer före söndag? Svara med endast dagens namn.", ["lördag"]),
    ("Vad heter Sveriges huvudstad? Svara med endast stadens namn.", ["Stockholm"]),
    ("Vad heter Sveriges största ö? Svara med endast namnet.", ["Gotland"]),
    ("Vad heter Sveriges högsta berg? Svara med endast namnet.", ["Kebnekaise"]),
    (
        "Vilken valuta används i Sverige? Svara med endast valutans namn.",
        ["krona", "kronor", "svenska kronor", "svensk krona"],
    ),
    ("Vilket hav ligger öster om Sverige? Svara med endast namnet.", ["Östersjön"]),
    ("Hur många sidor har en kvadrat? Svara med endast siffran.", ["4"]),
    ("Vad är 7 gånger 8? Svara med endast siffran.", ["56"]),
    ("Vad är 100 minus 45? Svara med endast siffran.", ["55"]),
    (
        "Vilken färg får man om man blandar blått och gult? Svara med endast ett ord.",
        ["grön", "grönt"],
    ),
]
SV_EN_SENTENCES = [
    ("Jag har en hund", ["I have a dog"]),
    ("Hon läser en bok", ["She is reading a book", "She reads a book"]),
    ("Vi bor i Stockholm", ["We live in Stockholm"]),
    ("Det regnar idag", ["It is raining today", "It's raining today", "It rains today"]),
    ("Han dricker te", ["He drinks tea", "He is drinking tea"]),
    ("Jag tycker om musik", ["I like music"]),
    ("Katten sover", ["The cat is sleeping", "The cat sleeps"]),
    ("Vi ses imorgon", ["See you tomorrow"]),
    ("Barnen leker ute", ["The children are playing outside", "The children play outside"]),
    ("Jag är hungrig", ["I am hungry", "I'm hungry"]),
]
EN_SV_SENTENCES = [
    ("I have a cat", ["Jag har en katt"]),
    ("The sun is shining", ["Solen skiner"]),
    ("We are going home", ["Vi går hem", "Vi åker hem"]),
    ("She has a red car", ["Hon har en röd bil"]),
    ("I am tired", ["Jag är trött"]),
    ("Thank you very much", ["Tack så mycket"]),
    ("Good morning", ["God morgon"]),
    ("The book is on the table", ["Boken ligger på bordet", "Boken är på bordet"]),
]


def swedish() -> list[Item]:
    out: list[Item] = [
        ("swedish", f"Vad är huvudstaden i {c}? Svara med endast stadens namn.", a)
        for c, a in SV_CAPITALS
    ]
    out += [
        ("swedish", f'Översätt det engelska ordet "{w}" till svenska. Svara med endast ordet.', a)
        for w, a in EN_SV
    ]
    out += [
        (
            "swedish",
            f'Översätt det svenska ordet "{a[0].split()[-1]}" till engelska. Svara med endast ordet.',
            [w],
        )
        for w, a in EN_SV[::2]
    ]
    out += [
        ("swedish", f'Vad är motsatsen till ordet "{w}"? Svara med endast ett ord.', a)
        for w, a in OPPOSITES
    ]
    out += [("swedish", q, a) for q, a in SV_FACTS]
    out += [
        ("swedish", f'Översätt meningen "{s}" till engelska. Svara med endast översättningen.', a)
        for s, a in SV_EN_SENTENCES
    ]
    out += [
        ("swedish", f'Översätt meningen "{s}" till svenska. Svara med endast översättningen.', a)
        for s, a in EN_SV_SENTENCES
    ]
    return out


# --------------------------------------------------------------------- code


def run_python(code: str) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(code, {"__builtins__": __builtins__})  # our own generated snippet
    return buffer.getvalue().strip()


WORDS = [
    "river",
    "planet",
    "window",
    "garden",
    "python",
    "keyboard",
    "lantern",
    "maple",
    "harbor",
    "cloud",
    "pixel",
    "tiger",
    "violin",
    "rocket",
    "island",
    "forest",
    "candle",
    "bridge",
    "silver",
    "meadow",
]


def code(rng: random.Random, n: int) -> list[Item]:
    out: list[Item] = []
    keywords = [
        (
            "Which Python keyword starts a loop over the items of a sequence? Reply with only the keyword.",
            ["for"],
        ),
        (
            "Which Python keyword sends a value back from a function? Reply with only the keyword.",
            ["return"],
        ),
        ("Which Python keyword loads a module? Reply with only the keyword.", ["import"]),
        ("Which Python keyword starts a class definition? Reply with only the keyword.", ["class"]),
        (
            "Which Python keyword starts a conditional statement? Reply with only the keyword.",
            ["if"],
        ),
        ("Which Python keyword exits a loop early? Reply with only the keyword.", ["break"]),
        (
            "Which built-in Python function returns the number of items in a list? Reply with only the function name.",
            ["len", "len()"],
        ),
        (
            "Which Python keyword starts a block that catches exceptions after try? Reply with only the keyword.",
            ["except"],
        ),
    ]
    out += [("code", q, a) for q, a in keywords]
    while len(out) < n:
        kind = rng.randrange(16)
        nums = [rng.randint(1, 20) for _ in range(rng.randint(3, 5))]
        word = rng.choice(WORDS)
        a, b = rng.randint(2, 30), rng.randint(2, 9)
        if kind == 0:
            snippet = f'print(len("{word}"))'
        elif kind == 1:
            snippet = f"print(sorted({nums})[{rng.choice([0, 1, -1, -2])}])"
        elif kind == 2:
            snippet = f"x = {nums}\nprint(sum(i * i for i in x))"
        elif kind == 3:
            snippet = f'print("{word[:2]}" * {b})'
        elif kind == 4:
            snippet = f"print({a} // {b}, {a} % {b})"
        elif kind == 5:
            snippet = f"def f(n):\n    return 1 if n < 2 else n * f(n - 1)\n\nprint(f({rng.randint(3, 7)}))"
        elif kind == 6:
            snippet = f"def g(n):\n    return 0 if n == 0 else n + g(n - 1)\n\nprint(g({rng.randint(3, 12)}))"
        elif kind == 7:
            snippet = f"print(max({nums}) - min({nums}))"
        elif kind == 8:
            snippet = f"print({nums}[::-1])"
        elif kind == 9:
            snippet = f'print("{word}".upper())'
        elif kind == 10:
            snippet = f"print(list(range({b}, {b + rng.randint(2, 5)})))"
        elif kind == 11:
            snippet = f"total = 0\nfor i in range({b + 2}):\n    total += i\nprint(total)"
        elif kind == 12:
            snippet = f'print("{word}"[{rng.randint(0, len(word) - 1)}])'
        elif kind == 13:
            start = rng.randint(0, 2)
            snippet = f'print("{word}"[{start}:{start + 3}])'
        elif kind == 14:
            snippet = f'd = {{"a": {a}, "b": {b}}}\nprint(d["b"] + d["a"])'
        else:
            snippet = f"print([n for n in {nums} if n % 2 == 0])"
        prompt = f"What does this Python code print? Reply with only the output.\n\n{snippet}"
        out.append(("code", prompt, [run_python(snippet)]))
    return out


# ------------------------------------------------------------- instructions

CATEGORY_WORDS = {
    "animal": ["lion", "zebra", "rabbit", "goat", "wolf", "eagle", "sheep", "otter"],
    "fruit": ["banana", "cherry", "plum", "grape", "lemon", "peach", "kiwi", "melon"],
    "vehicle": ["bus", "truck", "bicycle", "train", "tram", "scooter", "boat", "plane"],
    "colour": ["purple", "green", "orange", "brown", "white", "black", "pink", "grey"],
    "tool": ["hammer", "saw", "wrench", "drill", "chisel", "shovel", "pliers", "rake"],
}
SENTENCES = [
    "The quick fox runs over the hill",
    "We will meet at the library after lunch",
    "Rain is expected later this week",
    "My brother plays the piano every evening",
    "The museum opens at nine",
    "Please close the door when you leave",
]


def instructions(rng: random.Random, n: int) -> list[Item]:
    out: list[Item] = []
    pool = sorted({w for words in CATEGORY_WORDS.values() for w in words} | set(WORDS))
    while len(out) < n:
        kind = rng.randrange(8)
        word = rng.choice(pool)
        if kind == 0:
            out.append(
                (
                    "instructions",
                    f'Write the word "{word}" backwards. Reply with only the result.',
                    [word[::-1]],
                )
            )
        elif kind == 1:
            words = rng.sample(pool, rng.randint(3, 4))
            out.append(
                (
                    "instructions",
                    f"Sort these words alphabetically: {', '.join(words)}. Reply with only the sorted words, separated by commas.",
                    [", ".join(sorted(words))],
                )
            )
        elif kind == 2:
            same, other = rng.sample(sorted(CATEGORY_WORDS), 2)
            group = rng.sample(CATEGORY_WORDS[same], 3) + [rng.choice(CATEGORY_WORDS[other])]
            odd = group[-1]
            rng.shuffle(group)
            out.append(
                (
                    "instructions",
                    f"Which word does not belong with the others: {', '.join(group)}? Reply with only the word.",
                    [odd],
                )
            )
        elif kind == 3:
            out.append(
                (
                    "instructions",
                    f'How many letters are in the word "{word}"? Reply with only the number.',
                    [str(len(word))],
                )
            )
        elif kind == 4:
            out.append(
                (
                    "instructions",
                    f'What is the first letter of the word "{word}"? Reply with only the letter.',
                    [word[0]],
                )
            )
        elif kind == 5:
            out.append(
                (
                    "instructions",
                    f'What is the last letter of the word "{word}"? Reply with only the letter.',
                    [word[-1]],
                )
            )
        elif kind == 6:
            out.append(
                (
                    "instructions",
                    f'Write the word "{word}" in capital letters. Reply with only the result.',
                    [word.upper()],
                )
            )
        else:
            sentence = rng.choice(SENTENCES)
            out.append(
                (
                    "instructions",
                    f'How many words are in the sentence "{sentence}"? Reply with only the number.',
                    [str(len(sentence.split()))],
                )
            )
    return out


# ------------------------------------------------------------------ reading

PETS = [
    ("rabbit", "Clover"),
    ("parrot", "Kiwi"),
    ("hamster", "Pip"),
    ("dog", "Bruno"),
    ("cat", "Smilla"),
    ("turtle", "Otto"),
    ("dog", "Ludde"),
    ("cat", "Nova"),
]
EVENTS = [
    "The football practice",
    "The book club",
    "The dentist appointment",
    "The science lesson",
    "The team meeting",
    "The choir rehearsal",
]


def reading(rng: random.Random, n: int) -> list[Item]:
    out: list[Item] = []
    head = "Read the text and answer the question.\n\nText: "
    while len(out) < n:
        if rng.random() < 0.5:
            a, b = rng.sample(NAMES, 2)
            (pa, na), (pb, nb) = rng.sample(PETS, 2)
            if pa == pb:
                continue
            age, diff = rng.randint(1, 9), rng.randint(1, 4)
            text = f"{a} has a {pa} called {na}. {a}'s friend {b} has a {pb} called {nb}. {nb} is {diff} years older than {na}. {na} is {age} years old."
            q = rng.choice(
                [
                    (f"What is the name of {b}'s {pb}? Reply with only the name.", [nb]),
                    (f"How old is {nb}? Reply with only the number.", [str(age + diff)]),
                    (f"Who owns the {pa}? Reply with only the name.", [a]),
                    (f"What kind of animal is {nb}? Reply with only the animal.", [pb, f"a {pb}"]),
                ]
            )
        else:
            event = rng.choice(EVENTS)
            d1, d2 = rng.sample(DAYS[:5], 2)
            h, m = rng.randint(8, 16), rng.choice([0, 15, 30, 45])
            length = rng.choice([30, 45, 60, 75, 90, 105, 120])
            end = h * 60 + m + length
            reason = rng.choice(
                [
                    "the teacher was ill",
                    "the hall was closed",
                    "it clashed with a holiday",
                    "the room was double-booked",
                ]
            )
            text = f"{event} was moved from {d1} to {d2} because {reason}. It starts at {h:02d}:{m:02d} and ends at {end // 60:02d}:{end % 60:02d}."
            q = rng.choice(
                [
                    ("On which day is it now? Reply with only the day.", [d2]),
                    ("How many minutes does it last? Reply with only the number.", [str(length)]),
                    ("On which day was it originally planned? Reply with only the day.", [d1]),
                    (
                        "At what time does it end? Reply with only the time in HH:MM format.",
                        [f"{end // 60:02d}:{end % 60:02d}"],
                    ),
                ]
            )
        out.append(("reading", f"{head}{text}\n\nQuestion: {q[0]}", q[1]))
    return out


# --------------------------------------------------------------- open-ended

TOPICS = [
    "photosynthesis",
    "how a rainbow forms",
    "what a CPU does",
    "why the sky is blue",
    "how vaccines work",
    "what an API is",
    "how compound interest works",
    "what recursion means in programming",
    "why leaves change colour in autumn",
    "how a bicycle stays upright",
    "what a spreadsheet is useful for",
    "how tides work",
    "what machine learning is",
    "why sleep matters",
    "how a refrigerator keeps food cold",
    "what version control is",
    "how bees make honey",
    "what inflation means",
    "how a compass works",
    "what a password manager does",
]
TASKS = [
    "studying for an exam",
    "keeping a houseplant alive",
    "running a first 5 km race",
    "saving money on groceries",
    "writing a clear email",
    "learning a new language",
    "staying focused while working from home",
    "packing for a weekend trip",
    "cooking rice",
    "giving a short presentation",
]
MESSAGES = [
    ("a colleague", "a meeting that moved to tomorrow"),
    ("a neighbour", "borrowing a ladder"),
    ("a friend", "thanks for a birthday gift"),
    ("a teacher", "being absent on Friday"),
    ("a landlord", "a dripping tap"),
]
SV_TOPICS = [
    "allemansrätten",
    "midsommar",
    "en vulkan",
    "demokrati",
    "fotosyntes",
    "ett operativsystem",
    "klimatförändringar",
    "en budget",
]


def open_ended(rng: random.Random) -> list[Item]:
    out: list[Item] = []
    for topic in TOPICS:
        out.append(("open", f"Explain {topic} in two or three sentences.", []))
        out.append(("open", f"Explain {topic} to a ten-year-old.", []))
    for task in TASKS:
        out.append(("open", f"Give three short tips for {task}.", []))
    for who, what in MESSAGES:
        out.append(("open", f"Write a short, friendly message to {who} about {what}.", []))
    for topic in SV_TOPICS:
        out.append(("open", f"Förklara kort vad {topic} är.", []))
        out.append(("open", f"Ge tre korta fakta om {topic}.", []))
    for sentence in SENTENCES:
        out.append(("open", f'Rewrite this sentence to sound more formal: "{sentence}."', []))
    rng.shuffle(out)
    return out


# --------------------------------------------------------------------- build


def build(out_dir: Path) -> dict[str, object]:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty {out_dir}")
    eval_items = [
        json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    eval_prompts = [item["prompt"] for item in eval_items if item["modality"] == "text"]
    eval_norm = {norm(p) for p in eval_prompts}
    eval_content = {content(p) for p in eval_prompts}
    eval_grams = set()
    for prompt in eval_prompts:
        words = content(prompt).split()
        eval_grams |= {tuple(words[i : i + 8]) for i in range(len(words) - 7)}
    reserved = [
        re.compile(r"(?<!\w)" + re.escape(term.casefold()) + r"\w*", re.IGNORECASE)
        for term in RESERVED
    ]

    rng = random.Random(VERSION)
    generators: list[Callable[[], list[Item]]] = [
        lambda: arithmetic(rng, 200),
        lambda: word_problems(rng, 200),
        lambda: [("facts", q, a) for q, a in FACTS],
        swedish,
        lambda: code(rng, 220),
        lambda: instructions(rng, 200),
        lambda: reading(rng, 200),
        lambda: open_ended(rng),
    ]
    rejected = {
        "duplicate": 0,
        "eval_prompt": 0,
        "eval_content": 0,
        "reserved_term": 0,
        "eval_8gram": 0,
    }
    examples: dict[str, list[str]] = {reason: [] for reason in rejected}
    kept: list[dict[str, object]] = []
    seen: set[str] = set()
    for generate in generators:
        for category, prompt, answers in generate():
            key = norm(prompt)
            words = content(prompt).split()
            reason = None
            if key in seen:
                reason = "duplicate"
            elif key in eval_norm:
                reason = "eval_prompt"
            elif content(prompt) in eval_content:
                reason = "eval_content"
            elif any(pattern.search(prompt) for pattern in reserved):
                reason = "reserved_term"
            elif any(tuple(words[i : i + 8]) in eval_grams for i in range(len(words) - 7)):
                reason = "eval_8gram"
            if reason is None:
                seen.add(key)
                kept.append({"category": category, "prompt": prompt, "answers": answers})
            else:
                rejected[reason] += 1
                if reason != "duplicate" and prompt not in examples[reason][:200]:
                    examples[reason].append(prompt)
    counters: dict[object, int] = {}
    split_rng = random.Random(VERSION + "-split")
    for item in kept:
        index = counters.get(item["category"], 0)
        counters[item["category"]] = index + 1
        item["id"] = f"{item['category']}-{index:04d}"
        item["split"] = "dev" if split_rng.random() < DEV_FRACTION else "train"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "prompts.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for item in kept:
            ordered = {k: item[k] for k in ("id", "category", "split", "prompt", "answers")}
            stream.write(json.dumps(ordered, ensure_ascii=False) + "\n")
    report = {
        "version": VERSION,
        "eval_set": str(EVAL.relative_to(EVAL.parents[3])).replace("\\", "/"),
        "reserved_terms": RESERVED,
        "rejected": rejected,
        "rejected_templates": {
            r: sorted({re.sub(r"\d+", "N", p)[:90] for p in e}) for r, e in examples.items() if e
        },
        "kept": len(kept),
        "by_category": {
            c: sum(1 for i in kept if i["category"] == c)
            for c in dict.fromkeys(i["category"] for i in kept)
        },
        "dev": sum(1 for i in kept if i["split"] == "dev"),
    }
    (out_dir / "contamination.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1])), indent=2, ensure_ascii=False))
