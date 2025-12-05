import os
import re
import json
import time
import shutil
import requests
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from bs4 import BeautifulSoup
import google.generativeai as genai

# 尝试导入 EbookLib
try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    ebooklib = None

app = Flask(__name__)

# ================= 配置区域 =================
DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
NOVELS_DIR = "/app/novels"
if not os.path.exists(NOVELS_DIR):
    os.makedirs(NOVELS_DIR)

# 伪装头 (V6 的强力伪装)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Referer': 'https://syosetu.com/',
    'Cookie': 'over18=yes; sas_view=1; sas_c=1'
}

# ================= V6 核心：智能抓取算法 =================
def intelligent_extract(soup):
    """从网页中智能提取正文 (V6逻辑)"""
    candidates = []
    # 1. 尝试标准 ID
    selectors = ["#novel_honbun", ".novel_view", ".entry-content", "#content", ".p-novel__body", ".js-novel-text", "article"]
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator="\n")
            if len(text) > 200: candidates.append(text)

    # 2. 暴力扫描所有 div
    all_divs = soup.find_all("div")
    if all_divs:
        sorted_divs = sorted(all_divs, key=lambda d: len(d.get_text()), reverse=True)[:3]
        for div in sorted_divs:
            text = div.get_text(separator="\n")
            if len(text) > 200: candidates.append(text)

    # 3. 决策
    if not candidates:
        body_text = soup.body.get_text(separator="\n") if soup.body else ""
        return body_text if len(body_text) > 100 else None
    return max(candidates, key=len)

