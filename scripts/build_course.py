#!/usr/bin/env python3
"""Build the Course: System Design repository from source content.

Sources (all under ROOT):
  - book-chapters/NNN-*.md           (206 concept articles)
  - system-design-interview/NN-*.md  (design-problem walkthroughs)
  - system-design-additional/solutions/{system_design,object_oriented_design}/*/

Produces the same shape as course-ai-engineering:
  phases/NN-slug/NN-lesson-slug/{docs/en.md, code/, outputs/}
  phases/NN-slug/README.md
  ROADMAP.md, README.md
"""
import os, re, glob, shutil, pathlib

ROOT = "/Users/ritesh/Downloads/submission_folder/course-system-design"
BOOK = os.path.join(ROOT, "book-chapters")
IV   = os.path.join(ROOT, "system-design-interview")
SOL  = os.path.join(ROOT, "system-design-additional", "solutions")
PHASES_DIR = os.path.join(ROOT, "phases")

GITHUB = "https://github.com/ambicuity/course-system-design"

# ── source resolution helpers ────────────────────────────────────────
_book_index = {}
for p in glob.glob(os.path.join(BOOK, "*.md")):
    n = int(os.path.basename(p)[:3])
    _book_index[n] = p

_iv_index = {}
for p in glob.glob(os.path.join(IV, "*.md")):
    m = re.match(r"(\d+)-", os.path.basename(p))
    if m:
        _iv_index[int(m.group(1))] = p

