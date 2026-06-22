#!/usr/bin/env python3
"""
CDP Bridge MCP vs Playwright MCP — LLM 工具调用对比测评

分别加载 cdp-bridge MCP 和 Playwright MCP，
用相同的用户 query 测试 LLM 完成任务的效率差异。

对比维度:
  - 工具调用次数 (tool call count)
  - 总耗时 (wall clock)
  - Token 消耗 (input / output)
  - API 调用轮次

用法:
  python eval_mcp_compare.py                          # 全部测试用例
  python eval_mcp_compare.py --query "搜索今天天气"     # 单个自定义 query
  python eval_mcp_compare.py --cdp-only                # 仅测试 CDP Bridge
  python eval_mcp_compare.py --playwright-only         # 仅测试 Playwright
  python eval_mcp_compare.py --dry-run                 # 仅启动并列出工具

依赖:
  - CDP Bridge: Chrome 已启动且扩展已连接
  - Playwright MCP: npx @playwright/mcp
  - LLM API: Anthropic 兼容接口 (ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL)
"""

import subprocess
import json
import time
import sys
import os
import argparse
import threading
import queue
import urllib.request
import urllib.error
import re
import datetime
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

# ── LLM API 配置 ─────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get(
    "ANTHROPIC_API_KEY",
    "sk-xxx",
)
ANTHROPIC_BASE_URL = os.environ.get(
    "ANTHROPIC_BASE_URL",
    "https://api.deepseek.com/anthropic",
)
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro")

# ── MCP 服务配置 ─────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# CDP Bridge: HTTP 模式（需要服务已在运行，如 mcp-server-cdp-bridge）
CDP_BRIDGE_URL = os.environ.get("CDP_BRIDGE_URL", "http://localhost:8000/mcp")
# 备用: stdio 模式（自动启动子进程）
CDP_BRIDGE_CMD_FALLBACK = ["uv", "run", "cdp-bridge@latest"]
CDP_BRIDGE_CWD = str(PROJECT_ROOT)

PLAYWRIGHT_MCP_CMD = ["npx", "-y", "@playwright/mcp", "--headless"]
PLAYWRIGHT_MCP_CWD = None  # 使用当前工作目录

# ── MCP 协议超时 ─────────────────────────────────────────────────

MCP_INIT_TIMEOUT = 30
MCP_TOOL_TIMEOUT = 30
LLM_TIMEOUT = 60
MAX_TOOL_ROUNDS = 20  # 防止无限循环


# ═══════════════════════════════════════════════════════════════════
# MCP Client — 通过 stdio JSON-RPC 与 MCP 服务通信
# ═══════════════════════════════════════════════════════════════════

