# V2 CDP Bridge vs Playwright MCP 测评报告

**生成时间**: 2026-07-12T17:56:24+08:00
**模型**: `deepseek-v4-pro`
**API**: `https://api.deepseek.com/anthropic`
**重复次数**: 1

## 1. 测评设计

本版本采用相同 query、相同模型和成对重复运行；不把模型是否输出文本直接等同于答案正确。记录 MCP 工具调用、API 轮次、输入/输出 Token、耗时、工具失败和答案质量。

| 维度 | 定义 |
|---|---|
| 任务成功 | 模型在限制内返回非空最终答案，且未因 max_tokens 截断 |
| 答案质量 | 基于场景验收词的可解释启发式分数；无验收词的场景只检查答案非空 |
| 工具成功率 | 工具返回非 timeout/error/unknown-tool 的比例 |
| 耗时 | 从该次首个 LLM 请求开始至最终答案/失败的墙钟时间 |

## 2. 前置条件与工具清单

### CDP Bridge（10 个工具）

| 工具 | 描述 |
|---|---|
| `browser_batch` | Run multiple extension/CDP commands in one request.  Args:     commands: Command objects supported by the extension, such as         {"cmd":"cdp","method":"DOM.getDocument","params":{"depth":1}}.     tab_id: Optional tab ID inherited by commands that omit tabId.     timeout: Seconds to wait for the … |
| `browser_execute_js` | Execute JavaScript in the browser and capture results plus DOM changes.  Args:     script: JavaScript code to execute (or JSON command for CDP operations).     switch_tab_id: Switch to this tab before executing.     no_monitor: Skip DOM change monitoring (faster, less info).  |
| `browser_focus_tab` | Bring a Chrome tab to the foreground: activate the tab AND focus its window.  Unlike browser_switch_tab (which only changes the MCP-side active session without touching the visible Chrome UI), this actually makes the tab visible to the user. Use this when the user can't find the tab the agent is wor… |
| `browser_get_tabs` | Get all open browser tabs with their IDs, URLs, and titles. |
| `browser_navigate` | Navigate the active tab to a URL.  Args:     url: The URL to navigate to.  |
| `browser_save_image` | Save base64 screenshot data to PNG file.  Args:     screenshot_json_str_or_file: JSON output from browser_screenshot tool, or path to a JSON file containing the screenshot data.     output_path: Output PNG file path or directory. Behavior:         - Existing directory: save as {directory}/screenshot… |
| `browser_scan` | Get simplified HTML content of the active tab plus tab list. The HTML is optimized for LLM consumption (stripped of scripts, styles, invisible elements).  Args:     tabs_only: Only return tab list without page content (saves tokens).     switch_tab_id: Switch to this tab before scanning.     text_on… |
| `browser_screenshot` | Take a screenshot of the active tab (returns base64 PNG).  Args:     tab_id: Optional tab ID to screenshot. Uses active tab if empty.  |
| `browser_switch_tab` | Switch the active MCP browser tab without changing the visible Chrome tab.  Args:     tab_id: The tab ID to switch to (from browser_get_tabs).  |
| `browser_wait` | Wait until JavaScript condition returns a truthy value.  Args:     condition_js: JavaScript expression or script. The return value is tested for truthiness.     timeout: Maximum seconds to wait.     interval: Seconds between checks.     switch_tab_id: Optional tab ID to make active before waiting.  |

### Playwright（24 个工具）