def first_h1(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
    return os.path.splitext(os.path.basename(path))[0]

def en_from_notebook(nb_path, title):
    import json
    nb = json.load(open(nb_path, encoding="utf-8"))
    parts, code_seen = [], False
    for c in nb.get("cells", []):
        src = "".join(c.get("source", [])).strip()
        if not src:
            continue
        if c["cell_type"] == "markdown":
            if "This notebook was prepared by" in src:
                continue
            parts.append(src)
        elif c["cell_type"] == "code" and not code_seen:
            body = re.sub(r"^%%writefile.*\n", "", src).strip()
            parts.append("## Implementation\n\n```python\n" + body + "\n```")
            code_seen = True
    text = "\n\n".join(parts)
    if not text.lstrip().startswith("# "):
        text = f"# {title}\n\n" + text
    text += ("\n\n---\n\n_Object-oriented design kata. Full runnable code is in this lesson's "
             "`code/` folder. Source: the System Design Primer._\n")
    return text

def slugify(text):
    text = text.lower()
    text = text.replace("&", " and ").replace("+", " plus ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")

def book_slug(n):
    base = os.path.basename(_book_index[n])           # NNN-slug.md
    return re.sub(r"^\d+-", "", base[:-3])

def iv_slug(n):
    base = os.path.basename(_iv_index[n])             # NN-slug.md
    return re.sub(r"^\d+-", "", base[:-3])

# ── taxonomy ─────────────────────────────────────────────────────────
# Each lesson: (kind, ref, type_override)  kind in {book, iv, sol}
def B(n, t=None): return ("book", n, t)
def I(n, t=None): return ("iv", n, t)
def S(path, t=None): return ("sol", path, t)

PHASES = [
    dict(slug="foundations", name="System Design Foundations",
         desc="The mindset, vocabulary, and back-of-the-envelope math behind every design.",
         lessons=[
            I(4, "Learn"), I(3, "Learn"),
            B(61), B(110), B(73), B(25), B(1), B(165), B(200), B(111), B(28), B(16),
         ]),
    dict(slug="networking-and-the-web", name="Networking & The Web",
         desc="From a keystroke to a packet — DNS, IP, ports, and the wires underneath.",
         lessons=[B(5), B(113), B(197), B(35), B(154), B(170), B(204), B(205), B(53),
                  B(20), B(169), B(173), B(174), B(203), B(190), B(189), B(202), B(188)]),
    dict(slug="http-rest-and-web-protocols", name="HTTP & Web Protocols",
         desc="The protocols the web runs on, and how they stay fast and secure.",
         lessons=[B(34), B(199), B(196), B(117), B(183), B(80), B(114), B(198), B(201)]),
    dict(slug="api-design-and-communication", name="API Design & Communication",
         desc="REST, GraphQL, gRPC, gateways, proxies — how services talk.",
         lessons=[B(11), B(191), B(63), B(76), B(122), B(175), B(104), B(2), B(30),
                  B(166), B(157), B(52), B(32), B(143), B(184)]),
    dict(slug="databases-and-storage", name="Databases & Storage",
         desc="SQL, NoSQL, indexes, normal forms, object stores, and query internals.",
         lessons=[B(112), B(194), B(27), B(100), B(36), B(37), B(67), B(69), B(92),
                  B(98), B(102), B(107), B(19), B(97), B(192), B(47), B(86), B(85), B(99)]),
    dict(slug="caching-and-performance", name="Caching & Performance",
         desc="Where to cache, how caches fail, and squeezing latency out of the stack.",
         lessons=[B(138), B(109), B(43), B(146), B(40), B(51), B(87)]),
    dict(slug="scalability-and-architecture", name="Scalability & System Architecture",
         desc="Scaling from zero to billions, and the architectures that got there.",
         lessons=[B(7), I(2, "Learn"), B(115), B(24), B(13), B(82), B(172), B(126),
                  B(39), B(10), B(44), B(90), B(83), B(182), B(48)]),
    dict(slug="messaging-and-event-streaming", name="Messaging & Event Streaming",
         desc="Queues, logs, and streams — Kafka, RabbitMQ, and the async backbone.",
         lessons=[B(29), B(142), B(152), B(94), B(195), B(162)]),
    dict(slug="software-architecture-and-patterns", name="Software Architecture & Design Patterns",
         desc="SOLID, clean architecture, DDD, monoliths, microservices, and patterns.",
         lessons=[B(55), B(62), B(140), B(116), B(66), B(118), B(123), B(163), B(206), B(134)]),
    dict(slug="security-and-authentication", name="Security & Authentication",
         desc="Sessions, tokens, SSO, OAuth, 2FA, and the attacks you must defend against.",
         lessons=[B(9), B(148), B(14), B(22), B(70), B(75), B(128), B(41), B(121),
                  B(46), B(149), B(4), B(187), B(105), B(158), B(160)]),
    dict(slug="containers-orchestration-and-cloud", name="Containers, Orchestration & Cloud",
         desc="Docker, Kubernetes, virtualization, and the major cloud platforms.",
         lessons=[B(3), B(161), B(119), B(135), B(26), B(136), B(96), B(81), B(78),
                  B(130), B(50), B(186), B(180), B(193), B(23), B(64), B(106), B(177),
                  B(68), B(181), B(176)]),
    dict(slug="devops-and-engineering-practice", name="DevOps & Engineering Practice",
         desc="CI/CD, deployment, infrastructure-as-code, Git, and versioning.",
         lessons=[B(131), B(141), B(84), B(72), B(6), B(129), B(18), B(49), B(145),
                  B(151), B(58), B(133), B(56)]),
    dict(slug="languages-concurrency-and-internals", name="Languages, Concurrency & Internals",
         desc="How runtimes work, threads vs processes, and concurrency vs parallelism.",
         lessons=[B(139), B(144), B(156), B(57), B(42), B(127), B(185), B(77)]),
    dict(slug="ai-and-llm-foundations", name="AI & LLM Foundations",
         desc="How modern AI systems are built — models, transformers, and training.",
         lessons=[B(91), B(155), B(88), B(33), B(103), B(60), B(54), B(12), B(120),
                  B(167), B(65), B(59), B(74), B(125), B(15), B(31), B(171), B(21),
                  B(147), B(150)]),
    dict(slug="ai-agents-rag-and-protocols", name="AI Agents, RAG & Protocols",
         desc="Retrieval, agents, tool-use, and the MCP/A2A protocols wiring them up.",
         lessons=[B(45), B(95), B(168), B(89), B(132), B(179), B(17), B(159), B(93),
                  B(164), B(124), B(178), B(137), B(38), B(71), B(153), B(79), B(108),
                  B(8), B(101)]),
    dict(slug="design-problems-foundations", name="Design Problems: Foundations",
         desc="The building-block design questions every interview starts with.",
         lessons=[I(5), I(6), I(7), I(8), I(9), I(10)]),
    dict(slug="design-problems-social-and-communication", name="Design Problems: Social & Communication",
         desc="Feeds, chat, notifications, and autocomplete at scale.",
         lessons=[I(11), I(12), I(13), I(14)]),
    dict(slug="design-problems-media-and-storage", name="Design Problems: Media & Storage",
         desc="Video, files, email, and object storage systems.",
         lessons=[I(15), I(16), I(24), I(25)]),
    dict(slug="design-problems-geo-and-realtime", name="Design Problems: Geo & Real-Time",
         desc="Location, proximity, maps, and real-time leaderboards.",
         lessons=[I(17), I(18), I(19), I(26)]),
    dict(slug="design-problems-data-and-financial", name="Design Problems: Data-Intensive & Financial",
         desc="Queues, metrics, aggregation, reservations, payments, and exchanges.",
         lessons=[I(20), I(21), I(22), I(23), I(27), I(28), I(29)]),
    dict(slug="object-oriented-and-applied-design", name="Object-Oriented & Applied Design",
         desc="Hands-on OO design katas and end-to-end primer case studies.",
         lessons=[
            S("object_oriented_design/parking_lot"), S("object_oriented_design/call_center"),
            S("object_oriented_design/online_chat"), S("object_oriented_design/deck_of_cards"),
            S("object_oriented_design/lru_cache"), S("object_oriented_design/hash_table"),
            S("system_design/pastebin"), S("system_design/twitter"),
            S("system_design/web_crawler"), S("system_design/mint"),
            S("system_design/sales_rank"), S("system_design/social_graph"),
            S("system_design/scaling_aws"), S("system_design/query_cache"),
            I(30, "Learn"),
         ]),
]

# ── validate book coverage ───────────────────────────────────────────
assigned = []
for ph in PHASES:
    for kind, ref, _ in ph["lessons"]:
        if kind == "book":
            assigned.append(ref)
dups = sorted({n for n in assigned if assigned.count(n) > 1})
missing = sorted(set(_book_index) - set(assigned))
extra = sorted(set(assigned) - set(_book_index))
assert not dups, f"duplicate book chapters: {dups}"
assert not missing, f"unassigned book chapters: {missing}"
assert not extra, f"bad book refs: {extra}"
print(f"OK book coverage: {len(assigned)}/{len(_book_index)} chapters, no dups/gaps")

# ── resolve a lesson to (name, slug, type, lang, src_path|dir) ────────
def resolve(kind, ref, override):
    if kind == "book":
        path = _book_index[ref]
        return dict(name=first_h1(path), slug=book_slug(ref),
                    type=override or "Learn", lang="—", kind=kind, src=path)
    if kind == "iv":
        path = _iv_index[ref]
        return dict(name=first_h1(path), slug=iv_slug(ref),
                    type=override or "Build", lang="—", kind=kind, src=path)
    # solution dir
    d = os.path.join(SOL, ref)
    readme = os.path.join(d, "README.md")
    name = first_h1(readme) if os.path.exists(readme) else os.path.basename(ref).replace("_", " ").title()
    return dict(name=name, slug=slugify(os.path.basename(ref)),
                type=override or "Build", lang="Python", kind=kind, src=d)

# ── build phases ─────────────────────────────────────────────────────
if os.path.isdir(PHASES_DIR):
    shutil.rmtree(PHASES_DIR)

EST = {"Learn": "~30 min", "Build": "~90 min"}
built = []  # per-phase resolved data for README/ROADMAP

for pidx, ph in enumerate(PHASES):
    phase_folder = f"{pidx:02d}-{ph['slug']}"
    phase_path = os.path.join(PHASES_DIR, phase_folder)
    os.makedirs(phase_path, exist_ok=True)
    lessons_built = []
    for lidx, (kind, ref, override) in enumerate(ph["lessons"], start=1):
        L = resolve(kind, ref, override)
        lesson_folder = f"{lidx:02d}-{L['slug']}"
        lpath = os.path.join(phase_path, lesson_folder)
        docs = os.path.join(lpath, "docs")
        code = os.path.join(lpath, "code")
        outs = os.path.join(lpath, "outputs")
        os.makedirs(docs, exist_ok=True)
        os.makedirs(outs, exist_ok=True)

        if kind in ("book", "iv"):
            shutil.copyfile(L["src"], os.path.join(docs, "en.md"))
        else:
            # solution dir: README -> docs/en.md, code -> code/, images next to en.md
            readme = os.path.join(L["src"], "README.md")
            if os.path.exists(readme):
                shutil.copyfile(readme, os.path.join(docs, "en.md"))
            else:
                # code-only katas: build en.md from the notebook's markdown cells
                nb_files = [x for x in os.listdir(L["src"]) if x.endswith(".ipynb")]
                md = en_from_notebook(os.path.join(L["src"], nb_files[0]), L["name"]) if nb_files else f"# {L['name']}\n"
                with open(os.path.join(docs, "en.md"), "w", encoding="utf-8") as nf:
                    nf.write(md)
            for f in os.listdir(L["src"]):
                fp = os.path.join(L["src"], f)
                if not os.path.isfile(fp):
                    continue
                if f.endswith((".py", ".ipynb")):
                    os.makedirs(code, exist_ok=True)
                    shutil.copyfile(fp, os.path.join(code, f))
                elif f.endswith((".png", ".jpg", ".svg")):
                    shutil.copyfile(fp, os.path.join(docs, f))
        lessons_built.append(dict(idx=lidx, folder=lesson_folder, **L))

    # phase README
    with open(os.path.join(phase_path, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"# Phase {pidx}: {ph['name']}\n\n> {ph['desc']}\n\n")
        f.write("See [ROADMAP.md](../../ROADMAP.md) for the full lesson plan.\n\n")
        f.write("| # | Lesson | Type |\n|---|--------|------|\n")
        for L in lessons_built:
            f.write(f"| {L['idx']:02d} | [{L['name']}]({L['folder']}/) | {L['type']} |\n")

    built.append(dict(idx=pidx, folder=phase_folder, name=ph["name"],
                      slug=ph["slug"], desc=ph["desc"], lessons=lessons_built))

# ── ROADMAP.md ───────────────────────────────────────────────────────
def phase_hours(lessons):
    mins = sum(30 if L["type"] == "Learn" else 90 for L in lessons)
    return round(mins / 60)

total_lessons = sum(len(b["lessons"]) for b in built)
total_hours = sum(phase_hours(b["lessons"]) for b in built)

with open(os.path.join(ROOT, "ROADMAP.md"), "w", encoding="utf-8") as f:
    f.write("# Roadmap\n\n")
    f.write("Status tracker for every phase and lesson. The status glyphs in this file feed\n")
    f.write("the website (`site/build.js` parses them into `site/data.js`); do not change\n")
    f.write("their shape.\n\n")
    f.write(f"Total estimated time: ~{total_hours} hours, at your own pace.\n\n")
    f.write("**Legend:** ✅ Complete &nbsp;·&nbsp; 🚧 In Progress &nbsp;·&nbsp; ⬚ Planned\n\n")
    for b in built:
        f.write(f"## Phase {b['idx']}: {b['name']} — ✅ (~{phase_hours(b['lessons'])} hours)\n\n")
        f.write("| # | Lesson | Status | Est. |\n|---|--------|--------|------|\n")
        for L in b["lessons"]:
            f.write(f"| {L['idx']:02d} | {L['name']} | ✅ | {EST[L['type']]} |\n")
        f.write("\n")

print(f"Wrote ROADMAP.md  ({len(built)} phases, {total_lessons} lessons, ~{total_hours}h)")

# ── README.md (root) ─────────────────────────────────────────────────
SEP = "░░░▒▒▒" * 14
def lesson_table(lessons, folder):
    rows = ["| # | Lesson | Type | Lang |", "|:---:|--------|:----:|------|"]
    for L in lessons:
        rows.append(f"| {L['idx']:02d} | [{L['name']}](phases/{folder}/{L['folder']}/) | {L['type']} | {L['lang']} |")
    return "\n".join(rows)

with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as f:
    f.write('<p align="center">\n')
    f.write('  <img src="assets/banner.svg" alt="Course: System Design — banner" width="100%">\n')
    f.write('</p>\n\n')
    f.write('<p align="center">\n')
    f.write('  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-1A2E2A?style=flat-square&labelColor=ECFFF7" alt="MIT License"></a>\n')
    f.write(f'  <a href="ROADMAP.md"><img src="https://img.shields.io/badge/lessons-{total_lessons}-2557E2?style=flat-square&labelColor=ECFFF7" alt="{total_lessons} lessons"></a>\n')
    f.write(f'  <a href="#contents"><img src="https://img.shields.io/badge/phases-{len(built)}-2557E2?style=flat-square&labelColor=ECFFF7" alt="{len(built)} phases"></a>\n')
    f.write('</p>\n\n')
    f.write('<p align="center"><sub>by <b>Ritesh Rana</b> &nbsp;·&nbsp; <a href="mailto:contact@riteshrana.engineer">contact@riteshrana.engineer</a></sub></p>\n\n')
    f.write("```\n" + SEP + "\n```\n\n")
    f.write(f"> **{total_lessons} lessons. {len(built)} phases. ~{total_hours} hours.** Every core system design\n")
    f.write("> concept, every classic interview problem, and the distributed-systems theory underneath —\n")
    f.write("> built up from first principles. Free, open source, MIT.\n>\n")
    f.write("> You don't just memorize architectures. You understand *why* each one is shaped the way it is.\n\n")
    f.write("## How this works\n\n")
    f.write("Most system design material is a pile of disconnected diagrams. A load-balancer post here, a\n")
    f.write("Kafka explainer there, a YouTube walkthrough somewhere else. The pieces rarely line up. You can\n")
    f.write("recite \"use a cache\" but can't say *which* cache, *where*, or what breaks when it goes stale.\n\n")
    f.write(f"This curriculum is the spine. {len(built)} phases, {total_lessons} lessons. Networking at one end, full\n")
    f.write("system-design interviews at the other. Every concept is grounded before the design problems that\n")
    f.write("depend on it. By the time you design YouTube or a payment system, you already know the caching,\n")
    f.write("sharding, queueing, and consistency tradeoffs underneath.\n\n")
    f.write("```\n" + SEP + "\n```\n\n")
    f.write("## The shape of a lesson\n\n")
    f.write("Each lesson lives in its own folder, with the same structure across the entire curriculum:\n\n")
    f.write("```\n")
    f.write("phases/<NN>-<phase-name>/<NN>-<lesson-name>/\n")
    f.write("├── code/      runnable implementations (where applicable)\n")
    f.write("├── docs/\n")
    f.write("│   └── en.md  lesson narrative\n")
    f.write("└── outputs/   reusable artifacts this lesson produces\n")
    f.write("```\n\n")
    f.write("```\n" + SEP + "\n```\n\n")
    f.write('<a id="contents"></a>\n\n## Contents\n\n')
    f.write(f"{len(built)} phases. Click any phase to expand its lesson list.\n\n")
    # Phase 0 open
    b0 = built[0]
    f.write(f'<a id="phase-0"></a>\n')
    f.write(f"### Phase 0: {b0['name']} `{len(b0['lessons'])} lessons`\n")
    f.write(f"> {b0['desc']}\n\n")
    f.write(lesson_table(b0["lessons"], b0["folder"]) + "\n\n")
    for b in built[1:]:
        f.write(f'<details id="phase-{b["idx"]}">\n')
        f.write(f"<summary><b>Phase {b['idx']} — {b['name']}</b> &nbsp;<code>{len(b['lessons'])} lessons</code>&nbsp; <em>{b['desc']}</em></summary>\n<br/>\n\n")
        f.write(lesson_table(b["lessons"], b["folder"]) + "\n\n")
        f.write("</details>\n\n")
    f.write("```\n" + SEP + "\n```\n\n")
    f.write("## License\n\nMIT — see [LICENSE](LICENSE). Built by Ritesh Rana.\n")

print(f"Wrote README.md")
print("DONE")