class MCPClient:
    def __init__(self, name: str, cmd: list[str], cwd: str | None = None,
                 env: dict | None = None):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._pending: dict[int, queue.Queue] = {}
        self._reader_thread: threading.Thread | None = None
        self.tools: dict[str, Any] = {}
        self._startup_errors: list[str] = []

    def start(self) -> bool:
        full_env = os.environ.copy()
        if self.env:
            full_env.update(self.env)

        try:
            self.proc = subprocess.Popen(
                self.cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                env=full_env,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as e:
            print(f"  [{self.name}] 启动失败: {e}")
            return False

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        # stderr 收集线程
        def _read_stderr():
            assert self.proc and self.proc.stderr
            for line in self.proc.stderr:
                self._startup_errors.append(line.strip())
                if len(self._startup_errors) > 50:
                    self._startup_errors.pop(0)

        threading.Thread(target=_read_stderr, daemon=True).start()

        init_result = self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "eval-compare", "version": "1.0"},
        })
        if init_result is None:
            print(f"  [{self.name}] 初始化超时")
            return False

        self._send_notification("notifications/initialized", {})

        tools_result = self._call("tools/list", {})
        if tools_result:
            for t in tools_result.get("tools", []):
                self.tools[t["name"]] = t
            print(f"  [{self.name}] 已连接, {len(self.tools)} 个工具")

        return True

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[dict | None, float]:
        if tool_name not in self.tools:
            return {"_skipped": True, "_reason": f"工具 {tool_name} 不存在"}, 0

        t0 = time.perf_counter()
        result = self._call("tools/call", {"name": tool_name, "arguments": arguments})
        elapsed = time.perf_counter() - t0

        if result is None:
            return {"_error": "timeout"}, elapsed
        return result, elapsed

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, payload: dict):
        if self.proc and self.proc.stdin:
            line = json.dumps(payload, ensure_ascii=False)
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()

    def _send_notification(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _call(self, method: str, params: dict) -> dict | None:
        req_id = self._next_id()
        q: queue.Queue = queue.Queue()
        self._pending[req_id] = q
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        timeout = MCP_INIT_TIMEOUT if method == "initialize" else MCP_TOOL_TIMEOUT
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None
        finally:
            self._pending.pop(req_id, None)

    def _read_loop(self):
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = msg.get("id")
            if req_id is not None and req_id in self._pending:
                if "result" in msg:
                    self._pending[req_id].put(msg["result"])
                elif "error" in msg:
                    self._pending[req_id].put({"_error": msg["error"]})


# ═══════════════════════════════════════════════════════════════════
# MCP Client HTTP — 通过 HTTP 与远程 MCP 服务通信
# ═══════════════════════════════════════════════════════════════════

class MCPClientHTTP:
    """通过 HTTP Streamable 传输与 MCP 服务通信（无需启动子进程）。"""

    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url.rstrip("/")
        self.tools: dict[str, Any] = {}
        self._id = 0
        self._session_id: str | None = None
        # 绕过系统代理，直连本地 MCP 服务
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def start(self) -> bool:
        init_result = self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "eval-compare", "version": "1.0"},
        })
        if init_result is None:
            print(f"  [{self.name}] 初始化超时")
            return False

        self._send_notification("notifications/initialized", {})

        tools_result = self._call("tools/list", {})
        if tools_result:
            for t in tools_result.get("tools", []):
                self.tools[t["name"]] = t
            print(f"  [{self.name}] 已连接, {len(self.tools)} 个工具")

        return True

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[dict | None, float]:
        if tool_name not in self.tools:
            return {"_skipped": True, "_reason": f"工具 {tool_name} 不存在"}, 0

        t0 = time.perf_counter()
        result = self._call("tools/call", {"name": tool_name, "arguments": arguments})
        elapsed = time.perf_counter() - t0

        if result is None:
            return {"_error": "timeout"}, elapsed
        return result, elapsed

    def stop(self):
        pass  # HTTP 模式不管理进程

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send_notification(self, method: str, params: dict):
        self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def _call(self, method: str, params: dict) -> dict | None:
        req_id = self._next_id()
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        timeout = MCP_INIT_TIMEOUT if method == "initialize" else MCP_TOOL_TIMEOUT
        return self._post(payload, timeout=timeout)

    def _post(self, payload: dict, timeout: int = MCP_TOOL_TIMEOUT) -> dict | None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self._session_id:
            req.add_header("Mcp-Session-Id", self._session_id)

        try:
            with self._opener.open(req, timeout=timeout) as resp:
                # 保存 session ID
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid

                raw = resp.read().decode("utf-8")
                return self._parse_response(raw)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            print(f"    [{self.name}] HTTP {e.code}: {error_body[:300]}")
            return None
        except Exception as e:
            print(f"    [{self.name}] 请求失败: {e}")
            return None

    def _parse_response(self, raw: str) -> dict | None:
        """解析 HTTP 响应：直接 JSON 或 SSE 流。"""
        raw = raw.strip()

        # SSE 格式 (text/event-stream)
        if raw.startswith("event:") or raw.startswith("data:"):
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    data = line[5:].strip()
                    try:
                        msg = json.loads(data)
                        if "result" in msg:
                            return msg["result"]
                        elif "error" in msg:
                            return {"_error": msg["error"]}
                    except json.JSONDecodeError:
                        continue
            return None

        # 直接 JSON 响应
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            print(f"    [{self.name}] 非 JSON 响应: {raw[:200]}")
            return None

        if "result" in msg:
            return msg["result"]
        elif "error" in msg:
            return {"_error": msg["error"]}
        return None


