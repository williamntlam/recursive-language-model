"""Static HTML view of a trajectory directory. No JS required."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

REPORT_NAME = "report.html"


def resolve_run_dir(path: str | Path) -> Path:
    """Accept a run dir, events.jsonl, or a log parent (latest child)."""
    p = Path(path).resolve()
    if p.is_file() and p.name in {"events.jsonl", "trace.jsonl"}:
        return p.parent
    if p.is_dir() and (
        (p / "events.jsonl").is_file()
        or (p / "trace.jsonl").is_file()
        or (p / "meta.json").is_file()
    ):
        return p
    if p.is_dir():
        kids = sorted(
            (
                c
                for c in p.iterdir()
                if c.is_dir() and ((c / "events.jsonl").is_file() or (c / "trace.jsonl").is_file())
            ),
            key=lambda c: c.name,
            reverse=True,
        )
        if kids:
            return kids[0]
    raise FileNotFoundError(
        f"No RLM trajectory at {p}. Pass a run directory, events.jsonl, or a log parent."
    )


def load_run(run_dir: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    meta_path = run_dir / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            meta = {}
    usage: dict[str, Any] = {}
    usage_path = run_dir / "usage.json"
    if usage_path.is_file():
        loaded = json.loads(usage_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            usage = loaded
    answer = None
    answer_path = run_dir / "answer.txt"
    if answer_path.is_file():
        answer = answer_path.read_text(encoding="utf-8")
    events: list[dict[str, Any]] = []
    events_path = run_dir / "events.jsonl"
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                events.append(obj)
    trace: list[dict[str, Any]] = []
    trace_path = run_dir / "trace.jsonl"
    if trace_path.is_file():
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                if isinstance(obj, dict):
                    trace.append(obj)
    return {
        "dir": run_dir,
        "meta": meta,
        "usage": usage,
        "answer": answer,
        "events": events,
        "trace": trace,
        "complete": answer is not None,
    }


def write_report(run_dir: str | Path) -> Path:
    root = Path(run_dir)
    html = render_report(load_run(root))
    out = root / REPORT_NAME
    out.write_text(html, encoding="utf-8")
    return out


def render_report(run: dict[str, Any]) -> str:
    meta = run["meta"]
    usage = run["usage"]
    events: list[dict[str, Any]] = run["events"]
    run_id = escape(str(meta.get("id") or run["dir"].name))
    domain = escape(str(meta.get("domain") or "—"))
    status = "complete" if run["complete"] else "incomplete"
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    calls = _lm_calls(events)
    stats = _stats_row(usage, events, calls, run["complete"])
    calls_table = _calls_table(calls)
    parent_chart = _parent_token_chart(events)
    inst_note = _instruction_note(events)
    answer_html = _answer_block(run["answer"])
    timeline = "\n".join(_event_card(ev, i) for i, ev in enumerate(events))
    trace_overview = _trace_overview(run.get("trace", []))
    trace_tree = _trace_tree(run.get("trace", []), run["dir"], meta)
    if not events:
        timeline = '<p class="muted">No events recorded.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RLM trajectory — {run_id}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <header>
    <p class="kicker">Recursive Language Model</p>
    <h1>{run_id}</h1>
    <p class="sub">
      domain <strong>{domain}</strong>
      · {escape(str(meta.get("root_model") or "—"))} / {escape(str(meta.get("leaf_model") or "—"))}
      · <span class="status status-{status}">{status}</span>
    </p>
    {_meta_chips(meta)}
  </header>
  {stats}
  {calls_table}
  {parent_chart}
  {inst_note}
  {answer_html}
  {trace_overview}
  {trace_tree}
  <section>
    <h2>Timeline</h2>
    <p class="muted">Indent is recursion depth. Parent <code>hist</code>
      should stay small; bulky reads stay in REPL variables.</p>
    <div class="timeline">
      {timeline}
    </div>
  </section>
  <footer>
    Generated {escape(generated)} from <code>{escape(str(run["dir"]))}</code>.
    Offline static file — not a live UI.
  </footer>
</main>
</body>
</html>
"""


