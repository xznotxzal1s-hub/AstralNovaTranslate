import os
import time
import requests
from flask import Flask, request, jsonify, render_template_string
from bs4 import BeautifulSoup
import google.generativeai as genai

app = Flask(__name__)

# 获取环境变量里的默认 Key
DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# 伪装头 (强力伪装成 Windows 电脑上的 Chrome)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Referer': 'https://syosetu.com/',
    # sas_view=1 表示强制 PC 版，over18=yes 绕过年龄确认
    'Cookie': 'over18=yes; sas_view=1; sas_c=1'
}

# --- 智能提取核心逻辑 ---
def intelligent_extract(soup):
    """
    找不到 ID 时，自动寻找字数最多的 div 块
    """
    # 1. 优先尝试已知的标准 ID (Syosetu, Kakuyomu 等)
    selectors = ["#novel_honbun", ".novel_view", ".entry-content", "#content", ".p-novel__body", ".js-novel-text"]
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            return element.get_text(separator="\n")
    
    # 2. 备用方案：寻找网页里含有最多文字的 div 标签
    # (原理：小说页面的正文通常是整个网页里字数最多的那一块)
    all_divs = soup.find_all("div")
    if not all_divs:
        return None
    
    # 找字数最多的 div
    largest_div = max(all_divs, key=lambda d: len(d.get_text()))
    
    # 如果字数太少（小于200字），说明可能抓到了菜单栏，不算成功
    if len(largest_div.get_text()) < 200:
        return None
        
    return largest_div.get_text(separator="\n")