# ═══════════════════════════════════════════════════════════════════
# Anthropic 兼容 API — 支持 tool use 的消息接口
# ═══════════════════════════════════════════════════════════════════

def convert_mcp_tool_to_anthropic(mcp_tool: dict) -> dict:
    """将 MCP 工具定义转换为 Anthropic tool 格式。"""
    input_schema = mcp_tool.get("inputSchema", {}) or mcp_tool.get("input_schema", {})
    return {
        "name": mcp_tool["name"],
        "description": mcp_tool.get("description", "")[:1024],
        "input_schema": {
            "type": input_schema.get("type", "object"),
            "properties": input_schema.get("properties", {}),
            "required": input_schema.get("required", []),
        },
    }


def call_anthropic(
    messages: list[dict],
    tools: list[dict] | None,
    system: str = "",
    max_tokens: int = 4096,
) -> tuple[dict | None, float]:
    """调用 Anthropic 兼容 API，支持 tool use。"""
    url = f"{ANTHROPIC_BASE_URL}/v1/messages"

    body: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("x-api-key", ANTHROPIC_API_KEY)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            return result, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.perf_counter() - t0
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"    [LLM] HTTP {e.code}: {error_body[:500]}")
        return None, elapsed
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"    [LLM] 请求失败: {e}")
        return None, elapsed


def extract_text_from_content(content: list | str | None) -> str:
    """从 Anthropic 响应 content 中提取纯文本。"""
    if isinstance(content, str):
        return content
    if not content:
        return ""
    texts = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        elif isinstance(block, str):
            texts.append(block)
    return " ".join(texts)


# ═══════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ToolCallRecord:
    tool_name: str
    arguments: dict
    elapsed: float
    success: bool
    summary: str = ""


@dataclass
class RunResult:
    mcp_name: str
    query: str
    rounds: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    api_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_elapsed: float = 0.0
    success: bool = False
    final_text: str = ""
    error: str = ""


# ═══════════════════════════════════════════════════════════════════
# 工具调用 Loop
# ═══════════════════════════════════════════════════════════════════

def run_tool_loop(
    mcp: MCPClient,
    query: str,
    system_prompt: str = "",
) -> RunResult:
    """
    运行工具调用 loop：
    1. 发送 user query + tools 到 LLM
    2. LLM 返回 text 或 tool_use
    3. 如果是 tool_use，通过 MCP 执行，将结果反馈给 LLM
    4. 重复直到 LLM 返回纯文本或达到最大轮次
    """
    result = RunResult(mcp_name=mcp.name, query=query)
    t_start = time.perf_counter()

    tools = [convert_mcp_tool_to_anthropic(t) for t in mcp.tools.values()]
    if not tools:
        result.error = "MCP 没有可用工具"
        return result

    messages: list[dict] = [{"role": "user", "content": query}]

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        result.rounds = round_num
        result.api_calls += 1

        response, llm_elapsed = call_anthropic(
            messages=messages,
            tools=tools,
            system=system_prompt,
        )

        if response is None:
            result.error = f"第 {round_num} 轮 API 调用失败"
            break

        # 累计 token
        usage = response.get("usage", {})
        result.total_input_tokens += usage.get("input_tokens", 0)
        result.total_output_tokens += usage.get("output_tokens", 0)

        # 检查 stop_reason
        stop_reason = response.get("stop_reason", "")
        content = response.get("content", [])

        # 提取 tool_use 和 text
        tool_use_blocks = []
        text_blocks = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_use":
                    tool_use_blocks.append(block)
                elif block.get("type") == "text":
                    text_blocks.append(block.get("text", ""))

        # 没有 tool_use → 任务完成
        if not tool_use_blocks:
            result.final_text = " ".join(text_blocks)
            result.success = True
            break

        # 构建 assistant 消息（包含 tool_use 和可选 text）
        assistant_content: list[dict] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    assistant_content.append({"type": "text", "text": block.get("text", "")})
                elif block.get("type") == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": block.get("input", {}),
                    })
        messages.append({"role": "assistant", "content": assistant_content})

        # 构建 tool_result 消息
        tool_results: list[dict] = []
        for tu_block in tool_use_blocks:
            tool_name = tu_block["name"]
            tool_id = tu_block["id"]
            tool_input = tu_block.get("input", {})

            # 执行工具
            mcp_result, tool_elapsed = mcp.call_tool(tool_name, tool_input)
            ok = mcp_result is not None and "_error" not in mcp_result and not mcp_result.get("_skipped")

            # 提取文本用于反馈给 LLM
            result_text = _extract_tool_result_text(mcp_result)

            summary = _summarize_tool_result(tool_name, mcp_result, ok)
            result.tool_calls.append(ToolCallRecord(
                tool_name=tool_name,
                arguments=tool_input,
                elapsed=tool_elapsed,
                success=ok,
                summary=summary,
            ))

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_text[:8000],  # 截断过长内容
            })

        messages.append({"role": "user", "content": tool_results})

    result.total_elapsed = time.perf_counter() - t_start
    return result