def _trace_overview(records: list[dict[str, Any]]) -> str:
    """Render the causal structure as a compact static SVG graph."""
    starts = [
        record
        for record in records
        if record.get("event") == "span_start" and not _legacy_fallback_tool_start(record, records)
    ]
    if not starts:
        return ""
    ends = {
        record.get("span_id"): record for record in records if record.get("event") == "span_end"
    }
    raw = {str(record["span_id"]): record for record in starts}
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for span_id, node in raw.items():
        if node.get("kind") != "tool":
            continue
        end = ends.get(span_id, {})
        key = (
            str(node.get("parent_span_id")),
            str(node.get("name")),
            str(end.get("status") or "unfinished"),
        )
        grouped.setdefault(key, []).append(span_id)

    visual_for: dict[str, str] = {}
    visual: dict[str, dict[str, Any]] = {}
    for key, span_ids in grouped.items():
        visual_id = "group:" + ":".join(key)
        first = raw[span_ids[0]]
        visual[visual_id] = {
            "parent": first.get("parent_span_id"),
            "label": f"{first.get('name')} ×{len(span_ids)}",
            "kind": "tool",
            "status": key[2],
        }
        for span_id in span_ids:
            visual_for[span_id] = visual_id
    for span_id, node in raw.items():
        if span_id in visual_for:
            continue
        end = ends.get(span_id, {})
        visual[span_id] = {
            "parent": node.get("parent_span_id"),
            "label": str(node.get("name") or node.get("kind") or "operation"),
            "kind": str(node.get("kind") or "operation"),
            "status": str(end.get("status") or "unfinished"),
        }
        visual_for[span_id] = span_id
    for node in visual.values():
        parent = node["parent"]
        node["parent"] = visual_for.get(str(parent)) if parent is not None else None

    children: dict[str, list[str]] = {node_id: [] for node_id in visual}
    roots: list[str] = []
    for node_id, node in visual.items():
        parent = node["parent"]
        if isinstance(parent, str) and parent in children and parent != node_id:
            children[parent].append(node_id)
        else:
            roots.append(node_id)
    for group in children.values():
        group.sort(key=lambda child: visual[child]["label"])
    roots.sort(key=lambda root: visual[root]["label"])

    positions: dict[str, tuple[int, float]] = {}
    next_row = 0

    def place(node_id: str, depth: int) -> float:
        nonlocal next_row
        kids = children[node_id]
        if not kids:
            y = float(next_row)
            next_row += 1
        else:
            y = sum(place(child, depth + 1) for child in kids) / len(kids)
        positions[node_id] = (depth, y)
        return y

    for root in roots:
        place(root, 0)
    width = max((depth for depth, _ in positions.values()), default=0) * 220 + 240
    height = max(120, next_row * 58 + 36)
    lines = []
    for node_id, node in visual.items():
        parent = node["parent"]
        if parent not in positions or node_id not in positions:
            continue
        parent_depth, parent_row = positions[parent]
        depth, row = positions[node_id]
        lines.append(
            f'<path class="graph-edge" d="M {parent_depth * 220 + 174} {parent_row * 58 + 32} '
            f"C {parent_depth * 220 + 194} {parent_row * 58 + 32}, "
            f'{depth * 220 + 4} {row * 58 + 32}, {depth * 220 + 4} {row * 58 + 32}"/>'
        )
    boxes = []
    for node_id, node in visual.items():
        depth, row = positions[node_id]
        x, y = depth * 220 + 4, row * 58 + 12
        label = _graph_label(node["label"])
        kind = _graph_class(node["kind"])
        status = _graph_class(node["status"])
        title = escape(f"{node['kind']} · {node['label']} · {node['status']}")
        boxes.append(
            f'<g class="graph-node graph-{kind} graph-{status}"><title>{title}</title>'
            f'<rect x="{x}" y="{y}" width="170" height="40" rx="5"/>'
            f'<text x="{x + 9}" y="{y + 17}" class="graph-kind">{escape(str(node["kind"]))}</text>'
            f'<text x="{x + 9}" y="{y + 32}" class="graph-label">{escape(label)}</text></g>'
        )
    return f"""
  <section>
    <h2>Call graph overview</h2>
    <p class="muted">Every branch is visible here. Repeated tool calls are grouped by parent,
      operation, and status; hover a node for its full label.</p>
    <div class="graph-scroll"><svg class="call-graph" viewBox="0 0 {width} {height}" role="img"
      aria-label="Causal execution call graph">{"".join(lines)}{"".join(boxes)}</svg></div>
  </section>
"""


def _graph_label(value: Any, limit: int = 24) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _graph_class(value: Any) -> str:
    return "".join(char if char.isalnum() else "-" for char in str(value).lower())


