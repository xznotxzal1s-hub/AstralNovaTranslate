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

# 伪装头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Referer': 'https://syosetu.com/',
    'Cookie': 'over18=yes; sas_view=1; sas_c=1'
}

# ================= 核心逻辑：智能抓取 & 文件处理 =================
def intelligent_extract(soup):
    """智能提取正文 (保留 V6 暴力比对算法)"""
    candidates = []
    selectors = ["#novel_honbun", ".novel_view", ".entry-content", "#content", ".p-novel__body", ".js-novel-text", "article"]
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator="\n")
            if len(text) > 200: candidates.append(text)

    all_divs = soup.find_all("div")
    if all_divs:
        sorted_divs = sorted(all_divs, key=lambda d: len(d.get_text()), reverse=True)[:3]
        for div in sorted_divs:
            text = div.get_text(separator="\n")
            if len(text) > 200: candidates.append(text)

    if not candidates:
        body_text = soup.body.get_text(separator="\n") if soup.body else ""
        return body_text if len(body_text) > 100 else None
    return max(candidates, key=len)

def save_chapter(novel_id, chapter_index, title, content):
    """保存章节"""
    chapter_dir = os.path.join(NOVELS_DIR, novel_id, "chapters")
    if not os.path.exists(chapter_dir): os.makedirs(chapter_dir)
    
    data = {"index": chapter_index, "title": title, "content": content, "translation": ""}
    file_path = os.path.join(chapter_dir, f"{chapter_index}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            if old_data.get('translation'): data['translation'] = old_data['translation']

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def create_novel_meta(novel_name, source_type):
    """创建元数据"""
    novel_id = re.sub(r'[^\w\-_]', '', novel_name)[:50] 
    if not novel_id: novel_id = "novel_" + str(int(time.time()))
    novel_dir = os.path.join(NOVELS_DIR, novel_id)
    if not os.path.exists(novel_dir): os.makedirs(novel_dir)
    meta = {"title": novel_name, "type": source_type, "created_at": time.time()}
    with open(os.path.join(novel_dir, "meta.json"), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    return novel_id

def process_url_import(url):
    """处理 URL 导入"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, 'html.parser')
    title = soup.find('title').text.strip() if soup.find('title') else "网页抓取_" + str(int(time.time()))
    content = intelligent_extract(soup)
    if not content: raise Exception("无法提取网页正文")
    novel_id = create_novel_meta(title, "web")
    save_chapter(novel_id, 1, title, content)
    return novel_id

def process_txt(file_path, novel_name):
    """处理 TXT"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: text = f.read()
    novel_id = create_novel_meta(novel_name, "txt")
    chunk_size = 3000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    for i, chunk in enumerate(chunks):
        save_chapter(novel_id, i+1, f"第 {i+1} 部分", chunk)
    return novel_id

def process_epub(file_path, novel_name):
    """处理 EPUB"""
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

# ================= 前端 HTML (V9：带记忆功能的设置面板) =================
html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌸 姐姐的轻小说书架 V9</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #fff1f2; padding: 20px; color: #333; max-width: 1000px; margin: 0 auto; }
        .card { background: white; padding: 25px; border-radius: 16px; box-shadow: 0 4px 15px rgba(219,39,119,0.08); margin-bottom: 25px; }
        h1, h2 { color: #db2777; text-align: center; margin-top: 0; }
        .btn { background: #db2777; color: white; border: none; padding: 12px 24px; border-radius: 10px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 500; font-size: 15px; transition: 0.2s; }
        .btn:hover { background: #be185d; transform: translateY(-1px); }
        .btn:disabled { background: #fbcfe8; cursor: wait; }
        .btn-outline { background: white; border: 2px solid #db2777; color: #db2777; }
        
        input[type="text"], select, input[type="password"] { width: 100%; padding: 12px; border: 1px solid #fbcfe8; border-radius: 8px; box-sizing: border-box; margin-top: 5px; font-size: 14px; }
        
        .bookshelf { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 20px; margin-top: 30px; }
        .book-item { background: #fdf2f8; padding: 20px; border-radius: 12px; text-align: center; cursor: pointer; border: 2px solid transparent; transition: 0.2s; }
        .book-item:hover { border-color: #db2777; background: #fff; transform: translateY(-5px); box-shadow: 0 5px 15px rgba(219,39,119,0.1); }
        
        /* 阅读页 */
        .reader-container { display: flex; gap: 25px; flex-wrap: wrap; margin-top: 20px; }
        .text-box { flex: 1; min-width: 320px; background: #fafafa; padding: 25px; border-radius: 12px; line-height: 1.8; white-space: pre-wrap; height: 75vh; overflow-y: auto; border: 1px solid #eee; font-size: 17px; }
        .trans-box { background: #fff; border: 2px solid #fbcfe8; }
        
        /* 设置面板 */
        .settings-box { background: #fff1f2; border: 2px dashed #fbcfe8; border-radius: 12px; padding: 15px; margin-bottom: 20px; }
        .settings-summary { font-weight: bold; color: #be185d; cursor: pointer; }
        .settings-content { margin-top: 15px; display: grid; gap: 15px; }
    </style>
</head>
<body>

    {% if page == 'home' %}
    <div class="card">
        <h1>📚 姐姐的云端书架</h1>
        
        <div style="background: #fdf2f8; padding: 20px; border-radius: 12px; margin-bottom: 30px;">
            <div style="display:flex; gap:10px; margin-bottom:15px;">
                <input type="text" id="urlInput" placeholder="🔗 粘贴小说网页链接...">
                <button class="btn" onclick="importUrl()">抓取</button>
            </div>
            <div style="text-align:center;">
                <label for="fileInput" class="btn btn-outline" style="width:100%; box-sizing:border-box; cursor:pointer;">📂 上传 TXT / EPUB 文件</label>
                <input type="file" id="fileInput" accept=".txt,.epub" style="display:none" onchange="uploadFile()">
            </div>
            <div id="importStatus" style="text-align:center; margin-top:10px; color:#db2777;"></div>
        </div>

        <div class="bookshelf">
            {% for book in books %}
            <div class="book-item" onclick="window.location.href='/novel/{{ book.id }}'">
                <div style="font-size:40px; margin-bottom:10px;">{% if book.type=='web' %}🌐{% elif book.type=='epub' %}📘{% else %}📄{% endif %}</div>
                <div style="font-weight:bold; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{{ book.title }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <script>
        async function importUrl() {
            const url = document.getElementById('urlInput').value;
            if(!url) return;
            document.getElementById('importStatus').innerText = "⏳ 正在抓取...";
            try {
                const res = await fetch('/import_url', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})});
                const data = await res.json();
                if(data.id) window.location.href = "/novel/" + data.id;
                else throw new Error(data.error);
            } catch(e) { alert("失败: "+e); document.getElementById('importStatus').innerText=""; }
        }
        async function uploadFile() {
            const file = document.getElementById('fileInput').files[0];
            if(!file) return;
            const formData = new FormData();
            formData.append('file', file);
            document.getElementById('importStatus').innerText = "⏳ 正在上传...";
            try {
                const res = await fetch('/upload', {method:'POST', body:formData});
                if(res.ok) window.location.reload();
                else alert("上传失败");
            } catch(e) { alert("错误: "+e); }
        }
    </script>

    {% elif page == 'novel' %}
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <a href="/" class="btn btn-outline">⬅ 返回</a>
            <h2>{{ novel_title }}</h2>
        </div>
        <div style="display:grid; gap:10px;">
            {% for ch in chapters %}
            <a href="/read/{{ novel_id }}/{{ ch.index }}" style="padding:15px; background:#fafafa; border-radius:8px; display:flex; justify-content:space-between; text-decoration:none; color:#333;">
                <span>{{ ch.title }}</span>
                <span style="font-size:12px; color:{% if ch.has_trans %}#059669{% else %}#888{% endif %}">{% if ch.has_trans %}✅ 已译{% else %}未读{% endif %}</span>
            </a>
            {% endfor %}
        </div>
    </div>

    {% elif page == 'read' %}
    <div class="card">
        <div style="display:flex; justify-content:space-between; margin-bottom:20px;">
            <a href="/novel/{{ novel_id }}" class="btn btn-outline">⬅ 目录</a>
            {% if next_index %}
            <a href="/read/{{ novel_id }}/{{ next_index }}" class="btn btn-outline">下一章 ➡</a>
            {% endif %}
        </div>

        <details class="settings-box">
            <summary class="settings-summary">⚙️ AI 模型设置 (自动记忆)</summary>
            <div class="settings-content">
                <div>
                    <label>服务商：</label>
                    <select id="provider" onchange="updateDefaults()">
                        <option value="gemini">Google Gemini</option>
                        <option value="deepseek">DeepSeek / OpenAI</option>
                    </select>
                </div>
                <div>
                    <label>模型 (可手动输入)：</label>
                    <input type="text" id="modelName" value="gemini-1.5-flash" list="model_list">
                    <datalist id="model_list">
                        <option value="gemini-1.5-flash">Gemini 1.5 Flash (快)</option>
                        <option value="gemini-1.5-pro">Gemini 1.5 Pro (强)</option>
                        <option value="deepseek-chat">DeepSeek V3</option>
                        <option value="gpt-4o">GPT-4o</option>
                    </datalist>
                </div>
                <div>
                    <label>API Key：</label>
                    <input type="password" id="customKey" placeholder="自动保存，下次不用填">
                </div>
                <div id="baseUrlGroup" style="display:none;">
                    <label>Base URL：</label>
                    <input type="text" id="baseUrl" value="https://api.deepseek.com">
                </div>
                <div style="text-align:right;">
                    <button class="btn btn-outline" style="padding:5px 10px; font-size:12px;" onclick="saveSettings()">💾 强制保存设置</button>
                </div>
            </div>
        </details>

        <button id="transBtn" class="btn" style="width:100%; margin-bottom:20px;" onclick="translateChapter()">✨ 开始魔法翻译</button>

        <div class="reader-container">
            <div class="text-box">{{ content }}</div>
            <div class="text-box trans-box" id="transText">
                {% if translation %}
                    {{ translation }}
                {% else %}
                    <div style="color:#aaa; text-align:center; margin-top:50px;">点击翻译按钮...</div>
                {% endif %}
            </div>
        </div>
    </div>
    
    <input type="hidden" id="novelId" value="{{ novel_id }}">
    <input type="hidden" id="chapterIndex" value="{{ chapter_index }}">

    <script>
        // 页面加载时恢复设置
        window.onload = function() {
            const savedProvider = localStorage.getItem('novel_provider');
            if (savedProvider) {
                document.getElementById('provider').value = savedProvider;
                document.getElementById('modelName').value = localStorage.getItem('novel_model') || 'gemini-1.5-flash';
                document.getElementById('customKey').value = localStorage.getItem('novel_key') || '';
                document.getElementById('baseUrl').value = localStorage.getItem('novel_baseurl') || '';
                updateDefaults(); // 刷新UI状态
            }
        };

        function saveSettings() {
            localStorage.setItem('novel_provider', document.getElementById('provider').value);
            localStorage.setItem('novel_model', document.getElementById('modelName').value);
            localStorage.setItem('novel_key', document.getElementById('customKey').value);
            localStorage.setItem('novel_baseurl', document.getElementById('baseUrl').value);
            alert("设置已保存！下次打开会自动填好。");
        }

        function updateDefaults() {
            const p = document.getElementById('provider').value;
            const u = document.getElementById('baseUrlGroup');
            if (p === 'gemini') u.style.display = 'none';
            else u.style.display = 'block';
        }

        async function translateChapter() {
            // 翻译前自动保存一次设置
            const provider = document.getElementById('provider').value;
            const model = document.getElementById('modelName').value;
            const key = document.getElementById('customKey').value;
            const baseUrl = document.getElementById('baseUrl').value;
            
            localStorage.setItem('novel_provider', provider);
            localStorage.setItem('novel_model', model);
            localStorage.setItem('novel_key', key);
            localStorage.setItem('novel_baseurl', baseUrl);

            const btn = document.getElementById('transBtn');
            const box = document.getElementById('transText');
            btn.disabled = true; btn.innerText = "⏳ 翻译中...";
            
            try {
                const res = await fetch('/translate_api', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        novel_id: document.getElementById('novelId').value,
                        chapter_index: document.getElementById('chapterIndex').value,
                        provider, model, api_key: key, base_url: baseUrl
                    })
                });
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                box.innerText = data.content;
                btn.innerText = "✅ 翻译完成";
            } catch(e) {
                box.innerText = "错误: " + e;
                btn.innerText = "重试";
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
        temp_path = os.path.join("/tmp", file.filename)
        file.save(temp_path)
        name = os.path.splitext(file.filename)[0]
        ext = os.path.splitext(file.filename)[1].lower()
        if ext == '.txt': process_txt(temp_path, name)
        elif ext == '.epub': process_epub(temp_path, name)
        os.remove(temp_path)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/novel/<novel_id>')
def view_novel(novel_id):
    meta_path = os.path.join(NOVELS_DIR, novel_id, "meta.json")
    if not os.path.exists(meta_path): return "Not found", 404
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
    
    # 获取设置
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
        prompt = f"你是一位轻小说翻译家。请翻译以下日语片段为中文，保留小说感和沉浸感：\n\n{text[:12000]}"
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

        # 保存翻译
        chapter_data['translation'] = trans_text
        with open(file_path, 'w', encoding='utf-8') as f: json.dump(chapter_data, f, ensure_ascii=False, indent=2)

        return jsonify({"content": trans_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