def _extract_tool_result_text(result: dict | None) -> str:
    """从 MCP 工具返回值中提取文本用于 LLM 反馈。"""
    if result is None:
        return "[工具调用超时]"
    if "_error" in result:
        err = result["_error"]
        if isinstance(err, dict):
            return f"[工具错误: {err.get('message', str(err))[:300]}]"
        return f"[工具错误: {str(err)[:300]}]"
    if result.get("_skipped"):
        return f"[工具跳过: {result.get('_reason', '')}]"

    # MCP content 格式
    content = result.get("content", [])
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text", "")
                if t:
                    texts.append(t)
        return "\n".join(texts)[:8000]
    if isinstance(content, str):
        return content[:8000]

    # 其他格式
    return json.dumps(result, ensure_ascii=False)[:8000]


def _summarize_tool_result(tool_name: str, result: dict | None, ok: bool) -> str:
    if result is None:
        return "超时"
    if result.get("_skipped"):
        return f"跳过: {result.get('_reason', '')[:50]}"
    if "_error" in result:
        err = result["_error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return f"错误: {msg[:60]}"
    if not ok:
        return "失败"
    content = result.get("content", [])
    if isinstance(content, list):
        total_len = sum(len(json.dumps(c, ensure_ascii=False)) for c in content)
        return f"返回 {total_len:,} 字符"
    if isinstance(content, str):
        return f"返回 {len(content):,} 字符"
    return f"完成"


# ═══════════════════════════════════════════════════════════════════
# 报告输出
# ═══════════════════════════════════════════════════════════════════

def print_comparison(results: list[RunResult]) -> None:
    """控制台对比输出。"""
    print("\n" + "=" * 72)
    print("  对比结果")
    print("=" * 72)

    header = f"{'指标':<22} {'CDP Bridge':>20} {'Playwright':>20}"
    print(header)
    print("-" * 72)

    cdps = [r for r in results if r.mcp_name == "CDP Bridge"]
    pws = [r for r in results if r.mcp_name == "Playwright"]

    for cdpr, pwr in zip(cdps, pws):
        label = cdpr.query[:40] + ("..." if len(cdpr.query) > 40 else "")
        print(f"\n  [{label}]")
        _print_row("状态", "✓ 成功" if cdpr.success else f"✗ {cdpr.error[:30]}",
                    "✓ 成功" if pwr.success else f"✗ {pwr.error[:30]}")
        _print_row("API 调用轮次", str(cdpr.api_calls), str(pwr.api_calls))
        _print_row("工具调用次数", str(len(cdpr.tool_calls)), str(len(pwr.tool_calls)))
        _print_row("输入 Token", f"{cdpr.total_input_tokens:,}", f"{pwr.total_input_tokens:,}")
        _print_row("输出 Token", f"{cdpr.total_output_tokens:,}", f"{pwr.total_output_tokens:,}")
        _print_row("总 Token", f"{cdpr.total_input_tokens + cdpr.total_output_tokens:,}",
                    f"{pwr.total_input_tokens + pwr.total_output_tokens:,}")
        _print_row("总耗时", f"{cdpr.total_elapsed:.1f}s", f"{pwr.total_elapsed:.1f}s")

        # 工具级别耗时明细
        cdp_tool_time = sum(tc.elapsed for tc in cdpr.tool_calls)
        pw_tool_time = sum(tc.elapsed for tc in pwr.tool_calls)
        _print_row("  工具执行耗时", f"{cdp_tool_time:.1f}s", f"{pw_tool_time:.1f}s")
        _print_row("  LLM 耗时", f"{cdpr.total_elapsed - cdp_tool_time:.1f}s",
                    f"{pwr.total_elapsed - pw_tool_time:.1f}s")

        # 工具调用明细
        if cdpr.tool_calls:
            tools_cdp = ", ".join(f"{tc.tool_name}({tc.elapsed:.1f}s)" for tc in cdpr.tool_calls)
            print(f"    CDP Bridge 工具: {tools_cdp}")
        if pwr.tool_calls:
            tools_pw = ", ".join(f"{tc.tool_name}({tc.elapsed:.1f}s)" for tc in pwr.tool_calls)
            print(f"    Playwright 工具:  {tools_pw}")

    print("-" * 72)

    # 平均对比
    if cdps and pws:
        avg_cdp_rounds = sum(r.api_calls for r in cdps) / len(cdps)
        avg_pw_rounds = sum(r.api_calls for r in pws) / len(pws)
        avg_cdp_tools = sum(len(r.tool_calls) for r in cdps) / len(cdps)
        avg_pw_tools = sum(len(r.tool_calls) for r in pws) / len(pws)
        avg_cdp_tokens = sum(r.total_input_tokens + r.total_output_tokens for r in cdps) / len(cdps)
        avg_pw_tokens = sum(r.total_input_tokens + r.total_output_tokens for r in pws) / len(pws)
        avg_cdp_time = sum(r.total_elapsed for r in cdps) / len(cdps)
        avg_pw_time = sum(r.total_elapsed for r in pws) / len(pws)

        print(f"\n  {'平均指标':<22} {'CDP Bridge':>20} {'Playwright':>20}")
        print(f"  {'─'*22} {'─'*20} {'─'*20}")
        _print_row("API 轮次", f"{avg_cdp_rounds:.1f}", f"{avg_pw_rounds:.1f}")
        _print_row("工具调用", f"{avg_cdp_tools:.1f}", f"{avg_pw_tools:.1f}")
        _print_row("Token", f"{avg_cdp_tokens:,.0f}", f"{avg_pw_tokens:,.0f}")
        _print_row("耗时", f"{avg_cdp_time:.1f}s", f"{avg_pw_time:.1f}s")

    print("=" * 72)


def _print_row(label: str, left: str, right: str):
    print(f"  {label:<22} {left:>20} {right:>20}")


def write_report(
    output_path: str,
    results: list[RunResult],
    cdp_tools: dict | None,
    pw_tools: dict | None,
) -> None:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md: list[str] = []

    md.append("# CDP Bridge vs Playwright — MCP 对比测评报告")
    md.append("")
    md.append(f"**测试时间**: {now}")
    md.append(f"**LLM 模型**: {ANTHROPIC_MODEL}")
    md.append(f"**API**: {ANTHROPIC_BASE_URL}")
    md.append("")

    # 工具清单
    if cdp_tools:
        md.append("## 1. CDP Bridge 工具清单")
        md.append("")
        md.append("| 工具名 | 描述 |")
        md.append("|--------|------|")
        for name, info in sorted(cdp_tools.items()):
            desc = info.get("description", "")[:120]
            md.append(f"| `{name}` | {desc} |")
        md.append("")

    if pw_tools:
        md.append("## 2. Playwright MCP 工具清单")
        md.append("")
        md.append("| 工具名 | 描述 |")
        md.append("|--------|------|")
        for name, info in sorted(pw_tools.items()):
            desc = info.get("description", "")[:120]
            md.append(f"| `{name}` | {desc} |")
        md.append("")

    # 对比表格
    md.append("## 3. 对比结果")
    md.append("")
    md.append("| 查询 | MCP | 状态 | API轮次 | 工具调用 | 输入Token | 输出Token | 总Token | 耗时 |")
    md.append("|------|-----|------|---------|---------|----------|----------|---------|------|")

    for r in results:
        query_short = r.query[:50] + ("..." if len(r.query) > 50 else "")
        total_tokens = r.total_input_tokens + r.total_output_tokens
        status = "✓" if r.success else "✗"
        md.append(
            f"| {query_short} | {r.mcp_name} | {status} | {r.api_calls} | {len(r.tool_calls)} | "
            f"{r.total_input_tokens:,} | {r.total_output_tokens:,} | {total_tokens:,} | "
            f"{r.total_elapsed:.1f}s |"
        )
    md.append("")

    # 工具调用明细
    md.append("## 4. 工具调用明细")
    md.append("")
    for r in results:
        md.append(f"### {r.mcp_name} — `{r.query[:60]}`")
        md.append("")
        if r.tool_calls:
            md.append("| # | 工具 | 参数 | 耗时 | 状态 | 摘要 |")
            md.append("|---|------|------|------|------|------|")
            for i, tc in enumerate(r.tool_calls, 1):
                args_short = json.dumps(tc.arguments, ensure_ascii=False)[:80]
                status = "✓" if tc.success else "✗"
                md.append(f"| {i} | `{tc.tool_name}` | `{args_short}` | {tc.elapsed:.2f}s | {status} | {tc.summary[:50]} |")
        else:
            md.append("*(无工具调用)*")
        md.append("")
        if r.final_text:
            md.append(f"**LLM 最终输出**: {r.final_text[:300]}")
        md.append("")

    content = "\n".join(md)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n报告已保存到: {output_path}")


# ═══════════════════════════════════════════════════════════════════
# 默认测试用例
# ═══════════════════════════════════════════════════════════════════

DEFAULT_QUERIES = [
    "打开小红书 ，告诉我首页第一篇文章内容的标题是什么",
    "浏览 https://www.runoob.com/numpy/numpy-tutorial.html 页面，告诉我这个教程网站里面numpy的位运算内容",
]


# ═══════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="CDP Bridge vs Playwright MCP — LLM 工具调用对比测评"
    )
    p.add_argument("--query", type=str, nargs="*",
                   help="自定义测试 query (可多个)")
    p.add_argument("--cdp-only", action="store_true",
                   help="仅测试 CDP Bridge MCP")
    p.add_argument("--playwright-only", action="store_true",
                   help="仅测试 Playwright MCP")
    p.add_argument("--dry-run", action="store_true",
                   help="仅启动 MCP 服务并列出工具")
    p.add_argument("--system-prompt", type=str, default="",
                   help="自定义 system prompt")
    return p.parse_args()