def _trace_tree(records: list[dict[str, Any]], run_dir: Path, meta: dict[str, Any]) -> str:
    """Render span IDs as an actual causal tree, never as a depth-only list."""
    starts = [
        r
        for r in records
        if r.get("event") == "span_start" and not _legacy_fallback_tool_start(r, records)
    ]
    if not starts:
        return ""
    ends = {r.get("span_id"): r for r in records if r.get("event") == "span_end"}
    nodes = {str(r["span_id"]): r for r in starts}
    children: dict[str, list[str]] = {span_id: [] for span_id in nodes}
    roots: list[str] = []
    for span_id, node in nodes.items():
        parent = node.get("parent_span_id")
        if isinstance(parent, str) and parent in children:
            children[parent].append(span_id)
        else:
            roots.append(span_id)
    for group in children.values():
        group.sort(key=lambda child: int(nodes[child].get("seq") or 0))
    roots.sort(key=lambda root: int(nodes[root].get("seq") or 0))
    content = _trace_children(roots, nodes, children, ends, run_dir, meta)
    return f"""
  <section>
    <h2>Trace call tree</h2>
    <p class="muted">Each branch is linked by <code>parent_span_id</code>.
      Expand a node for timing, token, cost, status, and captured artifacts.</p>
    <div class="trace-tree">{content}</div>
  </section>
"""


def _legacy_fallback_tool_start(record: dict[str, Any], records: list[dict[str, Any]]) -> bool:
    """Hide a short-lived reporter bug without hiding genuine interrupted tools.

    Earlier traces accidentally emitted a second tool start immediately before
    ending the real tool span. It has no end itself; the following end belongs
    to a sibling with the same name and parent. A genuinely interrupted tool
    does not have that exact adjacent sibling-end shape and remains visible.
    """
    if record.get("kind") != "tool" or record.get("event") != "span_start":
        return False
    try:
        index = records.index(record)
    except ValueError:
        return False
    if index + 1 >= len(records):
        return False
    next_record = records[index + 1]
    if next_record.get("event") != "span_end" or next_record.get("kind") != "tool":
        return False
    if next_record.get("span_id") == record.get("span_id"):
        return False
    real_start = next(
        (item for item in records if item.get("span_id") == next_record.get("span_id")), None
    )
    return bool(
        real_start
        and real_start.get("event") == "span_start"
        and real_start.get("name") == record.get("name")
        and real_start.get("parent_span_id") == record.get("parent_span_id")
    )


def _trace_node(
    span_id: str,
    nodes: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
    ends: dict[Any, dict[str, Any]],
    run_dir: Path,
    meta: dict[str, Any],
) -> str:
    node = nodes[span_id]
    end = ends.get(span_id, {})
    kind = str(node.get("kind") or "operation")
    name = str(node.get("name") or "unnamed")
    status = str(end.get("status") or "unfinished")
    model = node.get("model") or node.get("requested_model")
    metric_bits = [
        f"status {status}",
        f"{_fmt_int(_as_int(end.get('input_tokens') or node.get('input_tokens')))} in",
        f"{_fmt_int(_as_int(end.get('output_tokens')))} out",
    ]
    if end.get("duration_ms") is not None:
        metric_bits.append(f"{_fmt_int(_as_int(end.get('duration_ms')))} ms")
    if end.get("cost_usd") is not None:
        metric_bits.append(_fmt_cost(_as_float(end.get("cost_usd"))))
    child_html = _trace_children(children[span_id], nodes, children, ends, run_dir, meta)
    detail_rows = _trace_detail_rows(node, end)
    content = _trace_content(node, end, run_dir, meta)
    expanded = " open" if kind in {"run", "model", "repl", "callback", "batch"} else ""
    return f"""
<details class="trace-node trace-{escape(kind)}"{expanded}>
  <summary>
    <span class="trace-kind">{escape(kind)}</span>
    <strong>{escape(name)}</strong>
    {f'<span class="trace-model">{escape(str(model))}</span>' if model else ""}
    <span class="trace-metrics">{escape(" · ".join(metric_bits))}</span>
  </summary>
  <div class="trace-detail">
    <dl>{detail_rows}</dl>
    {content}
    {f'<div class="trace-children">{child_html}</div>' if child_html else ""}
  </div>
</details>
"""


def _trace_children(
    span_ids: list[str],
    nodes: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
    ends: dict[Any, dict[str, Any]],
    run_dir: Path,
    meta: dict[str, Any],
) -> str:
    """Group only adjacent, leaf tool spans; preserve all other causal nodes."""
    rendered: list[str] = []
    i = 0
    while i < len(span_ids):
        span_id = span_ids[i]
        key = _tool_group_key(span_id, nodes, children, ends)
        group = [span_id]
        if key is not None:
            while i + len(group) < len(span_ids):
                next_id = span_ids[i + len(group)]
                if _tool_group_key(next_id, nodes, children, ends) != key:
                    break
                group.append(next_id)
        if len(group) > 1:
            rendered.append(_trace_group(group, nodes, ends))
        else:
            rendered.append(_trace_node(span_id, nodes, children, ends, run_dir, meta))
        i += len(group)
    return "".join(rendered)