| 工具 | 描述 |
|---|---|
| `browser_click` | Perform click on a web page |
| `browser_close` | Close the page |
| `browser_console_messages` | Returns all console messages |
| `browser_drag` | Perform drag and drop between two elements |
| `browser_drop` | Drop files or MIME-typed data onto an element, as if dragged from outside the page. At least one of "paths" or "data" must be provided. |
| `browser_evaluate` | Evaluate JavaScript expression on page or element |
| `browser_file_upload` | Upload one or multiple files |
| `browser_fill_form` | Fill multiple form fields |
| `browser_find` | Search the accessibility snapshot of the current page for text or a regular expression. Returns matching snapshot nodes with a few lines of surrounding context (like search snippets), each shown under its path from the root of the tree, which is cheaper than capturing the whole snapshot when you onl… |
| `browser_handle_dialog` | Handle a dialog |
| `browser_hover` | Hover over element on page |
| `browser_navigate` | Navigate to a URL |
| `browser_navigate_back` | Go back to the previous page in the history |
| `browser_network_request` | Returns full details (headers and body) of a single network request, or a single part if \`part\` is set. Use the number from browser_network_requests. |
| `browser_network_requests` | Returns a numbered list of network requests since loading the page. Use browser_network_request with the number to get full details. |
| `browser_press_key` | Press a key on the keyboard |
| `browser_resize` | Resize the browser window |
| `browser_run_code_unsafe` | Run a Playwright code snippet. Unsafe: executes arbitrary JavaScript in the Playwright server process and is RCE-equivalent. |
| `browser_select_option` | Select an option in a dropdown |
| `browser_snapshot` | Capture accessibility snapshot of the current page, this is better than screenshot |
| `browser_tabs` | List, create, close, or select a browser tab. |
| `browser_take_screenshot` | Take a screenshot of the current page. You can't perform actions based on the screenshot, use browser_snapshot for actions. |
| `browser_type` | Type text into editable element |
| `browser_wait_for` | Wait for text to appear or disappear or a specified time to pass |

## 3. 汇总结果

| 场景 | MCP | 成功率 | 平均质量 | 平均 API 轮次 | 平均工具调用 | 平均工具成功率 | 平均输入 Token | 平均输出 Token | 平均耗时 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| xiaohongshu | CDP Bridge | 100.0% | 1.00 | 4.0 | 3.0 | 100.0% | 4,799 | 458 | 14.2s |
| xiaohongshu | Playwright | 100.0% | 1.00 | 6.0 | 5.0 | 100.0% | 2,204 | 1,159 | 37.4s |
| numpy | CDP Bridge | 100.0% | 1.00 | 6.0 | 5.0 | 100.0% | 8,855 | 1,460 | 29.9s |
| numpy | Playwright | 100.0% | 1.00 | 11.0 | 10.0 | 100.0% | 16,204 | 2,443 | 68.1s |
| tabs | CDP Bridge | 100.0% | 1.00 | 2.0 | 1.0 | 100.0% | 1,112 | 532 | 8.8s |
| tabs | Playwright | 100.0% | 1.00 | 2.0 | 1.0 | 100.0% | 132 | 166 | 4.4s |

## 4. 成对差异

正数表示 CDP Bridge 的数值更大；Token/耗时/调用数的负数通常表示 CDP Bridge 更省。只对同一场景、同一重复编号配对，避免不同 query 样本混算。

| 场景 | 重复 | Δ API轮次 | Δ 工具调用 | Δ 总Token | Δ 耗时 | Δ 质量 |
|---|---:|---:|---:|---:|---:|---:|
| xiaohongshu | 1 | -2 | -2 | +1894 | -23.3s | +0.00 |
| numpy | 1 | -5 | -5 | -8332 | -38.2s | +0.00 |
| tabs | 1 | +0 | +0 | +1346 | +4.4s | +0.00 |

## 5. 逐次运行明细

### CDP Bridge / xiaohongshu / 第 1 次

- 状态：成功；质量：1.00；API：4 轮；Token：5,257；耗时：14.19s
- 场景验收说明：以非空、非错误最终答案为最低验收条件。

| # | 工具 | 参数 | 耗时 | 状态 | 返回字符 | 错误 |
|---:|---|---|---:|---|---:|---|
| 1 | `browser_navigate` | `{"url": "https://www.xiaohongshu.com"}` | 0.41s | ✓ | 73 |  |
| 2 | `browser_wait` | `{"condition_js": "document.querySelector('.note-item') \|\| document.querySelector('[class*=\"note\"]') \|\| document.querySelector('.feeds-page') \|\| document.querySelector('.home-container')", "timeout": 15}` | 0.41s | ✓ | 2,470 |  |
| 3 | `browser_scan` | `{"text_only": true}` | 0.83s | ✓ | 3,565 |  |

**模型最终答案**:

小红书首页第一篇文章的标题是：**"右右滑感受"**，作者是「收音鸡」，点赞数约 4 万。

### Playwright / xiaohongshu / 第 1 次

- 状态：成功；质量：1.00；API：6 轮；Token：3,363；耗时：37.45s
- 场景验收说明：以非空、非错误最终答案为最低验收条件。

| # | 工具 | 参数 | 耗时 | 状态 | 返回字符 | 错误 |
|---:|---|---|---:|---|---:|---|
| 1 | `browser_navigate` | `{"url": "https://www.xiaohongshu.com"}` | 2.02s | ✓ | 626 |  |
| 2 | `browser_snapshot` | `{}` | 0.01s | ✓ | 776 |  |
| 3 | `browser_click` | `{"target": "ref=f3e12", "element": "返回首页按钮"}` | 0.00s | ✓ | 95 |  |
| 4 | `browser_run_code_unsafe` | `{"code": "async (page) => {\n  // Try clicking the \"返回首页\" text\n  await page.click('text=返回首页');\n  await page.waitForTimeout(3000);\n  return await page.url();\n}"}` | 4.51s | ✓ | 1,045 |  |
| 5 | `browser_run_code_unsafe` | `{"code": "async (page) => {\n  // Try with mobile viewport and different approach\n  await page.setViewportSize({ width: 390, height: 844 });\n  // Try clearing and going to homepage\n  await page.goto('https://www.xiaohongshu.com/explore', { waitUntil: 'netwo…` | 5.24s | ✓ | 1,304 |  |

**模型最终答案**:

很遗憾，我无法完成您的请求。以下是具体情况：  ---  ## 访问结果：失败 ❌  **小红书（xiaohongshu.com）返回了安全限制页面**，错误信息如下：  - **错误码**：\`300012\` - **提示信息**：*"IP存在风险，请切换可靠网络环境后重试"*  ---  ### 原因分析  小红书的反爬/安全机制检测到当前网络环境的 IP（属于数据中心/代理 IP），触发了风控限制。我尝试了以下方法均无法绕过：  \| 方法 \| 结果 \| \|------\|------\| \| 桌面端访问首页 \| 被拦截 \| \| 移动端 viewport 访问 \| 被拦截 \| \| 直接访问 \`/explore\` 探索页 \| 被拦截 \|  这是 IP 层面的限制，单纯通过浏览器操作无法突破。您可能需要：  1. **切换网络环境**（使用家庭/办公网络而非数据中心 IP） 2. **使用已登录的 Cookie** 注入到浏览器中 3. **通过小红书开放 API** 或第三方数据平台获取内容  如果您能提供可用的 Cookie 或切换到可靠的网络环境，我可以再帮您获取首页第一篇文章的标题。

### CDP Bridge / numpy / 第 1 次

- 状态：成功；质量：1.00；API：6 轮；Token：10,315；耗时：29.92s
- 场景验收说明：应定位到 NumPy 位运算页面，并准确概括主要函数/操作。

| # | 工具 | 参数 | 耗时 | 状态 | 返回字符 | 错误 |
|---:|---|---|---:|---|---:|---|
| 1 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-tutorial.html"}` | 0.41s | ✓ | 94 |  |
| 2 | `browser_scan` | `{}` | 0.89s | ✓ | 12,000 |  |
| 3 | `browser_execute_js` | `{"script": "(() => {\n  const links = document.querySelectorAll('#leftcolumn a');\n  for (const a of links) {\n    if (a.textContent.includes('位运算')) {\n      return { href: a.href, text: a.textContent.trim() };\n    }\n  }\n  return null;\n})()"}` | 2.72s | ✓ | 565 |  |
| 4 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-binary-operators.html"}` | 0.41s | ✓ | 102 |  |
| 5 | `browser_scan` | `{"text_only": true}` | 0.83s | ✓ | 7,249 |  |

**模型最终答案**:

## 菜鸟教程 — NumPy 位运算 内容总结  该页面位于：**https://www.runoob.com/numpy/numpy-binary-operators.html**  以下是该教程中 NumPy 位运算的完整内容：  ---  ### 概述  位运算是在二进制数字的位级别上进行操作的一类运算，直接操作各个位。NumPy 提供了一系列 \`bitwise_\` 开头的位运算函数，支持矢量化处理，性能高于 Python 原生位运算。  ---  ### 六大位运算函数  \| 操作 \| 函数 \| 描述 \| \|------\|------\|------\| \| 按位与 \| \`numpy.bitwise_and(x1, x2)\` \| 对应位都为 1 时结果为 1，否则为 0 \| \| 按位或 \| \`numpy.bitwise_or(x1, x2)\` \| 对应位有一个为 1 时结果为 1 \| \| 按位异或 \| \`numpy.bitwise_xor(x1, x2)\` \| 对应位相异为 1，相同为 0 \| \| 按位取反 \| \`numpy.invert(x)\` \| 每个位取反（0→1，1→0） \| \| 左移 \| \`numpy.left_shift(x1, x2)\` \| 所有位向左移动指定位数，右侧补 0 \| \| 右移 \| \`numpy.right_shift(x1, x2)\` \| 所有位向右移动指定位数 \|  ---  ### 也可使用运算符  - \`&\` — 与运算，如 \`1010 & 1100 = 1000\` - \`\|\` — 或运算，如 \`1010 \| 1100 = 1110\` - \`^\` — 异或运算，如 \`1010 ^ 1100 = 0110\` - \`~\` — 取反运算，如 \`~1010 = 0101\` - \`<<\` — 左移，如 \`1010 << 2 = 101000\` - \`>>\` — 右移，如 \`1010 >> 2 = 0010\`  ---  ### 各函数详解  #### 1. \`bitwise_and()\` — 按位与 - 示例：\`np.bitwise_and(13, 17)\` → 结果为 \`1\` - 13 二进制 \`0b1101\`，17 二进制 \`0b10001\`，逐位与后得 \`00001\` = 1  #### 2. \`bitwise_or()\` — 按位或 - 示例：\`np.bitwise_or(13, 17)\` → 结果为 \`29\` - 逐位或后得 \`11101\` = 29  #### 3. \`invert()\` — 按位取反 - 对于有符号整数：取补码后 +1，最高位为符号位（0 正 1 负） - \`~1\` 的计算：\`00000001\` → 取反 \`11111110\` → 符号位为1，其余取反 \`10000001\` → 末位+1 \`10000010\` = **-2** - 对于 \`uint8\`：\`np.invert([13])\` → \`[242]\`（\`00001101\` → \`11110010\`）  #### 4. \`left_shift()\` — 左移 - \`np.left_shift(10, 2)\` → \`40\`（即 \`10 × 2²\`） - 10 的二进制 \`00001010\`，左移两位 → \`00101000\` = 40  #### 5. \`right_shift()\` — 右移 - \`np.right_shift(10, 1)\` → \`5\` - 10 的二进制 \`00001010\`，右移一位 → \`00000101\` = 5  ---  **可核验**：你可以在浏览器中打开 https://www.runoob.com/numpy/numpy-binary-operators.html 直接查看上述完整内容。

### Playwright / numpy / 第 1 次

- 状态：成功；质量：1.00；API：11 轮；Token：18,647；耗时：68.13s
- 场景验收说明：应定位到 NumPy 位运算页面，并准确概括主要函数/操作。

| # | 工具 | 参数 | 耗时 | 状态 | 返回字符 | 错误 |
|---:|---|---|---:|---|---:|---|
| 1 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-tutorial.html"}` | 5.00s | ✓ | 279 |  |
| 2 | `browser_snapshot` | `{}` | 0.02s | ✓ | 8,902 |  |
| 3 | `browser_find` | `{"text": "位运算"}` | 0.03s | ✓ | 38 |  |
| 4 | `browser_find` | `{"text": "bitwise"}` | 0.03s | ✓ | 42 |  |
| 5 | `browser_evaluate` | `{"function": "() => {\n  const links = document.querySelectorAll('a[href*=\"numpy\"]');\n  return Array.from(links).map(l => ({href: l.href, text: l.textContent.trim()})).filter(l => l.href.includes('numpy'));\n}"}` | 0.53s | ✓ | 3,664 |  |
| 6 | `browser_navigate` | `{"url": "https://www.runoob.com/numpy/numpy-binary-operators.html"}` | 5.11s | ✓ | 296 |  |
| 7 | `browser_snapshot` | `{}` | 0.04s | ✓ | 12,000 |  |
| 8 | `browser_evaluate` | `{"function": "() => {\n  window.scrollTo(0, document.body.scrollHeight);\n  return 'scrolled to bottom';\n}"}` | 0.54s | ✓ | 185 |  |
| 9 | `browser_snapshot` | `{}` | 0.04s | ✓ | 12,000 |  |
| 10 | `browser_evaluate` | `{"function": "() => {\n  const content = document.querySelector('.article-body') \|\| document.querySelector('.content') \|\| document.querySelector('article');\n  if (content) return content.innerText;\n  // fallback: get main content area\n  const main = doc…` | 1.09s | ✓ | 4,718 |  |

**模型最终答案**:

已成功找到并完整浏览了菜鸟教程中 NumPy 的位运算章节。以下是该页面的完整内容总结：  ---  ## NumPy 位运算 — 菜鸟教程  **页面地址：** [https://www.runoob.com/numpy/numpy-binary-operators.html](https://www.runoob.com/numpy/numpy-binary-operators.html)  ---  ### 📌 概述  位运算是在二进制数字的**位级别**上进行操作的一类运算。NumPy 提供了以 \`bitwise_\` 开头的一系列函数，支持对数组元素进行逐位矢量化操作，性能比 Python 原生位运算符更高。  ---  ### 📊 六大位运算函数一览  \| 操作 \| 函数 \| 描述 \| \|------\|------\|------\| \| **按位与** \| \`numpy.bitwise_and(x1, x2)\` \| 对应位都为1则结果为1 \| \| **按位或** \| \`numpy.bitwise_or(x1, x2)\` \| 对应位有一个为1则结果为1 \| \| **按位异或** \| \`numpy.bitwise_xor(x1, x2)\` \| 对应位相异为1，相同为0 \| \| **按位取反** \| \`numpy.invert(x)\` \| 对每个位取反（0变1，1变0） \| \| **左移** \| \`numpy.left_shift(x1, x2)\` \| 将位向左移动指定位数，右侧补0 \| \| **右移** \| \`numpy.right_shift(x1, x2)\` \| 将位向右移动指定位数，左侧补0 \|  ---  ### 🔣 运算符方式  也可以直接使用 Python 风格的操作符：  - \`&\` — 与运算（例：\`1010 & 1100 = 1000\`） - \`\|\` — 或运算（例：\`1010 \| 1100 = 1110\`） - \`^\` — 异或运算（例：\`1010 ^ 1100 = 0110\`） - \`~\` — 取反运算（例：\`~1010 = 0101\`） - \`<<\` — 左移运算（例：\`1010 << 2 = 101000\`） - \`>>\` — 右移运算（例：\`1010 >> 2 = 0010\`）  ---  ### 📝 各函数详解  #### 1. \`bitwise_and\` — 按位与 - 真值表：\`1&1=1\`，\`1&0=0\`，\`0&1=0\`，\`0&0=0\` - 示例：\`np.bitwise_and(13, 17)\` → \`1\`（\`0b1101 & 0b10001 = 0b00001\`）  #### 2. \`bitwise_or\` — 按位或 - 真值表：\`1\|1=1\`，\`1\|0=1\`，\`0\|1=1\`，\`0\|0=0\` - 示例：\`np.bitwise_or(13, 17)\` → \`29\`（\`0b1101 \| 0b10001 = 0b11101\`）  #### 3. \`invert\` — 按位取反 - 对有符号整数，取补码后 +1 - \`~1\` 的计算步骤：\`00000001\` → 取反 → \`11111110\` → 符号位为1，其余取反 → \`10000001\` → 末位加1 → \`10000010\` → 十进制 **-2** - 示例：\`np.invert(np.array([13], dtype=np.uint8))\` → \`[242]\`（\`00001101\` → \`11110010\`）  #### 4. \`left_shift\` — 左移 - 示例：\`np.left_shift(10, 2)\` → \`40\`（\`00001010\` → \`00101000\`）  #### 5. \`right_shift\` — 右移 - 示例：\`np.right_shift(40, 2)\` → \`10\`（\`00101000\` → \`00001010\`）  ---  以上就是该教程网站中 NumPy 位运算的全部内容，涵盖了概述、六大函数表格、运算符方式，以及每个函数的详细说明与代码实例。

### CDP Bridge / tabs / 第 1 次

- 状态：成功；质量：1.00；API：2 轮；Token：1,644；耗时：8.78s
- 场景验收说明：答案至少应包含标签页信息，不能把工具错误当成标签页。

| # | 工具 | 参数 | 耗时 | 状态 | 返回字符 | 错误 |
|---:|---|---|---:|---|---:|---|
| 1 | `browser_get_tabs` | `{}` | 0.01s | ✓ | 2,098 |  |

**模型最终答案**:

当前浏览器共打开了 **12 个标签页**，以下是详细信息：  \| # \| 标签页标题 \| URL \| \|---\|-----------\|-----\| \| 1 \| **NumPy 位运算 \\| 菜鸟教程** \| \`https://www.runoob.com/numpy/numpy-binary-operators.html\` \| \| 2 \| **Learn Claude Code** \| \`https://learn.shareai.run/zh/s19/\` \| \| 3 \| **t.me** \| \`https://t.me/s/shareAliyun?q=瑞克与莫蒂\` \| \| 4 \| **阿里云盘分享** \| \`https://www.aliyundrive.com/s/D5BK6RoD7UU\` \| \| 5 \| **阿里云盘分享** \| \`https://www.aliyundrive.com/s/RGhACcTP3Ys\` \| \| 6 \| **max_tokens 是输入还是输出 - Google 搜索** \| \`https://www.google.com/search?q=max_tokens+是输入还是输出...\` \| \| 7 \| **套餐详情 - MiniMax 开放平台** \| \`https://platform.minimaxi.com/console/plan\` \| \| 8 \| **Xiaomi MiMo 开放平台** \| \`https://platform.xiaomimimo.com/console/balance?userId=3029466137\` \| \| 9 \| **DeepSeek** \| \`https://platform.deepseek.com/usage\` \| \| 10 \| **模型 & 价格 \\| DeepSeek API Docs** \| \`https://api-docs.deepseek.com/zh-cn/quick_start/pricing/\` \| \| 11 \| **首次调用 API \\| DeepSeek API Docs** \| \`https://api-docs.deepseek.com/zh-cn/\` \| \| 12 \| **Qwen Studio** \| \`https://chat.qwen.ai/c/6eeffeca-db8b-4ece-82cf-a0cfb64e0e9c\` \|  > 🟢 当前活跃标签页：**#1 — NumPy 位运算 \| 菜鸟教程**

### Playwright / tabs / 第 1 次

- 状态：成功；质量：1.00；API：2 轮；Token：298；耗时：4.42s
- 场景验收说明：答案至少应包含标签页信息，不能把工具错误当成标签页。

| # | 工具 | 参数 | 耗时 | 状态 | 返回字符 | 错误 |
|---:|---|---|---:|---|---:|---|
| 1 | `browser_tabs` | `{"action": "list"}` | 0.04s | ✓ | 102 |  |

**模型最终答案**:

当前浏览器只有一个标签页：  \| 序号 \| 标题 \| URL \| \|------\|------\|-----\| \| 0 (当前) \| **NumPy 位运算 \\| 菜鸟教程** \| https://www.runoob.com/numpy/numpy-binary-operators.html \|  目前仅打开了这一个标签页。如果有需要，可以打开新的标签页或进行其他操作。

## 6. 结论与限制

- 本报告的答案质量是轻量、可审计的启发式评分，不替代人工核验；尤其是小红书首页内容会随时间、登录态和推荐流变化。
- CDP Bridge 连接真实浏览器会话，Playwright 通常使用其独立浏览器环境；两者的登录态、缓存、网络和页面推荐流不完全等价，不能把本报告解释成纯协议基准。
- 多次运行仍可能受网络、模型采样、页面动态内容和浏览器前台状态影响；比较时应关注中位数/成功率，而不是单次最好成绩。
- 若前置条件不足，本脚本仍会输出本报告，但结果区为空，预检结果会明确列出缺失项。
