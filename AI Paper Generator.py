import os
import re
import sys
import json
import time
import openai
from pathlib import Path
from datetime import datetime

BASE_PATH = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
CONFIG_FILE = BASE_PATH / "config.json"
CHECKPOINT_FILE = BASE_PATH / "others" / "checkpoint.json"
OUTLINE_FILE = BASE_PATH / "outline.txt"
OUTPUT_FILE = BASE_PATH / "OUTPUT" / "Paper.tex"

# ================= 0. 配置与解析 =================

DEFAULT_CONFIG = {
    
    "api_settings": {
        "api_key": "",
        "base_url": "",
        "model": "", 
        "debug_mode": True
    },
    "global_prompt": "你是一位严谨的本领域专家。"

}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"🚨 找不到配置文件 {CONFIG_FILE}！请先填写配置。")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_outline():
    # 核心解析器：将纯文本 Markdown 大纲转化为结构化字典列表
    if not os.path.exists(OUTLINE_FILE):
        raise FileNotFoundError(f"🚨 找不到大纲文件 {OUTLINE_FILE}！请先将大纲保存为该文件。")

    parsed_nodes = []
    current_node = None

    with open(OUTLINE_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue

            # 匹配标题
            title_match = re.match(r'^(section|subsection|subsubsection)\s+(.+)$', line)
        
            if title_match:
                level_name = title_match.group(1) # 获取匹配到的关键字
                title = title_match.group(2).strip()

                # 因为标识符现在直接就是层级名称，不再需要 level_map 转换
                current_node = {
                    "level": level_name,
                    "title": title,
                    "desc": ""
                }
                parsed_nodes.append(current_node)
            
            # 2. 匹配 [描述]
            elif line.startswith('[描述]') and current_node is not None:
                desc_text = line.replace('[描述]', '').strip()
                current_node["desc"] += desc_text + " "
                
    return parsed_nodes

# ================= 1. 状态管理 =================

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "completed_titles": [], 
        "summaries": [], 
        "full_paper_content": [],
        "last_content": "暂无前文"
    }

def save_checkpoint(state):
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

# ================= 2. API 调用 =================

def call_llm(prompt, api_cfg, is_summary=False, max_retries=10):
    if api_cfg["debug_mode"]:
        time.sleep(0.1) 
        if is_summary:
            return "【Debug摘要】模拟摘要生成。"
        else:
            return f"这里是由 Debug 模式模拟生成的内容。"

    client = openai.OpenAI(api_key=api_cfg["api_key"], base_url=api_cfg["base_url"])

    # 引入指数退避重试机制
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model = api_cfg.get("model"),
                messages = [{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
            
        except openai.RateLimitError as e:
            # 专门捕获 429 限流错误
            wait_time = (2 ** attempt) * 10  # 等待时间：10秒, 20秒, 40秒...
            print(f"⚠️ 触发限流 (429)，等待 {wait_time} 秒后重试 (第 {attempt + 1}/{max_retries} 次尝试)...")
            print(e.response.headers)
            time.sleep(wait_time)

        except Exception as e:
            # 捕获其他网络波动或超时错误，同样进行重试
            wait_time = 10
            print(f"❌ API 请求发生异常: {e}。等待 {wait_time} 秒后重试...")
            print(e.response.headers)
            time.sleep(wait_time)

    print("🚨 达到最大重试次数，停止当前生成操作。")
    return None

# ================= 3. 主干流程 =================

def main():
    config = load_config()
    api_cfg = config["api_settings"]
    global_prompt = config["global_prompt"]
    
    print("\n🔍 正在解析纯文本大纲...")
    nodes = parse_outline()
    print(f"✅ 大纲解析成功！共发现 {len(nodes)} 个结构节点。")
    
    state = load_checkpoint()
    
    for node in nodes:
        level = node["level"]
        title = node["title"]
        desc = node["desc"]

        if title in state["completed_titles"]:
            print(f"⏩ 跳过已生成: [{level}] {title}")
            continue

        print(f"\n✍️ 正在撰写: {title} ({level})")

        prompt = f"""
【全局提示词】：
{global_prompt}

【前文摘要】：
{state['summaries']}

【上一个单元】：
{state['last_content']}

【当前任务】：
请撰写论述内容。主题是：“{title}”。
写作重点与核心要求如下：
{desc if desc else "无。"}

【⚠️ 绝对指令 ⚠️】：
1. 直接输出学术正文！
2. 绝对不允许输出诸如 \section, \subsection, \subsubsection 等任何标题层级宏命令，程序会自动处理标题。
3. 纯 LaTeX 格式输出，你可以自由使用数学公式环境（如 $$...$$）和列表。
4. 不要包含任何 Markdown 的代码块标识（如 ```latex 或 **），也不要新定义命令。
5. 我们使用宏包 ctex, amsmath, amssymb, amsthm
"""

        body_content = call_llm(prompt, api_cfg, is_summary=False)
        if not body_content:
            print("🚨 生成中断，进度已保存。")
            break

        # 生成摘要
        print(f"\n | 正在浓缩摘要: {title} ({level})")
        summary_prompt = f"请将以下内容浓缩为200字核心摘要：\n\n{body_content}"
        current_summary = call_llm(summary_prompt, api_cfg, is_summary=True)

        # 【关键拼接】：Python 将结构化标签和 AI 写的正文拼接到一起
        final_latex_chunk = f"\\{level}{{{title}}}\n\n{body_content.strip()}\n"

        # 更新状态
        state["full_paper_content"].append(final_latex_chunk)
        state["summaries"].append(f"[{title}]摘要：{current_summary}")
        state["completed_titles"].append(title)
        state["last_content"] = body_content.strip()

        save_checkpoint(state)

        if not api_cfg["debug_mode"]:
            time.sleep(10)

    # ================= 4. 输出最终可编译的 LaTeX =================
    if len(state["completed_titles"]) == len(nodes):
        print("\n🎉 全文结构生成完毕！正在写入 tex 文件...")

        latex_preamble = r"""
\documentclass[12pt,a4paper]{article}
\usepackage[UTF8]{ctex}
\usepackage{amsmath, amssymb, amsthm, geometry, hyperref}
\geometry{left=2.5cm, right=2.5cm, top=2.5cm, bottom=2.5cm}
\title{论文}
\author{AI}
\begin{document}
\maketitle
\tableofcontents
\newpage
"""

        final_tex = latex_preamble + "\n".join(state["full_paper_content"]) + "\n\\end{document}"
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(final_tex)
        print(f"📁 论文已保存在 {OUTPUT_FILE} ！")

        checkpoint_file_base, checkpoint_file_ext = os.path.splitext(CHECKPOINT_FILE)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{checkpoint_file_base}_{timestamp}{checkpoint_file_ext}"

        os.rename(CHECKPOINT_FILE, new_name)
    else:
        print("\n⏳ 任务未全部完成，进度已保存。")

if __name__ == "__main__":
    main()