def _tool_group_key(
    span_id: str,
    nodes: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
    ends: dict[Any, dict[str, Any]],
) -> tuple[str, str, str] | None:
    node = nodes[span_id]
    if node.get("kind") != "tool" or children[span_id]:
        return None
    end = ends.get(span_id, {})
    return (str(node.get("kind")), str(node.get("name")), str(end.get("status") or "unfinished"))


def _trace_group(
    span_ids: list[str], nodes: dict[str, dict[str, Any]], ends: dict[Any, dict[str, Any]]
) -> str:
    first = nodes[span_ids[0]]
    end = ends.get(span_ids[0], {})
    name = escape(str(first.get("name") or "tool"))
    status = escape(str(end.get("status") or "unfinished"))
    duration = sum(int(ends.get(span_id, {}).get("duration_ms") or 0) for span_id in span_ids)
    return f"""
<details class="trace-node trace-group">
  <summary>
    <span class="trace-kind">tool</span><strong>{name}</strong>
    <span class="trace-metrics">status {status} · × {len(span_ids)} · {duration:,} ms total</span>
  </summary>
  <div class="trace-detail"><p class="muted trace-private">
    {len(span_ids)} adjacent calls were collapsed for readability.
    Individual spans remain in trace.jsonl.
  </p></div>
</details>
"""


def _trace_detail_rows(node: dict[str, Any], end: dict[str, Any]) -> str:
    fields = (
        ("span", str(node.get("span_id") or "")[:12]),
        ("parent", str(node.get("parent_span_id") or "—")[:12]),
        ("depth", node.get("depth")),
        ("model", node.get("model") or node.get("requested_model")),
        ("instruction count", node.get("instruction_count")),
        ("request chars", node.get("request_n_chars") or node.get("prompt_n_chars")),
        ("response chars", end.get("response_n_chars") or end.get("result_n_chars")),
        ("result count", end.get("result_count")),
        ("error", end.get("error_type")),
        ("request digest", node.get("request_digest") or node.get("prompt_digest")),
        ("response digest", end.get("response_digest") or end.get("result_digest")),
    )
    return "".join(
        f"<dt>{escape(label)}</dt><dd>{_e(value)}</dd>"
        for label, value in fields
        if value is not None and value != ""
    )


def _trace_content(
    node: dict[str, Any], end: dict[str, Any], run_dir: Path, meta: dict[str, Any]
) -> str:
    prompt = _read_artifact(run_dir, node.get("prompt_artifact") or end.get("prompt_artifact"))
    output = _read_artifact(run_dir, node.get("output_artifact") or end.get("output_artifact"))
    if prompt is not None or output is not None:
        parts = ['<div class="trace-content"><h3>Captured content</h3>']
        if prompt is not None:
            parts.append(
                f"<details><summary>Input / prompt</summary><pre>{escape(prompt)}</pre></details>"
            )
        if output is not None:
            parts.append(
                f"<details><summary>Output / response</summary>"
                f"<pre>{escape(output)}</pre></details>"
            )
        return "".join(parts) + "</div>"
    if meta.get("trace_capture") == "metadata":
        return (
            '<p class="muted trace-private">Input/output content was not retained '
            "(metadata capture).</p>"
        )
    return ""


def _read_artifact(run_dir: Path, ref: Any) -> str | None:
    if not isinstance(ref, str) or not ref.startswith("artifacts/"):
        return None
    path = (run_dir / ref).resolve()
    artifacts = (run_dir / "artifacts").resolve()
    try:
        path.relative_to(artifacts)
    except ValueError:
        return None
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        return None


LM_KINDS = frozenset({"root_lm", "llm_query"})


def _e(value: Any) -> str:
    if value is None:
        return "—"
    return escape(str(value))


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_int(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}"


def _fmt_cost(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:.4f}"


def _lm_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, ev in enumerate(events):
        if ev.get("kind") not in LM_KINDS:
            continue
        prompt = _as_int(ev.get("prompt_tokens"))
        completion = _as_int(ev.get("completion_tokens"))
        total = None
        if prompt is not None or completion is not None:
            total = (prompt or 0) + (completion or 0)
        rows.append(
            {
                "index": i,
                "kind": str(ev.get("kind")),
                "model": ev.get("model"),
                "depth": _as_int(ev.get("depth")) or 0,
                "iteration": ev.get("iteration"),
                "prompt": prompt,
                "completion": completion,
                "total": total,
                "cost": _as_float(ev.get("cost_usd")),
                "latency_s": _as_float(ev.get("latency_s")),
            }
        )
    return rows


