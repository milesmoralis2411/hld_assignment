"""Generate the Project Report PDF for submission.

Builds Project_Report.pdf with the five required sections:
  1. Architecture diagram / explanation
  2. Dataset source and loading instructions
  3. API documentation
  4. Design choices and trade-offs
  5. Performance report

Dependencies (report generation only; not needed to run the app):
    pip install reportlab matplotlib    # matplotlib only supplies the DejaVu fonts

Run:  python -m scripts.generate_report   ->  Project_Report.pdf
"""
from __future__ import annotations

import os
import sys

import matplotlib  # only used to locate the bundled DejaVu fonts
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Project_Report.pdf")
IMAGES = os.path.join(ROOT, "images")

# ---- colours ----
NAVY = colors.HexColor("#1a1f3a")
ACCENT = colors.HexColor("#6c7bff")
GREEN = colors.HexColor("#1f8f6a")
LIGHT = colors.HexColor("#eef0fb")
GREY = colors.HexColor("#666666")
BORDER = colors.HexColor("#cad0e8")


def register_fonts() -> None:
    fdir = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(fdir, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(fdir, "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Italic", os.path.join(fdir, "DejaVuSans-Oblique.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-BoldItalic", os.path.join(fdir, "DejaVuSans-BoldOblique.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                                  italic="DejaVu-Italic", boldItalic="DejaVu-BoldItalic")
    pdfmetrics.registerFont(TTFont("DejaVuMono", os.path.join(fdir, "DejaVuSansMono.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuMono-Bold", os.path.join(fdir, "DejaVuSansMono-Bold.ttf")))
    pdfmetrics.registerFontFamily("DejaVuMono", normal="DejaVuMono", bold="DejaVuMono-Bold",
                                  italic="DejaVuMono", boldItalic="DejaVuMono-Bold")


def styles() -> dict:
    s = getSampleStyleSheet()
    out = {}
    out["title"] = ParagraphStyle("title", parent=s["Title"], fontName="DejaVu-Bold",
                                  fontSize=26, leading=30, textColor=NAVY, alignment=TA_CENTER)
    out["subtitle"] = ParagraphStyle("subtitle", fontName="DejaVu", fontSize=13,
                                     leading=18, textColor=ACCENT, alignment=TA_CENTER)
    out["meta"] = ParagraphStyle("meta", fontName="DejaVu", fontSize=10.5,
                                 leading=16, textColor=GREY, alignment=TA_CENTER)
    out["h1"] = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=16, leading=20,
                               textColor=NAVY, spaceBefore=16, spaceAfter=8)
    out["h2"] = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=12, leading=16,
                               textColor=ACCENT, spaceBefore=10, spaceAfter=4)
    out["body"] = ParagraphStyle("body", fontName="DejaVu", fontSize=10, leading=15,
                                 textColor=colors.black, alignment=TA_LEFT, spaceAfter=6)
    out["bullet"] = ParagraphStyle("bullet", parent=out["body"], leftIndent=14,
                                   bulletIndent=2, spaceAfter=3)
    out["code"] = ParagraphStyle("code", fontName="DejaVuMono", fontSize=7.4,
                                 leading=9.2, textColor=colors.black)
    out["cell"] = ParagraphStyle("cell", fontName="DejaVu", fontSize=8.6, leading=11.5)
    out["cellh"] = ParagraphStyle("cellh", fontName="DejaVu-Bold", fontSize=8.8,
                                  leading=11.5, textColor=colors.white)
    out["caption"] = ParagraphStyle("caption", fontName="DejaVu-Italic", fontSize=8.5,
                                    leading=11, textColor=GREY, alignment=TA_CENTER, spaceBefore=3)
    out["codeblk"] = ParagraphStyle("codeblk", fontName="DejaVuMono", fontSize=8,
                                    leading=11, textColor=colors.black)
    return out


ST = None  # populated in main


def P(text, style="body"):
    return Paragraph(text, ST[style])


def bullets(items):
    return [Paragraph(f"• {t}", ST["bullet"]) for t in items]


def table(rows, widths, header=True):
    data = []
    for r, row in enumerate(rows):
        style = "cellh" if (header and r == 0) else "cell"
        data.append([Paragraph(str(c), ST[style]) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    ts = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        ts += [("BACKGROUND", (0, 0), (-1, 0), NAVY),
               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]
    t.setStyle(TableStyle(ts))
    return t


def code_block(text):
    """A monospace block with a light background panel."""
    para = Preformatted(text, ST["codeblk"])
    t = Table([[para]], colWidths=[17 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4fb")),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def image(name, max_w=15.5 * cm, caption=None):
    path = os.path.join(IMAGES, name)
    if not os.path.exists(path):
        return Paragraph(f"[missing image: {name}]", ST["caption"])
    iw, ih = ImageReader(path).getSize()
    w = max_w
    h = w * ih / iw
    flow = [Image(path, width=w, height=h)]
    if caption:
        flow.append(P(caption, "caption"))
    return flow


ARCH = r"""                            +------------------------------------------+
   Browser (frontend)       |                Backend (FastAPI)          |
 +--------------------+      |                                          |
 | search box         |      |   GET /suggest --> SuggestionService     |
 | suggestions(debounce)---->|         |                                |
 | trending section   |      |         v                                |
 | metrics panel      |      |   +--------------+  miss  +------------+  |
 | cache routing      |      |   | Distributed  |------->|   Trie     |  |
 +---------+----------+      |   |   Cache      |<-------|  index     |  |
           | POST /search    |   | (consistent  |  fill  +-----+------+  |
           v                 |   |   hashing)   |              | built  |
   {"message":"Searched"}    |   +--------------+              v from    |
           |                 |         ^                  +------------+  |
           |                 |         | invalidate       |  SQLite    |  |
           v                 |   +--------------+  flush   | primary    |  |
     TrendingTracker  <------+---| BatchWriter  |--------->|  store     |  |
     (decaying recency)      |   | (buffer+agg) |          +------------+  |
                             +------------------------------------------+"""


def build_story():
    story = []

    # ---------- title page ----------
    story.append(Spacer(1, 4 * cm))
    story.append(P("Search Typeahead System", "title"))
    story.append(Spacer(1, 0.3 * cm))
    story.append(P("Project Report", "subtitle"))
    story.append(Spacer(1, 1.2 * cm))
    story.append(P("SST-2028 &nbsp; HLD101 Assignment: Build a Search Typeahead System", "meta"))
    story.append(Spacer(1, 0.6 * cm))
    story.append(P("A backend-focused typeahead: Trie index, consistent-hashed distributed "
                   "cache, recency-aware trending, and batched writes.", "meta"))
    story.append(Spacer(1, 1.6 * cm))
    story.append(P("<b>Author:</b> Varun Mundada", "meta"))
    story.append(P('<b>Repository:</b> '
                   '<font color="#6c7bff">github.com/milesmoralis2411/hld_assignment</font>', "meta"))
    story.append(P("<b>Date:</b> June 2026", "meta"))
    story.append(PageBreak())

    # ---------- 1. Architecture ----------
    story.append(P("1. Architecture", "h1"))
    story.append(P(
        "The system is a search-as-you-type backend with a thin web UI. Suggestions are "
        "served from an in-memory <b>Trie</b> index fronted by a <b>distributed cache</b> "
        "(several logical LRU+TTL nodes addressed by a <b>consistent-hash ring</b>). Search "
        "submissions feed a <b>recency-aware trending</b> tracker immediately and are persisted "
        "in <b>batches</b> to a durable <b>SQLite</b> primary store, which is also the source "
        "the Trie is built from. This keeps reads fast and shields the database from per-search "
        "write pressure."))
    story.append(code_block(ARCH))
    story.append(P("Data-flow paths", "h2"))
    story.extend(bullets([
        "<b>Read</b> (GET /suggest): cache &rarr; on miss, the Trie returns a candidate pool "
        "&rarr; rank (by count, or by count+recency) &rarr; store the result back in the cache.",
        "<b>Write</b> (POST /search): record recency <b>immediately</b> (so trending reacts "
        "instantly) and <b>append the count update to a buffer</b>; return "
        '{"message": "Searched"}.',
        "<b>Flush</b> (background task): drain the buffer, <b>aggregate repeated queries</b>, "
        "persist in <b>one transaction</b>, refresh the Trie, and invalidate affected cache keys.",
    ]))
    story.append(P("Backend components (<font name='DejaVuMono'>app/</font>)", "h2"))
    story.append(table([
        ["Module", "Responsibility"],
        ["consistent_hash.py", "Hash ring with virtual nodes; routes a prefix key to a cache node."],
        ["cache.py", "One logical cache node: LRU + per-entry TTL + hit/miss stats."],
        ["cache_cluster.py", "N cache nodes behind the ring = the distributed cache."],
        ["trie.py", "Prefix index; precomputes top-N pools for shallow prefixes (bounded memory)."],
        ["store.py", "SQLite primary store; counts every DB read and write."],
        ["trending.py", "Exponentially time-decayed recency scores."],
        ["batch_writer.py", "Buffer + aggregate + periodic / size-based flush."],
        ["metrics.py", "Rolling latency window producing p50/p95/p99."],
        ["service.py", "Wires it together (read / write / flush / trending / metrics)."],
        ["main.py", "FastAPI routes + lifespan bootstrap + static frontend."],
    ], widths=[4.2 * cm, 12.8 * cm]))
    story.append(Spacer(1, 0.3 * cm))
    story.extend(image("typeahead.png", caption="The running UI: typeahead suggestions, live "
                       "metrics and consistent-hash cache routing."))
    story.append(PageBreak())

    # ---------- 2. Dataset ----------
    story.append(P("2. Dataset source and loading instructions", "h1"))
    story.append(P("Source (real, open)", "h2"))
    story.append(P(
        "The <b>Google Web Trillion Word Corpus</b> unigram counts &mdash; "
        "<font name='DejaVuMono'>count_1w.txt</font>, published by Peter Norvig "
        "(<font color='#6c7bff'>https://norvig.com/ngrams/</font>). It contains "
        "<b>333,333 real keywords with real corpus frequencies</b> and is free to use. "
        "“Keywords” is one of the entry types the assignment explicitly allows, and "
        "the counts are real frequencies (no aggregation needed)."))
    story.extend(bullets([
        "<b>Size:</b> all 333,333 rows by default (&#8811; the 100k minimum). Cap with "
        "<font name='DejaVuMono'>TYPEAHEAD_DATASET_LIMIT</font> or "
        "<font name='DejaVuMono'>--limit</font> (file is sorted by descending frequency).",
        "<b>Format:</b> raw file is <font name='DejaVuMono'>word&lt;TAB&gt;count</font>; the "
        "loader converts it to the assignment's <font name='DejaVuMono'>query,count</font> CSV "
        "at <font name='DejaVuMono'>data/queries.csv</font>.",
    ]))
    story.append(P("Loading instructions", "h2"))
    story.append(P("The dataset is fetched and loaded <b>automatically on first run</b> "
                   "(<font name='DejaVuMono'>python run.py</font>) &mdash; it just needs internet "
                   "access the first time. To do it explicitly:"))
    story.append(code_block(
        "python -m scripts.download_dataset            # -> data/queries.csv (all rows)\n"
        "python -m scripts.download_dataset --limit 150000   # top-150k by frequency"))
    story.append(P("On startup the CSV is bulk-loaded into SQLite (once), then the in-memory "
                   "Trie is built from the store (333,333 words / ~806,000 nodes, ready in "
                   "~10-15 s on first run, ~3-4 s thereafter)."))
    story.append(P("Using a different dataset / offline", "h2"))
    story.extend(bullets([
        "Drop any <font name='DejaVuMono'>query,count</font> CSV at "
        "<font name='DejaVuMono'>data/queries.csv</font> (e.g. an AOL query log or a Kaggle "
        "e-commerce search-terms set) and delete <font name='DejaVuMono'>data/typeahead.db</font> "
        "so it reloads. If the file has no counts, aggregate duplicates into counts first.",
        "If the download cannot reach the network on first run, the app falls back to a "
        "reproducible synthetic generator so it still runs (a message is printed).",
    ]))
    story.append(PageBreak())

    # ---------- 3. API documentation ----------
    story.append(P("3. API documentation", "h1"))
    story.append(P("Base URL <font name='DejaVuMono'>http://127.0.0.1:8000</font>. Interactive, "
                   "auto-generated docs are also served at "
                   "<font name='DejaVuMono'>/docs</font> (Swagger UI)."))
    story.append(table([
        ["Endpoint", "Purpose", "Notes"],
        ["GET /suggest?q=&lt;prefix&gt;&amp;ranking=count|recent",
         "Fetch up to 10 suggestions whose query starts with the prefix.",
         "ranking=count (default) = by overall count; ranking=recent = count + decaying recency."],
        ["POST /search &nbsp; {\"query\": \"...\"}",
         "Dummy search submission.",
         "Records recency now, buffers the count increment; returns {\"message\": \"Searched\"}."],
        ["GET /trending", "Currently trending queries.", "Recency-aware (time-decayed)."],
        ["GET /cache/debug?prefix=&lt;p&gt;",
         "Show consistent-hash routing for a key.",
         "Returns owning node, key hash, ring info and HIT/MISS."],
        ["GET /metrics", "Latency / cache / DB / batch metrics.", "p50/p95/p99, hit rate, write reduction."],
        ["POST /admin/flush", "Force a batch flush now.", "Handy in demos so writes show immediately."],
        ["GET /health", "Liveness check.", "{\"status\": \"ok\"}."],
    ], widths=[5.6 * cm, 5.0 * cm, 6.4 * cm]))
    story.append(P("Example responses", "h2"))
    story.append(P("<font name='DejaVuMono'>GET /suggest?q=iph</font>", "body"))
    story.append(code_block(
        '{\n'
        '  "prefix": "iph", "ranking": "count", "source": "store",\n'
        '  "suggestions": [\n'
        '    {"query": "iphoto", "count": 608838},\n'
        '    {"query": "iph", "count": 97233},\n'
        '    {"query": "iphigenia", "count": 55967},\n'
        '    {"query": "iphone", "count": 50988}\n'
        '  ]\n'
        '}'))
    story.append(P("<font name='DejaVuMono'>GET /cache/debug?prefix=iph</font>", "body"))
    story.append(code_block(
        '{\n'
        '  "key": "count:iph", "owner_node": "cache-3", "cache_status": "HIT",\n'
        '  "total_nodes": 4, "virtual_nodes_per_node": 150, "total_points_on_ring": 600\n'
        '}'))
    story.append(P("<font name='DejaVuMono'>GET /trending</font>", "body"))
    story.append(code_block(
        '{"trending": [{"query": "python", "recency_score": 12.5, "count": 17610578}]}'))
    story.append(PageBreak())

    # ---------- 4. Design choices ----------
    story.append(P("4. Design choices and trade-offs", "h1"))

    story.append(P("In-memory Trie with bounded precomputation", "h2"))
    story.append(P(
        "Suggestions need the top-K completions of a prefix. A Trie gives O(prefix length) "
        "traversal. The catch is broad prefixes (“a”, “ip”) that fan out to "
        "huge subtrees, so we <b>precompute a top-N candidate pool only for shallow nodes</b> "
        "(depth &le; 4); those expensive lookups become O(1), while deep prefixes (tiny "
        "subtrees) are computed on demand. This bounds memory instead of storing a list on all "
        "~806k nodes. <b>Trade-off:</b> a recency-surging query with a very low count may not be "
        "in a broad prefix's pool until its count rises &mdash; acceptable, because searching it "
        "also raises its count and it still appears in the trending section."))

    story.append(P("Distributed cache via consistent hashing", "h2"))
    story.append(P(
        "Each prefix-ranking key (e.g. <font name='DejaVuMono'>count:iph</font>) is routed by a "
        "consistent-hash ring to one of N logical cache nodes (LRU + TTL). It is modelled "
        "in-process so the whole system is one-command-runnable, but the behaviour is real: even "
        "key spread via 150 virtual nodes per node, per-shard stats, and only ~1/N keys remapped "
        "when a node is added/removed. <b>Trade-off:</b> TTL means suggestions can be briefly "
        "stale after a write; we additionally invalidate the changed query's short prefixes on "
        "flush to tighten this."))

    story.append(P("Recency without permanent bias", "h2"))
    story.append(P(
        "Trending uses an <b>exponentially decayed counter</b> per query "
        "(<font name='DejaVuMono'>score = score &times; 0.5^(&Delta;t / half_life) + 1</font>). "
        "It reacts instantly to bursts but the boost fades on its own, so a short-lived spike "
        "does not stay over-ranked. It is O(1) per update with no sliding-window buffers to "
        "sweep. The enhanced ranking blends it as "
        "<font name='DejaVuMono'>final = log1p(count) + recency_weight &times; recency</font> "
        "&mdash; log-compressing popularity so recency stays meaningful whether counts are in "
        "the tens or the billions (this dataset's counts reach ~2.3&times;10^10). "
        "<b>Trade-off:</b> <font name='DejaVuMono'>half_life</font> and "
        "<font name='DejaVuMono'>recency_weight</font> tune freshness vs. stability."))

    story.append(P("Batched writes", "h2"))
    story.append(P(
        "<font name='DejaVuMono'>POST /search</font> never writes to the DB synchronously &mdash; "
        "it buffers. A background flusher drains on size or interval and <b>aggregates repeated "
        "queries</b> (50&times; “iphone” &rarr; one +50 row-write), collapsing many "
        "writes into few. <b>Failure trade-off:</b> the buffer is in-memory, so a crash before a "
        "flush loses un-flushed submissions; mitigations (kept off to favour low write latency) "
        "would be a durable append-only log / persistent queue (Kafka, fsync'd WAL). On graceful "
        "shutdown the remaining buffer is flushed."))

    story.append(P("Why SQLite + FastAPI", "h2"))
    story.append(P(
        "Zero-setup (“easy to run locally”) yet a real transactional store and a real "
        "async HTTP framework with auto-generated API docs. The access pattern (bulk load, "
        "single-row upserts in a transaction on flush) maps cleanly onto any RDBMS, and the "
        "cache layer onto Redis, if scaled out. All tunables live in "
        "<font name='DejaVuMono'>app/config.py</font> (overridable via environment variables)."))
    story.append(PageBreak())

    # ---------- 5. Performance ----------
    story.append(P("5. Performance report", "h1"))
    story.append(P("Methodology", "h2"))
    story.append(P(
        "Driven over HTTP by <font name='DejaVuMono'>scripts/benchmark.py</font>: first 3,000 "
        "searches (to exercise batched writes), then 5,000 suggestion reads over a Zipf-biased "
        "prefix mix at concurrency 16. Default config: 4 cache nodes &times; 150 virtual nodes, "
        "TTL 30 s, batch size 200, flush interval 2 s, dataset = 333,333 real keywords "
        "(806k Trie nodes). Numbers below are a sample local run (Windows 11, Python 3.12) and "
        "vary by machine."))

    story.append(P("Suggestion read latency", "h2"))
    story.append(table([
        ["Metric", "Client-measured (incl. HTTP)", "Server-side (engine)"],
        ["p50", "32.90 ms", "0.036 ms"],
        ["p95", "37.43 ms", "0.057 ms"],
        ["p99", "41.67 ms", "0.111 ms"],
        ["avg", "33.02 ms", "0.036 ms"],
        ["max", "136.43 ms", "0.545 ms"],
    ], widths=[4 * cm, 6.5 * cm, 6.5 * cm]))
    story.append(P("Server-side latency excludes HTTP/loopback/threading overhead, so it is the "
                   "truest measure of the engine: <b>p95 &asymp; 0.06 ms</b> over a 333k-keyword "
                   "index. Client figures are dominated by the Python loopback round-trip under "
                   "16 threads, not the engine.", "body"))

    story.append(P("Distributed cache, database and write reduction", "h2"))
    story.append(table([
        ["Area", "Result"],
        ["Cache hit rate", "99.29% (5,464 hits / 39 misses across 4 nodes)"],
        ["Cache key spread", "cache-0: 1981 &middot; cache-1: 1483 &middot; cache-2: 1088 &middot; cache-3: 912"],
        ["DB reads / writes", "14 reads / 121 writes (despite 5,000 reads + 3,000 searches)"],
        ["Raw search submissions", "3,015"],
        ["DB row-writes performed", "121 (writes saved: 2,894)"],
        ["Write reduction (batching)", "<b>95.99%</b> over 13 flushes"],
    ], widths=[5.5 * cm, 11.5 * cm]))
    story.append(P("The cache + in-memory Trie absorb almost all read traffic (only 14 DB reads), "
                   "and batching collapses ~3,000 submissions into 121 row-writes &mdash; a "
                   "<b>96% reduction</b> in write pressure.", "body"))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(image("metrics.png", max_w=13.5 * cm,
                       caption="Live metrics panel from the running app (real dataset)."))

    story.append(P("Interpreting the trade-offs", "h2"))
    story.extend(bullets([
        "<b>Latency vs. freshness (cache TTL):</b> higher TTL &rarr; higher hit rate / lower "
        "latency but staler post-write reads (mitigated by prefix invalidation on flush).",
        "<b>Throughput vs. durability (batching):</b> bigger batches / longer intervals &rarr; "
        "fewer DB writes but a larger in-memory window lost on a crash.",
        "<b>Freshness vs. stability (recency):</b> shorter half-life / higher weight &rarr; "
        "trendier but jumpier ranking; decay prevents permanent over-ranking.",
        "<b>Memory vs. cold-prefix latency (Trie precompute depth):</b> deeper precomputation "
        "&rarr; faster broad-prefix lookups but more memory.",
    ]))

    return story


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("DejaVu", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(2 * cm, 1.1 * cm, "Search Typeahead System — Project Report")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {doc.page}")
    canvas.restoreState()


def main():
    global ST
    register_fonts()
    ST = styles()
    doc = SimpleDocTemplate(
        OUT, pagesize=A4, title="Search Typeahead System - Project Report",
        author="Varun Mundada", leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=1.8 * cm,
    )
    doc.build(build_story(), onFirstPage=lambda c, d: None, onLaterPages=footer)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