def start_mcp_stdio(name: str, cmd: list[str], cwd: str | None) -> MCPClient | None:
    """启动 stdio 模式的 MCP 服务（作为子进程）。"""
    client = MCPClient(name, cmd, cwd=cwd)
    if client.start():
        return client
    client.stop()
    return None


def start_mcp_http(name: str, url: str) -> MCPClientHTTP | None:
    """连接 HTTP 模式的 MCP 服务（服务已在运行）。"""
    client = MCPClientHTTP(name, url)
    if client.start():
        return client
    client.stop()
    return None


def main():
    args = parse_args()

    queries = args.query if args.query else DEFAULT_QUERIES
    test_cdp = not args.playwright_only
    test_pw = not args.cdp_only

    print("=" * 72)
    print("  CDP Bridge vs Playwright — MCP 对比测评")
    print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  LLM: {ANTHROPIC_MODEL}")
    print(f"  API: {ANTHROPIC_BASE_URL}")
    print(f"  测试 CDP Bridge: {'是' if test_cdp else '否'}")
    print(f"  测试 Playwright: {'是' if test_pw else '否'}")
    print(f"  查询数: {len(queries)}")
    print("=" * 72)

    cdp_client: MCPClient | MCPClientHTTP | None = None
    pw_client: MCPClient | MCPClientHTTP | None = None

    # ── 启动 MCP 服务 ──
    if test_cdp:
        print(f"\n连接 CDP Bridge (HTTP): {CDP_BRIDGE_URL}")
        cdp_client = start_mcp_http("CDP Bridge", CDP_BRIDGE_URL)
        if not cdp_client:
            # 备用: 尝试 stdio 模式
            print(f"  HTTP 连接失败，尝试 stdio: {' '.join(CDP_BRIDGE_CMD_FALLBACK)}")
            cdp_client = start_mcp_stdio("CDP Bridge", CDP_BRIDGE_CMD_FALLBACK, CDP_BRIDGE_CWD)
        if not cdp_client:
            print("  CDP Bridge 启动失败")

    if test_pw:
        print(f"\n启动 Playwright MCP: {' '.join(PLAYWRIGHT_MCP_CMD)}")
        pw_client = start_mcp_stdio("Playwright", PLAYWRIGHT_MCP_CMD, PLAYWRIGHT_MCP_CWD)
        if not pw_client:
            print("  Playwright MCP 启动失败")

    # ── dry-run ──
    if args.dry_run:
        for client, label in [(cdp_client, "CDP Bridge"), (pw_client, "Playwright")]:
            if client:
                print(f"\n{label} 工具 ({len(client.tools)}):")
                for name, info in sorted(client.tools.items()):
                    desc = info.get("description", "")[:120]
                    print(f"  - {name}: {desc}")
        for c in [cdp_client, pw_client]:
            if c:
                c.stop()
        return

    # ── 执行测试 ──
    results: list[RunResult] = []
    system_prompt = args.system_prompt or (
        "你是一个浏览器操作助手。使用提供的工具完成用户的任务。"
        "完成任务后给出简洁的总结。如果工具调用失败，尝试其他方法。"
    )

    for i, query in enumerate(queries):
        print(f"\n{'─'*72}")
        print(f"  查询 {i+1}/{len(queries)}: {query}")
        print(f"{'─'*72}")

        clients_to_test = []
        if cdp_client:
            clients_to_test.append(cdp_client)
        if pw_client:
            clients_to_test.append(pw_client)

        for client in clients_to_test:
            print(f"\n  [{client.name}] 开始执行...")
            result = run_tool_loop(client, query, system_prompt)
            results.append(result)

            # 简要输出
            status = "✓" if result.success else "✗"
            total_tokens = result.total_input_tokens + result.total_output_tokens
            print(f"  [{client.name}] {status} "
                  f"API:{result.api_calls}轮 "
                  f"工具:{len(result.tool_calls)}次 "
                  f"Token:{total_tokens:,} "
                  f"耗时:{result.total_elapsed:.1f}s")
            if result.error:
                print(f"    error: {result.error}")
            if result.final_text:
                print(f"    result: {result.final_text[:150]}")

    # ── 输出对比 ──
    if results:
        print_comparison(results)

        report_dir = Path(__file__).resolve().parent
        report_path = report_dir / "eval_compare_report.md"
        write_report(
            str(report_path),
            results,
            cdp_client.tools if cdp_client else None,
            pw_client.tools if pw_client else None,
        )

    # ── 清理 ──
    print(f"\n清理...")
    for c in [cdp_client, pw_client]:
        if c:
            c.stop()
    print("  已停止所有 MCP 服务")


if __name__ == "__main__":
    main()