def _meta_chips(meta: dict[str, Any]) -> str:
    chips = []
    mapping = [
        ("max_prompt_tokens", "max tokens"),
        ("max_instructions", "max inst"),
        ("max_depth", "max depth"),
        ("n_docs", "docs"),
        ("context_n_chars", "context chars"),
        ("repo", "repo"),
    ]
    for key, label in mapping:
        if key in meta and meta[key] is not None:
            chips.append(f'<span class="chip">{escape(label)} {_e(meta[key])}</span>')
    if not chips:
        return ""
    return '<p class="chips">' + "".join(chips) + "</p>"


def _stats_row(
    usage: dict[str, Any],
    events: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    complete: bool,
) -> str:
    prompt = _as_int(usage.get("prompt_tokens"))
    completion = _as_int(usage.get("completion_tokens"))
    cost = _as_float(usage.get("cost_usd"))
    if not usage:
        prompt = sum((c["prompt"] or 0) for c in calls)
        completion = sum((c["completion"] or 0) for c in calls)
        priced = [c["cost"] for c in calls if c["cost"] is not None]
        cost = sum(priced) if priced else None
    total = None
    if prompt is not None or completion is not None:
        total = (prompt or 0) + (completion or 0)
    iters = usage.get("iterations") if usage else None
    subcalls = usage.get("subcalls") if usage else None
    kinds: dict[str, int] = {}
    for e in events:
        k = str(e.get("kind") or "other")
        kinds[k] = kinds.get(k, 0) + 1
    kind_s = ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) or "—"
    note = ""
    if not complete:
        note = (
            '<p class="warn">Run did not finish. '
            "Answer and usage may be missing. Totals below are summed "
            "from recorded LM calls.</p>"
        )
    return f"""
  <section class="stats">
    {note}
    <div class="grid">
      <div>
        <div class="label">Prompt tokens</div>
        <div class="value">{_fmt_int(prompt)}</div>
      </div>
      <div>
        <div class="label">Completion tokens</div>
        <div class="value">{_fmt_int(completion)}</div>
      </div>
      <div>
        <div class="label">Total tokens</div>
        <div class="value">{_fmt_int(total)}</div>
      </div>
      <div>
        <div class="label">Cost (USD)</div>
        <div class="value">{_fmt_cost(cost)}</div>
      </div>
      <div>
        <div class="label">Iterations</div>
        <div class="value">{_fmt_int(_as_int(iters))}</div>
      </div>
      <div>
        <div class="label">Subcalls</div>
        <div class="value">{_fmt_int(_as_int(subcalls))}</div>
      </div>
    </div>
    <p class="muted kinds">{escape(kind_s)}. Cost is estimated from a
      local price table when OpenAI does not report dollars.</p>
  </section>
"""