html_code = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌸 姐姐的轻小说翻译机 V4 (智能版)</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #fff5f7; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 25px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { color: #db2777; text-align: center; font-size: 1.5rem; }
        
        /* 设置区域 */
        .settings-box { background: #fff1f2; border: 2px dashed #fbcfe8; border-radius: 12px; padding: 15px; margin-bottom: 20px; }
        .settings-summary { font-weight: bold; color: #be185d; cursor: pointer; list-style: none; }
        .settings-content { margin-top: 10px; }
        
        label { display: block; font-size: 0.9rem; color: #831843; margin-top: 10px; }
        input, select { width: 100%; padding: 10px; border: 1px solid #fbcfe8; border-radius: 8px; margin-top: 5px; box-sizing: border-box; }
        
        .main-input { border: 2px solid #db2777; padding: 12px; border-radius: 10px; font-size: 16px; margin-bottom: 15px; }
        button { width: 100%; background: #db2777; color: white; border: none; padding: 15px; border-radius: 10px; font-size: 16px; font-weight: bold; cursor: pointer; }
        button:disabled { background: #f9a8d4; cursor: wait; }
        
        #result { margin-top: 25px; line-height: 1.8; white-space: pre-wrap; color: #1f2937; font-size: 17px; }
        .error-box { background: #fee2e2; color: #b91c1c; padding: 15px; border-radius: 10px; border: 1px solid #fca5a5; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌸 轻小说翻译机 V4 (智能版)</h1>
        
        <details class="settings-box">
            <summary class="settings-summary">⚙️ 模型与设置 (点击展开)</summary>
            <div class="settings-content">
                <label>选择 AI 服务商：</label>
                <select id="provider" onchange="updateDefaults()">
                    <option value="gemini">Google Gemini (默认)</option>
                    <option value="deepseek">DeepSeek (性价比之王)</option>
                    <option value="openai">OpenAI / 兼容接口</option>
                </select>
                
                <label>模型名称 (Model)：</label>
                <input type="text" id="modelName" value="gemini-1.5-flash">
                
                <label>API Key (留空使用默认)：</label>
                <input type="password" id="customKey" placeholder="如用 DeepSeek 请在此填入 sk-...">
                
                <div id="baseUrlGroup" style="display:none;">
                    <label>Base URL (仅 OpenAI/DeepSeek 需要)：</label>
                    <input type="text" id="baseUrl" value="https://api.deepseek.com/v1">
                </div>
            </div>
        </details>

        <input type="text" class="main-input" id="urlInput" placeholder="🔗 粘贴小说链接 (例如 ncode.syosetu.com)...">
        <button onclick="startTranslate()" id="btn">开始魔法翻译 ✨</button>
        <div id="loading" style="display:none; text-align:center; margin-top:15px; color:#db2777;">⏳ 正在智能提取正文并翻译...</div>
        <div id="result"></div>
    </div>

    <script>
        function updateDefaults() {
            const provider = document.getElementById('provider').value;
            const modelInput = document.getElementById('modelName');
            const baseUrlGroup = document.getElementById('baseUrlGroup');
            const baseUrlInput = document.getElementById('baseUrl');

            if (provider === 'gemini') {
                modelInput.value = 'gemini-1.5-flash';
                baseUrlGroup.style.display = 'none';
            } else if (provider === 'deepseek') {
                modelInput.value = 'deepseek-chat';
                baseUrlGroup.style.display = 'block';
                baseUrlInput.value = 'https://api.deepseek.com';
            } else {
                modelInput.value = 'gpt-3.5-turbo';
                baseUrlGroup.style.display = 'block';
                baseUrlInput.value = '';
            }
        }

        async function startTranslate() {
            const url = document.getElementById('urlInput').value;
            const btn = document.getElementById('btn');
            const loading = document.getElementById('loading');
            const result = document.getElementById('result');
            
            // 获取设置
            const provider = document.getElementById('provider').value;
            const model = document.getElementById('modelName').value;
            const apiKey = document.getElementById('customKey').value;
            const baseUrl = document.getElementById('baseUrl').value;

            if (!url) return;
            btn.disabled = true; loading.style.display = 'block'; result.innerText = '';

            try {
                const response = await fetch('/translate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        url, provider, model, api_key: apiKey, base_url: baseUrl
                    })
                });
                const data = await response.json();
                
                if (data.error) {
                    result.innerHTML = `<div class="error-box"><b>🥺 出错了：</b><br>${data.error}</div>`;
                } else {
                    result.innerHTML = `<h3>${data.title}</h3><hr>${data.content}`;
                }
            } catch (e) {
                result.innerHTML = `<div class="error-box">网络错误，请检查 NAS 连接。</div>`;
            } finally {
                btn.disabled = false; loading.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(html_code)

@app.route('/translate', methods=['POST'])
def translate():
    data = request.json
    url = data.get('url')
    
    # 配置 AI
    provider = data.get('provider', 'gemini')
    user_model = data.get('model', 'gemini-1.5-flash')
    user_key = data.get('api_key') or DEFAULT_GEMINI_KEY
    base_url = data.get('base_url')

    if not user_key:
        return jsonify({"error": "没有 API Key！请在网页设置里填入，或者检查 NAS 环境变量。"}), 400

    try:
        # 1. 抓取 (带重试)
        resp = None
        for i in range(2):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200: break
            except: time.sleep(1)
        
        if not resp or resp.status_code != 200:
            return jsonify({"error": "无法连接到小说网站，可能是网络问题或被拦截。"}), 400

        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 2. 智能提取 (关键修改点！)
        title = soup.find('title').text if soup.find('title') else "未命名章节"
        raw_text = intelligent_extract(soup)

        if not raw_text:
            # 调试信息：如果还是抓不到，把网页前200个字返回来看看
            debug_info = soup.get_text()[:200].replace("\n", " ")
            return jsonify({"error": f"已连接网站，但【智能提取】失败。<br>页面似乎是：{debug_info}..."}), 400

        # 3. AI 翻译
        prompt = f"""
        你是一位精通中日文化的轻小说翻译家。请将以下日语小说片段翻译成流畅、优美且符合中文轻小说阅读习惯的中文。
        
        原文片段：
        {raw_text[:10000]} 
        """

        translated_text = ""
        
        if provider == 'gemini':
            genai.configure(api_key=user_key)
            # Gemini 只有 1.5 系列，防止用户填错
            model_name = user_model if "1.5" in user_model else "gemini-1.5-flash"
            model = genai.GenerativeModel(model_name)
            chat_resp = model.generate_content(prompt)
            translated_text = chat_resp.text
        else:
            # DeepSeek / OpenAI 兼容模式
            target_url = (base_url.rstrip('/') + "/chat/completions") if base_url else "https://api.deepseek.com/chat/completions"
            payload = {
                "model": user_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
            headers = {"Authorization": f"Bearer {user_key}", "Content-Type": "application/json"}
            
            ai_resp = requests.post(target_url, json=payload, headers=headers, timeout=60)
            if ai_resp.status_code != 200:
                return jsonify({"error": f"AI 接口报错: {ai_resp.text}"}), 400
            translated_text = ai_resp.json()['choices'][0]['message']['content']

        return jsonify({"title": title, "content": translated_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