# ================= V7 核心：本地存储与分章 =================
def save_chapter(novel_id, chapter_index, title, content):
    """保存章节"""
    chapter_dir = os.path.join(NOVELS_DIR, novel_id, "chapters")
    if not os.path.exists(chapter_dir): os.makedirs(chapter_dir)
    
    data = {"index": chapter_index, "title": title, "content": content, "translation": ""}
    # 如果已存在，保留旧的翻译
    file_path = os.path.join(chapter_dir, f"{chapter_index}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            if old_data.get('translation'):
                data['translation'] = old_data['translation']

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def create_novel_meta(novel_name, source_type):
    """创建小说元数据"""
    # 简单的 ID 生成 (保留字母数字)
    novel_id = re.sub(r'[^\w\-_]', '', novel_name)[:50] 
    if not novel_id: novel_id = "novel_" + str(int(time.time()))
    
    novel_dir = os.path.join(NOVELS_DIR, novel_id)
    if not os.path.exists(novel_dir): os.makedirs(novel_dir)
    
    meta = {"title": novel_name, "type": source_type, "created_at": time.time()}
    with open(os.path.join(novel_dir, "meta.json"), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    return novel_id

def process_url_import(url):
    """处理 URL 导入 (V6 功能融入 V7)"""
    # 1. 抓取
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # 2. 提取信息
    title = soup.find('title').text.strip() if soup.find('title') else "网页抓取_" + str(int(time.time()))
    content = intelligent_extract(soup)
    
    if not content: raise Exception("无法提取网页正文")
    
    # 3. 保存为一本“书” (单章模式)
    novel_id = create_novel_meta(title, "web")
    save_chapter(novel_id, 1, title, content)
    return novel_id

def process_txt(file_path, novel_name):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: text = f.read()
    novel_id = create_novel_meta(novel_name, "txt")
    
    # 按 3000 字分章
    chunk_size = 3000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    for i, chunk in enumerate(chunks):
        save_chapter(novel_id, i+1, f"第 {i+1} 部分", chunk)
    return novel_id

def process_epub(file_path, novel_name):
    if not ebooklib: return None
    book = epub.read_epub(file_path)
    novel_id = create_novel_meta(novel_name, "epub")
    index = 1
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text = soup.get_text(separator="\n").strip()
            if len(text) > 100:
                title_tag = soup.find(['h1', 'h2', 'h3'])
                title = title_tag.text.strip() if title_tag else f"章节 {index}"
                save_chapter(novel_id, index, title, text)
                index += 1
    return novel_id

# ================= 前端 HTML (融合版) =================
html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌸 姐姐的云端书架 V8</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #fff1f2; padding: 20px; color: #333; max-width: 1000px; margin: 0 auto; }
        .card { background: white; padding: 25px; border-radius: 16px; box-shadow: 0 4px 15px rgba(219,39,119,0.08); margin-bottom: 25px; }
        h1, h2 { color: #db2777; text-align: center; margin-top: 0; }
        .btn { background: #db2777; color: white; border: none; padding: 12px 24px; border-radius: 10px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 500; font-size: 15px; transition: 0.2s; }
        .btn:hover { background: #be185d; transform: translateY(-1px); }
        .btn:disabled { background: #fbcfe8; cursor: wait; }
        .btn-outline { background: white; border: 2px solid #db2777; color: #db2777; }
        input[type="text"], select, input[type="password"] { width: 100%; padding: 12px; border: 1px solid #fbcfe8; border-radius: 8px; box-sizing: border-box; margin-top: 5px; font-size: 14px; }
        
        /* 首页布局 */
        .input-group { margin-bottom: 20px; display: flex; gap: 10px; }
        .bookshelf { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 20px; margin-top: 30px; }
        .book-item { background: #fdf2f8; padding: 20px; border-radius: 12px; text-align: center; cursor: pointer; border: 2px solid transparent; transition: 0.2s; }
        .book-item:hover { border-color: #db2777; background: #fff; transform: translateY(-5px); box-shadow: 0 5px 15px rgba(219,39,119,0.1); }
        .book-icon { font-size: 48px; margin-bottom: 10px; display: block; }
        .book-title { font-weight: bold; font-size: 15px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; line-height: 1.4; height: 42px; }
        .book-tag { font-size: 11px; background: white; padding: 2px 8px; border-radius: 10px; color: #db2777; border: 1px solid #fbcfe8; margin-top: 8px; display: inline-block; }

        /* 阅读页布局 */
        .reader-container { display: flex; gap: 25px; flex-wrap: wrap; margin-top: 20px; }
        .text-box { flex: 1; min-width: 320px; background: #fafafa; padding: 25px; border-radius: 12px; line-height: 1.8; white-space: pre-wrap; height: 75vh; overflow-y: auto; border: 1px solid #eee; font-size: 17px; }
        .trans-box { background: #fff; border: 2px solid #fbcfe8; }
        
        /* 设置面板 (V6 样式回归) */
        .settings-box { background: #fff1f2; border: 2px dashed #fbcfe8; border-radius: 12px; padding: 15px; margin-bottom: 20px; }
        .settings-summary { font-weight: bold; color: #be185d; cursor: pointer; user-select: none; }
        .settings-content { margin-top: 15px; display: grid; gap: 15px; }
    </style>
</head>
<body>

    {% if page == 'home' %}
    <div class="card">
        <h1>📚 姐姐的云端书架</h1>
        
        <div style="background: #fdf2f8; padding: 20px; border-radius: 12px; margin-bottom: 30px;">
            <h3 style="margin-top:0; color:#db2777;">📥 导入新书 (支持 URL 或 文件)</h3>
            
            <div class="input-group">
                <input type="text" id="urlInput" placeholder="🔗 粘贴小说网页链接 (Syosetu / Kakuyomu)...">
                <button class="btn" onclick="importUrl()">抓取保存</button>
            </div>
            
            <div style="text-align: center; color: #888; margin: 10px 0;">—— 或者 ——</div>

            <div style="text-align:center;">
                <label for="fileInput" class="btn btn-outline" style="cursor:pointer; width:100%; box-sizing:border-box;">📂 点击上传 TXT / EPUB 文件</label>
                <input type="file" id="fileInput" accept=".txt,.epub" style="display:none" onchange="uploadFile()">
            </div>
            <div id="importStatus" style="text-align:center; margin-top:10px; font-weight:bold; color:#db2777;"></div>
        </div>

        <div class="bookshelf">
            {% for book in books %}
            <div class="book-item" onclick="window.location.href='/novel/{{ book.id }}'">
                <span class="book-icon">
                    {% if book.type == 'web' %}🌐{% elif book.type == 'epub' %}📘{% else %}📄{% endif %}
                </span>
                <div class="book-title">{{ book.title }}</div>
                <span class="book-tag">{{ book.type | upper }}</span>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <script>
        async function importUrl() {
            const url = document.getElementById('urlInput').value;
            const status = document.getElementById('importStatus');
            if (!url) return;
            status.innerText = "⏳ 正在前往日本网站抓取正文...";
            try {
                const res = await fetch('/import_url', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                window.location.href = "/novel/" + data.id; // 跳转到目录
            } catch (e) { status.innerText = "❌ 抓取失败: " + e; }
        }

        async function uploadFile() {
            const file = document.getElementById('fileInput').files[0];
            const status = document.getElementById('importStatus');
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            status.innerText = "⏳ 正在上传并智能分章...";
            try {
                const res = await fetch('/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                window.location.reload();
            } catch (e) { status.innerText = "❌ 上传失败: " + e; }
        }
    </script>

    {% elif page == 'novel' %}
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #eee; padding-bottom:15px; margin-bottom:15px;">
            <a href="/" class="btn btn-outline">⬅ 返回书架</a>
            <h2 style="margin:0; font-size:1.2rem;">{{ novel_title }}</h2>
        </div>
        <div style="display:grid; gap:10px;">
            {% for ch in chapters %}
            <a href="/read/{{ novel_id }}/{{ ch.index }}" style="text-decoration:none; color:#333; padding:15px; background:#fafafa; border-radius:8px; display:flex; justify-content:space-between; align-items:center; transition:0.2s;">
                <span>{{ ch.title }}</span>
                <span style="font-size:12px; padding:4px 10px; border-radius:12px; background:{% if ch.has_trans %}#d1fae5;color:#059669{% else %}#eee;color:#888{% endif %}">
                    {% if ch.has_trans %}已翻译{% else %}未读{% endif %}
                </span>
            </a>
            {% endfor %}
        </div>
    </div>

    {% elif page == 'read' %}
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <a href="/novel/{{ novel_id }}" class="btn btn-outline">⬅ 目录</a>
            <h3 style="margin:0; font-size:1rem; flex:1; text-align:center;">{{ chapter_title }}</h3>
            {% if next_index %}
            <a href="/read/{{ novel_id }}/{{ next_index }}" class="btn btn-outline">下一章 ➡</a>
            {% endif %}
        </div>

        <details class="settings-box">
            <summary class="settings-summary">⚙️ AI 翻译模型设置 (想要用 DeepSeek 点这里)</summary>
            <div class="settings-content">
                <div>
                    <label>AI 服务商：</label>
                    <select id="provider" onchange="updateDefaults()">
                        <option value="gemini">Google Gemini (免费/默认)</option>
                        <option value="deepseek">DeepSeek (性价比/兼容)</option>
                        <option value="openai">OpenAI / 其它</option>
                    </select>
                </div>
                <div>
                    <label>模型名称 (Model)：</label>
                    <input type="text" id="modelName" value="gemini-1.5-flash">
                </div>
                <div>
                    <label>API Key (留空使用 NAS 预设)：</label>
                    <input type="password" id="customKey" placeholder="如用 DeepSeek 在此填 sk-...">
                </div>
                <div id="baseUrlGroup" style="display:none;">
                    <label>Base URL (API地址)：</label>
                    <input type="text" id="baseUrl" value="https://api.deepseek.com">
                </div>
            </div>
        </details>

        <button id="transBtn" class="btn" style="width:100%; padding:15px; font-size:1.1rem;" onclick="translateChapter()">✨ 开始魔法翻译</button>

        <div class="reader-container">
            <div class="text-box" id="rawText">{{ content }}</div>
            <div class="text-box trans-box" id="transText">
                {% if translation %}
                    {{ translation }}
                {% else %}
                    <div style="color:#aaa; text-align:center; margin-top:100px;">
                        (点击上方按钮，召唤 AI 进行翻译)
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
    
    <input type="hidden" id="novelId" value="{{ novel_id }}">
    <input type="hidden" id="chapterIndex" value="{{ chapter_index }}">

    <script>
        function updateDefaults() {
            const p = document.getElementById('provider').value;
            const m = document.getElementById('modelName');
            const u = document.getElementById('baseUrlGroup');
            const ui = document.getElementById('baseUrl');
            
            if (p === 'gemini') { m.value = 'gemini-1.5-flash'; u.style.display = 'none'; }
            else if (p === 'deepseek') { m.value = 'deepseek-chat'; u.style.display = 'block'; ui.value = 'https://api.deepseek.com'; }
            else { m.value = 'gpt-3.5-turbo'; u.style.display = 'block'; ui.value = ''; }
        }

        async function translateChapter() {
            const btn = document.getElementById('transBtn');
            const transBox = document.getElementById('transText');
            
            // 获取 AI 配置
            const provider = document.getElementById('provider').value;
            const model = document.getElementById('modelName').value;
            const apiKey = document.getElementById('customKey').value;
            const baseUrl = document.getElementById('baseUrl').value;

            btn.disabled = true; btn.innerText = "⏳ 正在翻译中...";
            transBox.innerHTML = "<div style='text-align:center;margin-top:50px'>⏳ AI 正在阅读上下文并翻译...</div>";

            try {
                const res = await fetch('/translate_api', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        novel_id: document.getElementById('novelId').value,
                        chapter_index: document.getElementById('chapterIndex').value,
                        // 传回 V6 风格的配置参数
                        provider, model, api_key: apiKey, base_url: baseUrl
                    })
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                transBox.innerText = data.content;
                btn.innerText = "✅ 翻译完成 (已自动保存)";
            } catch (e) {
                transBox.innerText = "错误: " + e;
                btn.innerText = "❌ 重试";
            } finally {
                btn.disabled = false;
            }
        }
    </script>
    {% endif %}
</body>
</html>
"""

# ================= 路由逻辑 =================

@app.route('/')
def home():
    novels = []
    if os.path.exists(NOVELS_DIR):
        # 按修改时间倒序排列，新书在前
        dirs = sorted(os.listdir(NOVELS_DIR), key=lambda x: os.path.getmtime(os.path.join(NOVELS_DIR, x)), reverse=True)
        for name in dirs:
            meta_path = os.path.join(NOVELS_DIR, name, "meta.json")
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f: novels.append({"id": name, **json.load(f)})
    return render_template_string(html_template, page='home', books=novels)

@app.route('/import_url', methods=['POST'])
def api_import_url():
    try:
        url = request.json.get('url')
        novel_id = process_url_import(url)
        return jsonify({"id": novel_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/upload', methods=['POST'])
def api_upload():
    try:
        file = request.files['file']
        filename = file.filename
        temp_path = os.path.join("/tmp", filename)
        file.save(temp_path)
        
        name = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == '.txt': process_txt(temp_path, name)
        elif ext == '.epub': process_epub(temp_path, name)
        
        os.remove(temp_path)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/novel/<novel_id>')
def view_novel(novel_id):
    meta_path = os.path.join(NOVELS_DIR, novel_id, "meta.json")
    if not os.path.exists(meta_path): return "Book not found", 404
    with open(meta_path, 'r', encoding='utf-8') as f: meta = json.load(f)
    
    chapter_dir = os.path.join(NOVELS_DIR, novel_id, "chapters")
    chapters = []
    if os.path.exists(chapter_dir):
        files = sorted(os.listdir(chapter_dir), key=lambda x: int(x.split('.')[0]))
        for f in files:
            with open(os.path.join(chapter_dir, f), 'r', encoding='utf-8') as j:
                d = json.load(j)
                chapters.append({"index": d['index'], "title": d['title'], "has_trans": bool(d.get('translation'))})
    
    return render_template_string(html_template, page='novel', chapters=chapters, novel_id=novel_id, novel_title=meta['title'])

@app.route('/read/<novel_id>/<int:chapter_index>')
def read_chapter(novel_id, chapter_index):
    file_path = os.path.join(NOVELS_DIR, novel_id, "chapters", f"{chapter_index}.json")
    if not os.path.exists(file_path): return "Chapter not found", 404
    with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
    
    next_path = os.path.join(NOVELS_DIR, novel_id, "chapters", f"{chapter_index + 1}.json")
    return render_template_string(html_template, page='read', novel_id=novel_id, chapter_index=chapter_index,
                                  chapter_title=data['title'], content=data['content'], translation=data.get('translation', ''),
                                  next_index=(chapter_index + 1 if os.path.exists(next_path) else None))

@app.route('/translate_api', methods=['POST'])
def translate_api():
    data = request.json
    novel_id = data.get('novel_id')
    idx = data.get('chapter_index')
    
    # 获取前端传来的 V6 配置
    provider = data.get('provider', 'gemini')
    user_model = data.get('model', 'gemini-1.5-flash')
    user_key = data.get('api_key') or DEFAULT_GEMINI_KEY
    base_url = data.get('base_url')

    # 读取原文
    file_path = os.path.join(NOVELS_DIR, novel_id, "chapters", f"{idx}.json")
    with open(file_path, 'r', encoding='utf-8') as f: chapter_data = json.load(f)
    text = chapter_data['content']

    if not user_key: return jsonify({"error": "请填入 API Key"}), 400

    try:
        # 复用 V6 的多模型逻辑
        prompt = f"你是一位轻小说翻译家。请将以下日语小说片段翻译成流畅、优美且符合中文轻小说阅读习惯的中文。\n\n原文：\n{text[:12000]}"
        trans_text = ""

        if provider == 'gemini':
            genai.configure(api_key=user_key)
            model = genai.GenerativeModel(user_model)
            trans_text = model.generate_content(prompt).text
        else:
            # DeepSeek / OpenAI
            target_url = (base_url.rstrip('/') + "/chat/completions")
            payload = {"model": user_model, "messages": [{"role": "user", "content": prompt}], "stream": False}
            headers = {"Authorization": f"Bearer {user_key}", "Content-Type": "application/json"}
            resp = requests.post(target_url, json=payload, headers=headers, timeout=60)
            if resp.status_code != 200: return jsonify({"error": resp.text}), 400
            trans_text = resp.json()['choices'][0]['message']['content']

        # 保存结果
        chapter_data['translation'] = trans_text
        with open(file_path, 'w', encoding='utf-8') as f: json.dump(chapter_data, f, ensure_ascii=False, indent=2)

        return jsonify({"content": trans_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