def _calls_table(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return ""
    kind_label = {"root_lm": "root LM", "llm_query": "llm_query"}
    body: list[str] = []
    for row in calls:
        kind = kind_label.get(row["kind"], row["kind"])
        iter_s = "—" if row["iteration"] is None else str(row["iteration"])
        lat = row["latency_s"]
        lat_s = "—" if lat is None else f"{lat:.2f}s"
        body.append(
            "<tr>"
            f'<td class="left">#{row["index"]}</td>'
            f'<td class="left">{escape(kind)}</td>'
            f'<td class="left">{_e(row["model"])}</td>'
            f"<td>{row['depth']}</td>"
            f"<td>{escape(iter_s)}</td>"
            f"<td>{_fmt_int(row['prompt'])}</td>"
            f"<td>{_fmt_int(row['completion'])}</td>"
            f"<td>{_fmt_int(row['total'])}</td>"
            f"<td>{_fmt_cost(row['cost'])}</td>"
            f"<td>{escape(lat_s)}</td>"
            "</tr>"
        )
    sp = sum((c["prompt"] or 0) for c in calls)
    sc = sum((c["completion"] or 0) for c in calls)
    priced = [c["cost"] for c in calls if c["cost"] is not None]
    st = sp + sc
    cost_sum = sum(priced) if priced else None
    return f"""
  <section>
    <h2>LM calls</h2>
    <p class="muted">One row per OpenAI request (root turns and
      <code>llm_query</code> leaves). Nested <code>rlm_query</code>
      children appear as extra root LM rows at a higher depth.
      Prompt tokens here are the guarded input size for that send.</p>
    <div class="table-wrap">
    <table class="calls">
      <thead>
        <tr>
          <th class="left">#</th>
          <th class="left">Kind</th>
          <th class="left">Model</th>
          <th>Depth</th>
          <th>Iter</th>
          <th>Prompt</th>
          <th>Completion</th>
          <th>Total</th>
          <th>Cost</th>
          <th>Latency</th>
        </tr>
      </thead>
      <tbody>
        {"".join(body)}
      </tbody>
      <tfoot>
        <tr>
          <td class="left" colspan="5">Sum of {len(calls)} calls</td>
          <td>{_fmt_int(sp)}</td>
          <td>{_fmt_int(sc)}</td>
          <td>{_fmt_int(st)}</td>
          <td>{_fmt_cost(cost_sum)}</td>
          <td></td>
        </tr>
      </tfoot>
    </table>
    </div>
  </section>
"""


def _parent_token_chart(events: list[dict[str, Any]]) -> str:
    rows = [e for e in events if e.get("kind") == "root_lm" and int(e.get("depth") or 0) == 0]
    if not rows:
        return ""
    vals = [max(0, int(e.get("prompt_tokens") or 0)) for e in rows]
    peak = max(vals) or 1
    bars = []
    for i, (ev, n) in enumerate(zip(rows, vals, strict=True)):
        pct = max(2, round(100 * n / peak))
        inst = ev.get("instruction_count")
        bars.append(
            f'<div class="bar-col" title="iteration {i}: {n} tokens">'
            f'<div class="bar" style="height:{pct}%"></div>'
            f'<div class="bar-n">{n}</div>'
            f'<div class="bar-i">i{i}'
            f"{'' if inst is None else f' · {escape(str(inst))} inst'}</div>"
            f"</div>"
        )
    return f"""
  <section>
    <h2>Parent prompt tokens by iteration</h2>
    <p class="muted">Should stay in the low thousands.
      Growth here means observations are rotting <code>hist</code>.</p>
    <div class="chart">{"".join(bars)}</div>
  </section>
"""


def _instruction_note(events: list[dict[str, Any]]) -> str:
    counts = [int(e["instruction_count"]) for e in events if e.get("instruction_count") is not None]
    if len(counts) < 2:
        return ""
    unique = sorted(set(counts))
    if len(unique) == 1:
        return (
            f'<p class="ok">Instruction count is constant at {unique[0]} '
            "(new observations are not adding rules).</p>"
        )
    return (
        f'<p class="warn">Instruction count changed across events: '
        f"{escape(', '.join(str(x) for x in unique))}. "
        "That usually means rules leaked into observations.</p>"
    )


def _answer_block(answer: str | None) -> str:
    if answer is None:
        return ""
    return f"""
  <section>
    <h2>Answer</h2>
    <pre class="answer">{escape(answer)}</pre>
  </section>
"""


def _event_card(ev: dict[str, Any], index: int) -> str:
    kind = str(ev.get("kind") or "event")
    kind_class = "".join(c if c.isalnum() or c in "-_" else "_" for c in kind)
    depth = int(ev.get("depth") or 0)
    title = {
        "root_lm": "root LM",
        "repl": "REPL cell",
        "llm_query": "llm_query",
        "rlm_query": "rlm_query",
        "parse_error": "parse error",
    }.get(kind, kind)
    bits = [f"#{index}", f"depth {depth}"]
    if ev.get("iteration") is not None:
        bits.append(f"iter {ev['iteration']}")
    if ev.get("model"):
        bits.append(str(ev["model"]))
    if ev.get("instruction_count") is not None and kind not in LM_KINDS:
        bits.append(f"{ev['instruction_count']} inst")
    if ev.get("child_depth") is not None:
        bits.append(f"child depth {ev['child_depth']}")
    if ev.get("answer_n_chars") is not None:
        bits.append(f"{ev['answer_n_chars']} char answer")

    body: list[str] = []
    if kind in LM_KINDS:
        prompt = _as_int(ev.get("prompt_tokens"))
        completion = _as_int(ev.get("completion_tokens"))
        total = None
        if prompt is not None or completion is not None:
            total = (prompt or 0) + (completion or 0)
        lat = _as_float(ev.get("latency_s"))
        lat_s = "—" if lat is None else f"{lat:.2f}s"
        inst = ev.get("instruction_count")
        inst_s = "—" if inst is None else str(inst)
        body.append(
            '<div class="call-metrics">'
            f'<div><div class="label">Prompt tokens</div>'
            f'<div class="value">{_fmt_int(prompt)}</div></div>'
            f'<div><div class="label">Completion tokens</div>'
            f'<div class="value">{_fmt_int(completion)}</div></div>'
            f'<div><div class="label">Total tokens</div>'
            f'<div class="value">{_fmt_int(total)}</div></div>'
            f'<div><div class="label">Cost (USD)</div>'
            f'<div class="value">{_fmt_cost(_as_float(ev.get("cost_usd")))}'
            f"</div></div>"
            f'<div><div class="label">Latency</div>'
            f'<div class="value">{escape(lat_s)}</div></div>'
            f'<div><div class="label">Instructions</div>'
            f'<div class="value">{escape(inst_s)}</div></div>'
            "</div>"
        )
    if ev.get("text_preview"):
        body.append(
            "<details open>"
            "<summary>model output (no executable fence)</summary>"
            f"<pre>{escape(str(ev['text_preview']))}</pre>"
            "</details>"
        )
    if ev.get("error"):
        body.append(f'<pre class="err">{escape(str(ev["error"]))}</pre>')
    if ev.get("code"):
        body.append(
            f"<details open><summary>code</summary><pre>{escape(str(ev['code']))}</pre></details>"
        )
    if ev.get("stdout"):
        body.append(
            "<details open>"
            "<summary>stdout (truncated as shown to the model)</summary>"
            f"<pre>{escape(str(ev['stdout']))}</pre>"
            "</details>"
        )
    inner = "".join(body)
    return (
        f'<article class="ev ev-{kind_class}" style="margin-left:{depth * 1.25}rem">'
        f'<div class="ev-h"><span class="badge">{escape(title)}</span>'
        f'<span class="meta">{escape(" · ".join(bits))}</span></div>'
        f"{inner}</article>"
    )


_CSS = """
:root {
  --bg: #f6f5f1;
  --fg: #1c1b19;
  --muted: #5c5852;
  --line: #d9d4c8;
  --card: #fff;
  --accent: #2155a6;
  --ok: #1f6b3a;
  --warn-bg: #f8ebd4;
  --warn-fg: #6a4b10;
  --err: #9b1c1c;
  --repl: #2155a6;
  --leaf: #6b4ea0;
  --child: #8a4b12;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161513;
    --fg: #eceae4;
    --muted: #a8a398;
    --line: #2e2c28;
    --card: #1e1d1a;
    --accent: #7ea8e8;
    --ok: #7dca96;
    --warn-bg: #3a3018;
    --warn-fg: #e6c88a;
    --err: #ee8b8b;
    --repl: #7ea8e8;
    --leaf: #c4a6ef;
    --child: #e0a56b;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; }
main { max-width: 920px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
h1 { font-size: 1.35rem; font-weight: 650; margin: 0.2rem 0 0.4rem;
  letter-spacing: -0.02em; }
h2 { font-size: 0.92rem; text-transform: uppercase; letter-spacing: 0.06em;
  margin: 2rem 0 0.5rem; }
.kicker { color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em;
  font-size: 0.72rem; margin: 0; }
.sub, .muted, footer { color: var(--muted); }
.sub { margin: 0 0 0.75rem; }
.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0; }
.chip { border: 1px solid var(--line); padding: 0.15rem 0.5rem; font-size: 0.8rem; }
.status { font-weight: 600; }
.status-complete { color: var(--ok); }
.status-incomplete { color: var(--err); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: 0.75rem;
  border: 1px solid var(--line); background: var(--card); padding: 1rem; }
.label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase;
  letter-spacing: 0.05em; }
.value { font-variant-numeric: tabular-nums; font-size: 1.1rem; }
.call-metrics { display: grid;
  grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
  gap: 0.5rem; margin: 0.4rem 0 0.2rem; }
.call-metrics .value { font-size: 1rem; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); background: var(--card); }
table.calls { width: 100%; border-collapse: collapse; font-size: 0.85rem;
  font-variant-numeric: tabular-nums; }
table.calls th, table.calls td { padding: 0.4rem 0.55rem; text-align: right;
  border-bottom: 1px solid var(--line); }
table.calls th.left, table.calls td.left { text-align: left; }
table.calls tfoot td { font-weight: 650; border-bottom: 0; }
.kinds { margin: 0.6rem 0 0; font-size: 0.85rem; }
.warn, .ok { padding: 0.6rem 0.8rem; margin: 0 0 0.8rem; }
.warn { background: var(--warn-bg); color: var(--warn-fg); }
.ok { color: var(--ok); }
.chart { display: flex; align-items: flex-end; gap: 0.45rem; height: 140px;
  border: 1px solid var(--line); background: var(--card); padding: 0.75rem 0.75rem 0.4rem; }
.bar-col { flex: 1; display: flex; flex-direction: column; justify-content: flex-end;
  align-items: center; height: 100%; min-width: 2rem; }
.bar { width: 70%; background: var(--accent); min-height: 2px; }
.bar-n, .bar-i { font-size: 0.68rem; color: var(--muted); font-variant-numeric: tabular-nums; }
pre { white-space: pre-wrap; word-break: break-word; background: var(--bg);
  border: 1px solid var(--line); padding: 0.7rem 0.8rem; font-size: 0.8rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow: auto; }
pre.answer { background: var(--card); }
pre.err { color: var(--err); }
.timeline { display: flex; flex-direction: column; gap: 0.65rem; }
.ev { background: var(--card); border: 1px solid var(--line);
  border-left-width: 3px; padding: 0.7rem 0.8rem; }
.ev-root_lm { border-left-color: var(--accent); }
.ev-repl { border-left-color: var(--repl); }
.ev-llm_query { border-left-color: var(--leaf); }
.ev-rlm_query { border-left-color: var(--child); }
.ev-parse_error { border-left-color: var(--err); }
.ev-h { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline;
  margin-bottom: 0.35rem; }
.badge { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  font-weight: 650; }
.ev-root_lm .badge { color: var(--accent); }
.ev-repl .badge { color: var(--repl); }
.ev-llm_query .badge { color: var(--leaf); }
.ev-rlm_query .badge { color: var(--child); }
.ev-parse_error .badge { color: var(--err); }
.meta { color: var(--muted); font-size: 0.8rem; font-variant-numeric: tabular-nums; }
details { margin-top: 0.4rem; }
summary { cursor: pointer; color: var(--muted); font-size: 0.8rem; }
footer { margin-top: 2.5rem; font-size: 0.8rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; }
.trace-tree { border-left: 2px solid var(--line); padding-left: 0.8rem; }
.trace-node { display: block; margin: 0.38rem 0; border: 1px solid var(--line);
  background: var(--card); }
.trace-node > summary { padding: 0.5rem 0.65rem; display: flex; flex-wrap: wrap;
  gap: 0.45rem; align-items: baseline; }
.trace-node > summary::marker { color: var(--accent); }
.trace-kind { color: var(--accent); font: 0.72rem ui-monospace, monospace;
  text-transform: uppercase; }
.trace-model, .trace-metrics { color: var(--muted); font-size: 0.8rem;
  font-variant-numeric: tabular-nums; }
.trace-detail { border-top: 1px solid var(--line); padding: 0.6rem 0.75rem; }
.trace-detail dl { display: grid; grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.18rem 0.7rem; margin: 0; font-size: 0.8rem; }
.trace-detail dt { color: var(--muted); }
.trace-detail dd { margin: 0; overflow-wrap: anywhere; font-family: ui-monospace, monospace; }
.trace-children { margin: 0.65rem 0 0.1rem 0.7rem; padding-left: 0.7rem;
  border-left: 2px solid var(--line); }
.trace-content h3 { font-size: 0.78rem; margin: 0.8rem 0 0.25rem;
  text-transform: uppercase; letter-spacing: 0.05em; }
.trace-private { margin: 0.7rem 0 0; font-size: 0.8rem; }
.graph-scroll { overflow: auto; border: 1px solid var(--line); background: var(--card); }
.call-graph { display: block; min-width: 700px; width: 100%;
  font-family: ui-sans-serif, system-ui, sans-serif; }
.graph-edge { fill: none; stroke: var(--line); stroke-width: 2; }
.graph-node rect { fill: var(--card); stroke: var(--line); stroke-width: 1.25; }
.graph-node.graph-run rect { fill: color-mix(in srgb, var(--accent) 10%, var(--card));
  stroke: var(--accent); }
.graph-node.graph-model rect { stroke: var(--accent); }
.graph-node.graph-repl rect { stroke: var(--repl); }
.graph-node.graph-callback rect, .graph-node.graph-batch rect { stroke: var(--child); }
.graph-node.graph-tool rect { stroke: var(--leaf); }
.graph-node.graph-error rect, .graph-node.graph-unfinished rect { stroke: var(--err);
  stroke-dasharray: 4 3; }
.graph-kind { fill: var(--muted); font-size: 9px; text-transform: uppercase; }
.graph-label { fill: var(--fg); font-size: 11px; font-weight: 600; }
"""
