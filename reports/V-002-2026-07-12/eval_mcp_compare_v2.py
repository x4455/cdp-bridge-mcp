#!/usr/bin/env python3
"""V2: CDP Bridge 与 Playwright MCP 的可重复对比测评。

设计目标：同一 query、同一模型、成对重复运行；同时记录效率、可靠性、答案质量
和工具轨迹。脚本只使用标准库，支持 CDP Bridge 的 streamable HTTP 和 stdio。

示例：
  python eval_mcp_compare_v2.py --preflight
  python eval_mcp_compare_v2.py --repeats 3
  ANTHROPIC_API_KEY=... python eval_mcp_compare_v2.py --case numpy
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "eval_compare_report.md"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic").rstrip("/")
MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro")
CDP_URL = os.environ.get("CDP_BRIDGE_URL", "http://localhost:8000/mcp")
CDP_CMD = ["uv", "run", "cdp-bridge@latest"]
PW_CMD = ["npx", "-y", "@playwright/mcp", "--headless"]
INIT_TIMEOUT = 30
TOOL_TIMEOUT = 45
LLM_TIMEOUT = 90
MAX_ROUNDS = 20


@dataclass(frozen=True)
class Case:
    key: str
    query: str
    expected_terms: tuple[str, ...] = ()
    quality_note: str = ""


CASES = (
    Case("xiaohongshu", "打开小红书，告诉我首页第一篇文章内容的标题是什么"),
    Case(
        "numpy",
        "浏览 https://www.runoob.com/numpy/numpy-tutorial.html 页面，告诉我这个教程网站里面 numpy 的位运算内容",
        ("bitwise_and", "bitwise_or", "bitwise_xor", "按位与", "按位或"),
        "应定位到 NumPy 位运算页面，并准确概括主要函数/操作。",
    ),
    Case(
        "tabs",
        "查看当前浏览器打开的标签页，列出每个标签页的标题和 URL。",
        (),
        "答案至少应包含标签页信息，不能把工具错误当成标签页。",
    ),
)


def esc(value: Any, limit: int = 240) -> str:
    text = str(value if value is not None else "").replace("\n", " ").replace("|", "\\|").replace("`", "\\`")
    return text[:limit] + ("…" if len(text) > limit else "")


class MCPClient:
    def __init__(self, name: str, cmd: list[str] | None = None, cwd: str | None = None, url: str | None = None):
        self.name, self.cmd, self.cwd, self.url = name, cmd, cwd, url
        self.proc: subprocess.Popen[str] | None = None
        self.tools: dict[str, dict] = {}
        self._id = 0
        self._pending: dict[int, queue.Queue] = {}
        self._reader: threading.Thread | None = None
        self.session_id: str | None = None
        self.http = url is not None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def start(self) -> bool:
        if self.http:
            init = self.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "eval-v2", "version": "2.0"}}, INIT_TIMEOUT)
            if init is None:
                return False
            self.notify("notifications/initialized", {})
            listed = self.call("tools/list", {}, TOOL_TIMEOUT) or {}
        else:
            try:
                self.proc = subprocess.Popen(self.cmd or [], cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            except (OSError, FileNotFoundError):
                return False
            self._reader = threading.Thread(target=self._read_stdio, daemon=True)
            self._reader.start()
            init = self.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "eval-v2", "version": "2.0"}}, INIT_TIMEOUT)
            if init is None:
                return False
            self.notify("notifications/initialized", {})
            listed = self.call("tools/list", {}, TOOL_TIMEOUT) or {}
        self.tools = {x["name"]: x for x in listed.get("tools", []) if isinstance(x, dict) and x.get("name")}
        return bool(self.tools)

    def _next(self) -> int:
        self._id += 1
        return self._id

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def call(self, method: str, params: dict, timeout: int = TOOL_TIMEOUT) -> dict | None:
        req_id = self._next()
        if not self.http:
            q: queue.Queue = queue.Queue()
            self._pending[req_id] = q
            self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            try:
                return q.get(timeout=timeout)
            except queue.Empty:
                return None
            finally:
                self._pending.pop(req_id, None)
        payload = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}, ensure_ascii=False).encode()
        request = urllib.request.Request(self.url or "", payload, method="POST", headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        if self.session_id:
            request.add_header("Mcp-Session-Id", self.session_id)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
                return self._parse_http(response.read().decode("utf-8", "replace"))
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            return None

    def _send(self, payload: dict) -> None:
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def _read_stdio(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        for line in self.proc.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = message.get("id")
            if req_id in self._pending:
                self._pending[req_id].put(message.get("result", {"_error": message.get("error", "JSON-RPC error")}))

    @staticmethod
    def _parse_http(raw: str) -> dict | None:
        for line in raw.strip().splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                break
        try:
            msg = json.loads(raw)
            return msg.get("result", {"_error": msg.get("error", "JSON-RPC error")})
        except json.JSONDecodeError:
            return None

    def tool(self, name: str, arguments: dict) -> tuple[dict | None, float]:
        if name not in self.tools:
            return {"_skipped": f"unknown tool: {name}"}, 0.0
        started = time.perf_counter()
        result = self.call("tools/call", {"name": name, "arguments": arguments}, TOOL_TIMEOUT)
        return result, time.perf_counter() - started

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


@dataclass
class ToolRecord:
    name: str
    args: dict
    elapsed: float
    ok: bool
    result_chars: int
    error: str = ""


@dataclass
class Run:
    backend: str
    case: Case
    repeat: int
    started_at: str = ""
    rounds: int = 0
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed: float = 0.0
    success: bool = False
    quality: float = 0.0
    final_text: str = ""
    error: str = ""
    tools: list[ToolRecord] = field(default_factory=list)


def tool_text(result: dict | None) -> str:
    if result is None:
        return "[tool timeout]"
    if "_error" in result:
        return f"[tool error] {result['_error']}"
    if "_skipped" in result:
        return f"[tool skipped] {result['_skipped']}"
    content = result.get("content", "")
    if isinstance(content, list):
        return "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))[:12000]
    return str(content)[:12000]


def as_tool(t: dict) -> dict:
    schema = t.get("inputSchema") or t.get("input_schema") or {"type": "object"}
    return {"name": t["name"], "description": str(t.get("description", ""))[:1600], "input_schema": schema}


def llm(messages: list[dict], tools: list[dict], system: str) -> tuple[dict | None, float]:
    body = {"model": MODEL, "max_tokens": 4096, "messages": messages, "tools": tools, "system": system}
    request = urllib.request.Request(f"{BASE_URL}/v1/messages", json.dumps(body, ensure_ascii=False).encode(), method="POST", headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=LLM_TIMEOUT) as response:
            return json.loads(response.read().decode()), time.perf_counter() - started
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        return {"_error": str(exc)}, time.perf_counter() - started


def quality_score(run: Run) -> float:
    text = run.final_text.lower()
    if not run.success or not text:
        return 0.0
    if not run.case.expected_terms:
        return 1.0 if len(text) >= 20 and not text.startswith("[") else 0.0
    hits = sum(1 for term in run.case.expected_terms if term.lower() in text)
    return round(min(1.0, hits / max(3, len(run.case.expected_terms) * 0.6)), 2)


def run_case(client: MCPClient, case: Case, repeat: int, system: str) -> Run:
    run = Run(client.name, case, repeat, dt.datetime.now().isoformat(timespec="seconds"))
    started = time.perf_counter()
    messages: list[dict] = [{"role": "user", "content": case.query}]
    tools = [as_tool(t) for t in client.tools.values()]
    for round_no in range(1, MAX_ROUNDS + 1):
        run.rounds = round_no
        run.api_calls += 1
        response, _ = llm(messages, tools, system)
        if not response or response.get("_error"):
            run.error = str((response or {}).get("_error", "LLM request failed"))
            break
        usage = response.get("usage", {})
        run.input_tokens += int(usage.get("input_tokens", 0) or 0)
        run.output_tokens += int(usage.get("output_tokens", 0) or 0)
        content = response.get("content", [])
        uses = [x for x in content if isinstance(x, dict) and x.get("type") == "tool_use"]
        texts = [x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text"]
        if not uses:
            run.final_text = " ".join(texts).strip()
            run.success = bool(run.final_text) and response.get("stop_reason") != "max_tokens"
            break
        messages.append({"role": "assistant", "content": content})
        results = []
        for use in uses:
            value, elapsed = client.tool(use.get("name", ""), use.get("input", {}))
            ok = value is not None and "_error" not in value and "_skipped" not in value
            txt = tool_text(value)
            error = "" if ok else txt[:300]
            run.tools.append(ToolRecord(use.get("name", ""), use.get("input", {}), elapsed, ok, len(txt), error))
            results.append({"type": "tool_result", "tool_use_id": use.get("id", ""), "content": txt})
        messages.append({"role": "user", "content": results})
    else:
        run.error = f"超过最大工具轮次 {MAX_ROUNDS}"
    run.elapsed = time.perf_counter() - started
    run.quality = quality_score(run)
    return run


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def avg(runs: list[Run], attr: str) -> float:
    return sum(float(getattr(x, attr)) for x in runs) / len(runs) if runs else 0.0


def report(path: Path, runs: list[Run], clients: dict[str, MCPClient], preflight: list[str], args: argparse.Namespace) -> None:
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    md = ["# V2 CDP Bridge vs Playwright MCP 测评报告", "", f"**生成时间**: {now}", f"**模型**: `{esc(MODEL)}`", f"**API**: `{esc(BASE_URL)}`", f"**重复次数**: {args.repeats}", "", "## 1. 测评设计", "", "本版本采用相同 query、相同模型和成对重复运行；不把模型是否输出文本直接等同于答案正确。记录 MCP 工具调用、API 轮次、输入/输出 Token、耗时、工具失败和答案质量。", "", "| 维度 | 定义 |", "|---|---|", "| 任务成功 | 模型在限制内返回非空最终答案，且未因 max_tokens 截断 |", "| 答案质量 | 基于场景验收词的可解释启发式分数；无验收词的场景只检查答案非空 |", "| 工具成功率 | 工具返回非 timeout/error/unknown-tool 的比例 |", "| 耗时 | 从该次首个 LLM 请求开始至最终答案/失败的墙钟时间 |", "", "## 2. 前置条件与工具清单", ""]
    if preflight:
        md += ["### 预检结果", "", *[f"- {esc(x)}" for x in preflight], ""]
    for name, client in clients.items():
        md += [f"### {name}（{len(client.tools)} 个工具）", "", "| 工具 | 描述 |", "|---|---|"]
        md += [f"| `{esc(n, 100)}` | {esc(t.get('description', ''), 300)} |" for n, t in sorted(client.tools.items())]
        md.append("")
    md += ["## 3. 汇总结果", "", "| 场景 | MCP | 成功率 | 平均质量 | 平均 API 轮次 | 平均工具调用 | 平均工具成功率 | 平均输入 Token | 平均输出 Token | 平均耗时 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for case in CASES:
        for backend in ("CDP Bridge", "Playwright"):
            group = [r for r in runs if r.case.key == case.key and r.backend == backend]
            if not group:
                continue
            calls = sum(len(r.tools) for r in group)
            ok_calls = sum(sum(t.ok for t in r.tools) for r in group)
            avg_tool_calls = sum(len(r.tools) for r in group) / len(group)
            md.append(f"| {case.key} | {backend} | {pct(sum(r.success for r in group)/len(group))} | {avg(group, 'quality'):.2f} | {avg(group, 'api_calls'):.1f} | {avg_tool_calls:.1f} | {pct(ok_calls/calls if calls else 0)} | {avg(group, 'input_tokens'):,.0f} | {avg(group, 'output_tokens'):,.0f} | {avg(group, 'elapsed'):.1f}s |")
    md += ["", "## 4. 成对差异", "", "正数表示 CDP Bridge 的数值更大；Token/耗时/调用数的负数通常表示 CDP Bridge 更省。只对同一场景、同一重复编号配对，避免不同 query 样本混算。", "", "| 场景 | 重复 | Δ API轮次 | Δ 工具调用 | Δ 总Token | Δ 耗时 | Δ 质量 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for case in CASES:
        for repeat in range(1, args.repeats + 1):
            c = next((r for r in runs if r.case.key == case.key and r.backend == "CDP Bridge" and r.repeat == repeat), None)
            p = next((r for r in runs if r.case.key == case.key and r.backend == "Playwright" and r.repeat == repeat), None)
            if c and p:
                md.append(f"| {case.key} | {repeat} | {c.api_calls-p.api_calls:+d} | {len(c.tools)-len(p.tools):+d} | {c.input_tokens+c.output_tokens-p.input_tokens-p.output_tokens:+d} | {c.elapsed-p.elapsed:+.1f}s | {c.quality-p.quality:+.2f} |")
    md += ["", "## 5. 逐次运行明细", ""]
    for r in runs:
        md += [f"### {r.backend} / {r.case.key} / 第 {r.repeat} 次", "", f"- 状态：{'成功' if r.success else '失败'}；质量：{r.quality:.2f}；API：{r.api_calls} 轮；Token：{r.input_tokens + r.output_tokens:,}；耗时：{r.elapsed:.2f}s", f"- 场景验收说明：{r.case.quality_note or '以非空、非错误最终答案为最低验收条件。'}"]
        if r.error:
            md.append(f"- 错误：`{esc(r.error, 500)}`")
        md += ["", "| # | 工具 | 参数 | 耗时 | 状态 | 返回字符 | 错误 |", "|---:|---|---|---:|---|---:|---|"]
        for i, t in enumerate(r.tools, 1):
            md.append(f"| {i} | `{esc(t.name, 100)}` | `{esc(json.dumps(t.args, ensure_ascii=False), 260)}` | {t.elapsed:.2f}s | {'✓' if t.ok else '✗'} | {t.result_chars:,} | {esc(t.error, 180)} |")
        if not r.tools:
            md.append("| - | *(无工具调用)* | | | | | |")
        md += ["", "**模型最终答案**:", "", esc(r.final_text, 2000) or "*(无)*", ""]
    md += ["## 6. 结论与限制", "", "- 本报告的答案质量是轻量、可审计的启发式评分，不替代人工核验；尤其是小红书首页内容会随时间、登录态和推荐流变化。", "- CDP Bridge 连接真实浏览器会话，Playwright 通常使用其独立浏览器环境；两者的登录态、缓存、网络和页面推荐流不完全等价，不能把本报告解释成纯协议基准。", "- 多次运行仍可能受网络、模型采样、页面动态内容和浏览器前台状态影响；比较时应关注中位数/成功率，而不是单次最好成绩。", "- 若前置条件不足，本脚本仍会输出本报告，但结果区为空，预检结果会明确列出缺失项。", ""]
    path.write_text("\n".join(md), encoding="utf-8")


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="V2 CDP Bridge vs Playwright MCP evaluation")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--case", choices=[x.key for x in CASES] + ["all"], default="all")
    p.add_argument("--cdp-only", action="store_true")
    p.add_argument("--playwright-only", action="store_true")
    p.add_argument("--preflight", action="store_true", help="只检查前置条件并生成 Markdown")
    p.add_argument("--system-prompt", default="你是严谨的浏览器操作助手。只使用提供的工具完成任务；不要臆测工具没有返回的事实。完成后给出简洁、可核验的答案。")
    return p.parse_args()


def main() -> int:
    config = args()
    if config.repeats < 1:
        raise SystemExit("--repeats 必须 >= 1")
    selected = [x for x in CASES if config.case == "all" or x.key == config.case]
    preflight = []
    if not API_KEY:
        preflight.append("未设置 ANTHROPIC_API_KEY：无法执行 LLM 测评。")
    if config.repeats > 1:
        preflight.append(f"将对 {len(selected)} 个场景分别重复 {config.repeats} 次；动态网页结果可能随时间变化。")
    clients: dict[str, MCPClient] = {}
    if not config.playwright_only and not config.preflight:
        cdp = MCPClient("CDP Bridge", url=CDP_URL)
        if cdp.start():
            clients[cdp.name] = cdp
        else:
            preflight.append(f"CDP Bridge 无法连接：{CDP_URL}；将尝试 stdio。")
            cdp = MCPClient("CDP Bridge", cmd=CDP_CMD, cwd=str(ROOT))
            if cdp.start():
                clients[cdp.name] = cdp
            else:
                preflight.append("CDP Bridge HTTP 与 stdio 均不可用。")
    if not config.cdp_only and not config.preflight:
        pw = MCPClient("Playwright", cmd=PW_CMD)
        if pw.start():
            clients[pw.name] = pw
        else:
            preflight.append("Playwright MCP 无法启动（请确认 npx/网络可用）。")
    runs: list[Run] = []
    if not config.preflight and API_KEY and clients:
        for case in selected:
            for repeat in range(1, config.repeats + 1):
                for client in clients.values():
                    print(f"[{case.key}] {client.name} repeat={repeat}", flush=True)
                    runs.append(run_case(client, case, repeat, config.system_prompt))
    elif not API_KEY:
        preflight.append("本次未执行任务，因此没有把前置条件失败伪装成 0 分或成功样本。")
    report(OUT, runs, clients, preflight, config)
    for client in clients.values():
        client.stop()
    print(f"报告已生成：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
