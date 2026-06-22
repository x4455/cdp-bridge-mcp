# CDP Bridge vs Playwright — MCP 对比测评报告

**测试时间**: 2026-06-23 01:55:06
**LLM 模型**: deepseek-v4-pro
**API**: https://api.deepseek.com/anthropic

## 1. CDP Bridge 工具清单

| 工具名 | 描述 |
|--------|------|
| `browser_batch` | Run multiple extension/CDP commands in one request.

Args:
    commands: Command objects supported by the extension, suc |
| `browser_execute_js` | Execute JavaScript in the browser and capture results plus DOM changes.

Args:
    script: JavaScript code to execute (o |
| `browser_focus_tab` | Bring a Chrome tab to the foreground: activate the tab AND focus its window.

Unlike browser_switch_tab (which only chan |
| `browser_get_tabs` | Get all open browser tabs with their IDs, URLs, and titles. |
| `browser_navigate` | Navigate the active tab to a URL.

Args:
    url: The URL to navigate to.
 |
| `browser_scan` | Get simplified HTML content of the active tab plus tab list. The HTML is optimized for LLM consumption (stripped of scri |
| `browser_screenshot` | Take a screenshot of the active tab (returns base64 PNG).

Args:
    tab_id: Optional tab ID to screenshot. Uses active  |
| `browser_switch_tab` | Switch the active MCP browser tab without changing the visible Chrome tab.

Args:
    tab_id: The tab ID to switch to (f |
| `browser_wait` | Wait until JavaScript condition returns a truthy value.

Args:
    condition_js: JavaScript expression or script. The re |
| `save_screenshot` | Save base64 screenshot data to PNG file.

Args:
    screenshot_json_str_or_file: JSON output from browser_screenshot too |

## 2. Playwright MCP 工具清单

| 工具名 | 描述 |
|--------|------|
| `browser_click` | Perform click on a web page |
| `browser_close` | Close the page |
| `browser_console_messages` | Returns all console messages |
| `browser_drag` | Perform drag and drop between two elements |
| `browser_drop` | Drop files or MIME-typed data onto an element, as if dragged from outside the page. At least one of "paths" or "data" mu |
| `browser_evaluate` | Evaluate JavaScript expression on page or element |
| `browser_file_upload` | Upload one or multiple files |
| `browser_fill_form` | Fill multiple form fields |
| `browser_handle_dialog` | Handle a dialog |
| `browser_hover` | Hover over element on page |
| `browser_navigate` | Navigate to a URL |
| `browser_navigate_back` | Go back to the previous page in the history |
| `browser_network_request` | Returns full details (headers and body) of a single network request, or a single part if `part` is set. Use the number f |
| `browser_network_requests` | Returns a numbered list of network requests since loading the page. Use browser_network_request with the number to get f |
| `browser_press_key` | Press a key on the keyboard |
| `browser_resize` | Resize the browser window |
| `browser_run_code_unsafe` | Run a Playwright code snippet. Unsafe: executes arbitrary JavaScript in the Playwright server process and is RCE-equival |
| `browser_select_option` | Select an option in a dropdown |
| `browser_snapshot` | Capture accessibility snapshot of the current page, this is better than screenshot |
| `browser_tabs` | List, create, close, or select a browser tab. |
| `browser_take_screenshot` | Take a screenshot of the current page. You can't perform actions based on the screenshot, use browser_snapshot for actio |
| `browser_type` | Type text into editable element |
| `browser_wait_for` | Wait for text to appear or disappear or a specified time to pass |

## 3. 对比结果

| 查询 | MCP | 状态 | API轮次 | 工具调用 | 输入Token | 输出Token | 总Token | 耗时 |
|------|-----|------|---------|---------|----------|----------|---------|------|
| 打开小红书 ，告诉我首页第一篇文章内容的标题是什么 | CDP Bridge | ✓ | 3 | 2 | 3,668 | 322 | 3,990 | 6.1s |
| 打开小红书 ，告诉我首页第一篇文章内容的标题是什么 | Playwright | ✗ | 20 | 20 | 13,691 | 3,057 | 16,748 | 114.2s |
| 浏览 https://www.runoob.com/numpy/numpy-tutorial.htm... | CDP Bridge | ✓ | 6 | 5 | 6,544 | 1,472 | 8,016 | 22.4s |
| 浏览 https://www.runoob.com/numpy/numpy-tutorial.htm... | Playwright | ✓ | 10 | 9 | 11,834 | 1,758 | 13,592 | 35.5s |

## 4. 工具调用明细

### CDP Bridge — `打开小红书 ，告诉我首页第一篇文章内容的标题是什么`

| # | 工具 | 参数 | 耗时 | 状态 | 摘要 |
|---|------|------|------|------|------|
| 1 | `browser_navigate` | `{"url": "https://www.xiaohongshu.com"}` | 0.42s | ✓ | 返回 109 字符 |
| 2 | `browser_wait` | `{"condition_js": "document.querySelector('.note-item') || document.querySelector` | 0.41s | ✓ | 返回 14,855 字符 |

**LLM 最终输出**: 小红书首页第一篇文章的标题是：

**「阿根廷vs奥地利第23分钟萨比策打门被挡」**

该文章来自用户「**世界杯瞬间**」，是一篇带有视频的内容，目前有 10 个点赞。

### Playwright — `打开小红书 ，告诉我首页第一篇文章内容的标题是什么`

| # | 工具 | 参数 | 耗时 | 状态 | 摘要 |
|---|------|------|------|------|------|
| 1 | `browser_navigate` | `{"url": "https://www.xiaohongshu.com"}` | 6.69s | ✓ | 返回 664 字符 |
| 2 | `browser_navigate` | `{"url": "https://m.xiaohongshu.com"}` | 2.20s | ✓ | 返回 662 字符 |
| 3 | `browser_snapshot` | `{}` | 0.00s | ✓ | 返回 825 字符 |
| 4 | `browser_click` | `{"target": "e12", "element": "返回首页按钮"}` | 2.05s | ✓ | 返回 656 字符 |
| 5 | `browser_navigate` | `{"url": "https://www.xiaohongshu.com/explore"}` | 2.34s | ✓ | 返回 672 字符 |
| 6 | `browser_navigate` | `{"url": "https://www.baidu.com/s?wd=%E5%B0%8F%E7%BA%A2%E4%B9%A6%E9%A6%96%E9%A1%B` | 1.06s | ✓ | 返回 975 字符 |
| 7 | `browser_navigate` | `{"url": "https://www.bing.com/search?q=%E5%B0%8F%E7%BA%A2%E4%B9%A6+%E9%A6%96%E9%` | 0.64s | ✓ | 返回 407 字符 |
| 8 | `browser_snapshot` | `{}` | 0.03s | ✓ | 返回 13,519 字符 |
| 9 | `browser_navigate` | `{"url": "https://cn.bing.com/search?q=%E5%B0%8F%E7%BA%A2%E4%B9%A6+%E4%BB%8A%E6%9` | 0.32s | ✓ | 返回 539 字符 |
| 10 | `browser_navigate` | `{"url": "https://www.google.com/search?q=site:xiaohongshu.com+%E9%A6%96%E9%A1%B5` | 5.57s | ✓ | 返回 801 字符 |
| 11 | `browser_navigate` | `{"url": "https://duckduckgo.com/?q=%E5%B0%8F%E7%BA%A2%E4%B9%A6+%E9%A6%96%E9%A1%B` | 3.46s | ✓ | 返回 548 字符 |
| 12 | `browser_snapshot` | `{}` | 0.02s | ✓ | 返回 10,862 字符 |
| 13 | `browser_press_key` | `{"key": "Escape"}` | 0.02s | ✓ | 返回 118 字符 |
| 14 | `browser_snapshot` | `{}` | 0.02s | ✓ | 返回 10,862 字符 |
| 15 | `browser_click` | `{"target": "e133", "element": "关闭菜单按钮"}` | 5.03s | ✓ | 返回 1,084 字符 |
| 16 | `browser_evaluate` | `{"function": "() => {\n  // Close the side menu if open\n  const closeBtn = docu` | 2.33s | ✓ | 返回 452 字符 |
| 17 | `browser_take_screenshot` | `{"type": "png"}` | 0.09s | ✓ | 返回 357,941 字符 |
| 18 | `browser_run_code_unsafe` | `{"code": "async (page) => {\n  // Close side menu\n  const closeBtn = page.locat` | 30.00s | ✗ | 错误: timeout |
| 19 | `browser_evaluate` | `{"function": "() => {\n  // Close side menu\n  const closeBtn = document.querySe` | 6.04s | ✓ | 返回 974 字符 |
| 20 | `browser_navigate` | `{"url": "https://www.sogou.com/web?query=%E5%B0%8F%E7%BA%A2%E4%B9%A6+%E9%A6%96%E` | 0.35s | ✓ | 返回 528 字符 |


### CDP Bridge — `浏览 https://www.runoob.com/numpy/numpy-tutorial.html 页面，告诉我这个`

| # | 工具 | 参数 | 耗时 | 状态 | 摘要 |
|---|------|------|------|------|------|
| 1 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-tutorial.html"}` | 0.43s | ✓ | 返回 130 字符 |
| 2 | `browser_scan` | `{"text_only": true}` | 0.83s | ✓ | 返回 6,273 字符 |
| 3 | `browser_execute_js` | `{"script": "\n// 找到\"NumPy 位运算\"的链接\nconst links = document.querySelectorAll('a'` | 2.67s | ✓ | 返回 240 字符 |
| 4 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-binary-operators.html"}` | 0.41s | ✓ | 返回 138 字符 |
| 5 | `browser_scan` | `{"text_only": true}` | 0.82s | ✓ | 返回 8,075 字符 |

**LLM 最终输出**: 已成功获取 NumPy 位运算页面的全部内容。以下是该教程网站的 **NumPy 位运算** 内容总结：

---

## 📘 NumPy 位运算（菜鸟教程）

**页面地址**：`https://www.runoob.com/numpy/numpy-binary-operators.html`

### 概述
位运算是在二进制位级别上直接操作数字的运算。NumPy 以 `bitwise_` 开头的函数提供矢量化位运算，比 Python 原生位运算符在数组上性能更高。

### 六大位运算函数

| 操作 | 函数 | 运算符 | 说明 |
|------|------|--------|--

### Playwright — `浏览 https://www.runoob.com/numpy/numpy-tutorial.html 页面，告诉我这个`

| # | 工具 | 参数 | 耗时 | 状态 | 摘要 |
|---|------|------|------|------|------|
| 1 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-tutorial.html"}` | 4.02s | ✓ | 返回 315 字符 |
| 2 | `browser_snapshot` | `{}` | 0.03s | ✓ | 返回 26,807 字符 |
| 3 | `browser_click` | `{"target": "ref=e78", "element": "NumPy 位运算导航链接"}` | 0.00s | ✓ | 返回 124 字符 |
| 4 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-binary-operators.html"}` | 2.11s | ✓ | 返回 332 字符 |
| 5 | `browser_snapshot` | `{}` | 0.05s | ✓ | 返回 38,895 字符 |
| 6 | `browser_evaluate` | `{"function": "() => window.scrollTo(0, 0)"}` | 6.05s | ✓ | 返回 139 字符 |
| 7 | `browser_take_screenshot` | `{"fullPage": true, "type": "png"}` | 0.38s | ✓ | 返回 429,778 字符 |
| 8 | `browser_snapshot` | `{"boxes": true}` | 0.04s | ✓ | 返回 51,527 字符 |
| 9 | `browser_evaluate` | `{"function": "() => {\n  const mainContent = document.querySelector('.article-bo` | 0.55s | ✓ | 返回 5,291 字符 |

**LLM 最终输出**: 我已经完整获取了 NumPy 位运算页面的内容。以下是该教程中 **NumPy 位运算** 的详细内容总结：

---

## NumPy 位运算（NumPy Binary Operators）

### 概述
位运算是一种在二进制数字的位级别上进行操作的一类运算，直接操作二进制数字的各个位。NumPy 提供了一系列 **`bitwise_`** 开头的位运算函数，允许对数组中的元素进行逐位操作，支持矢量化处理，性能比 Python 原生位运算符更高。

---

### 六大位运算函数

| 操作 | 函数 | 描述 |
|------|------|------|
| **按位与** | 
