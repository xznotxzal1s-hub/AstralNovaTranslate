import os
import time
import requests
from flask import Flask, request, jsonify, render_template_string
from bs4 import BeautifulSoup
import google.generativeai as genai

app = Flask(__name__)

# 默认 Key
DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# 伪装头 (保持强力)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Referer': 'https://syosetu.com/',
    'Cookie': 'over18=yes; sas_view=1; sas_c=1'
}

# --- 🧠 真正的智能提取逻辑 (修复版) ---
def intelligent_extract(soup):
    candidates = []

    # 1. 选手A：尝试标准 ID (Syosetu, Kakuyomu 等)
    selectors = ["#novel_honbun", ".novel_view", ".entry-content", "#content", ".p-novel__body", ".js-novel-text", "article"]
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator="\n")
            # 只有字数超过 200 才算有效候选，防止抓到“请登录”之类的提示
            if len(text) > 200:
                candidates.append(text)

    # 2. 选手B：扫描网页里所有 div，找出字数最多的那个 (暴力兜底)
    all_divs = soup.find_all("div")
    if all_divs:
        # 找出字数最多的前 3 个 div 进行比对
        sorted_divs = sorted(all_divs, key=lambda d: len(d.get_text()), reverse=True)[:3]
        for div in sorted_divs:
            text = div.get_text(separator="\n")
            if len(text) > 200:
                candidates.append(text)

    # 3. 裁判环节：如果没有候选人，或者候选人都太短
    if not candidates:
        # 绝望时刻：直接返回 body 的全部文字（虽然会乱，但比没有强）
        body_text = soup.body.get_text(separator="\n") if soup.body else ""
        return body_text if len(body_text) > 100 else None

    # 4. 冠军诞生：返回字数最多的那个候选内容
    return max(candidates, key=len)

html_code = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌸 姐姐的轻小说翻译机 V6 (修复版)</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #fff5f7; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 25px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { color: #db2777; text-align: center; }
        .settings-box { background: #fff1f2; border: 2px dashed #fbcfe8; border-radius: 12px; padding: 15px; margin-bottom: 20px; }
        .settings-summary { font-weight: bold; color: #be185d; cursor: pointer; }
        .settings-content { margin-top: 10px; }
        label { display: block; font-size: 0.9rem; color: #831843; margin-top: 10px; }
        input, select { width: 100%; padding: 10px; border: 1px solid #fbcfe8; border-radius: 8px; margin-top: 5px; box-sizing: border-box; }
        .main-input { border: 2px solid #db2777; padding: 12px; border-radius: 10px; font-size: 16px; margin-bottom: 15px; width: 100%; box-sizing: border-box; }
        button { width: 100%; background: #db2777; color: white; border: none; padding: 15px; border-radius: 10px; font-size: 16px; font-weight: bold; cursor: pointer; }
        button:disabled { background: #f9a8d4; }
        #result { margin-top: 25px; line-height: 1.8; white-space: pre-wrap; font-size: 17px; }
        .error-box { background: #fee2e2; color: #b91c1c; padding: 15px; border-radius: 10px; }
        .success-info { font-size: 12px; color: #059669; background: #d1fae5; padding: 8px; border-radius: 6px; margin-bottom: 15px; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌸 轻小说翻译机 V6 (修复版)</h1>
        
        <details class="settings-box" open>
            <summary class="settings-summary">⚙️ 模型配置 (点我收起)</summary>
            <div class="settings-content">
                <label>选择 AI 服务商：</label>
                <select id="provider" onchange="updateDefaults()">
                    <option value="gemini">Google Gemini (默认)</option>
                    <option value="deepseek">DeepSeek (深度求索)</option>
                    <option value="openai">OpenAI / 兼容接口</option>
                </select>
                
                <label>模型名称 (Model)：</label>
                <input type="text" id="modelName" value="gemini-1.5-flash" list="model_suggestions" placeholder="输入模型名称...">
                <datalist id="model_suggestions">
                    <option value="gemini-1.5-flash">Gemini 1.5 Flash (推荐)</option>
                    <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
                    <option value="gemini-2.0-flash-exp">Gemini 2.0 (新)</option>
                    <option value="deepseek-chat">DeepSeek V3</option>
                </datalist>
                
                <label>API Key (留空使用 NAS 预设)：</label>
                <input type="password" id="customKey" placeholder="如用 DeepSeek 请在此填入 sk-...">
                
                <div id="baseUrlGroup" style="display:none;">
                    <label>Base URL (仅 OpenAI/DeepSeek 需要)：</label>
                    <input type="text" id="baseUrl" value="https://api.deepseek.com">
                </div>
            </div>
        </details>

        <input type="text" class="main-input" id="urlInput" placeholder="🔗 粘贴小说链接 (例如 syosetu.com)...">
        <button onclick="startTranslate()" id="btn">开始魔法翻译 ✨</button>
        
        <div id="loading" style="display:none; text-align:center; margin-top:15px; color:#db2777;">
            ⏳ 正在暴力提取正文并翻译...<br>
            <span style="font-size:12px; color:#aaa;">(如果不翻译，可能是被墙了，请检查 NAS 网络)</span>
        </div>
        
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
            
            // 获取用户配置
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
                    body: JSON.stringify({ url, provider, model, api_key: apiKey, base_url: baseUrl })
                });
                const data = await response.json();
                
                if (data.error) {
                    result.innerHTML = `<div class="error-box"><b>🥺 出错了：</b><br>${data.error}</div>`;
                } else {
                    result.innerHTML = `
                        <div class="success-info">✅ 成功抓取！原文长度：${data.length} 字</div>
                        <h3>${data.title}</h3><hr>${data.content}
                    `;
                }
            } catch (e) {
                result.innerHTML = `<div class="error-box">网络连接失败，请确保 NAS 能连接外网。</div>`;
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
    provider = data.get('provider', 'gemini')
    user_model = data.get('model', 'gemini-1.5-flash')
    user_key = data.get('api_key') or DEFAULT_GEMINI_KEY
    base_url = data.get('base_url')

    if not user_key:
        return jsonify({"error": "未找到 API Key，请在设置中填入。"}), 400

    try:
        # 1. 抓取网页 (带重试)
        resp = None
        for i in range(2):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200: break
            except: time.sleep(1)
        
        if not resp or resp.status_code != 200:
            return jsonify({"error": "无法连接到小说网站。"}), 400

        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 2. 调用新的逻辑
        title = soup.find('title').text if soup.find('title') else "未命名章节"
        raw_text = intelligent_extract(soup) # 👈 这里调用新的超级函数

        if not raw_text:
            return jsonify({"error": "所有抓取策略都失败了，页面可能真的没有正文。"}), 400

        # 3. AI 翻译
        prompt = f"你是一位轻小说翻译家。请将以下日语小说片段翻译成流畅、优美且符合中文轻小说阅读习惯的中文。\n\n原文：\n{raw_text[:12000]}"
        translated_text = ""
        
        if provider == 'gemini':
            genai.configure(api_key=user_key)
            model = genai.GenerativeModel(user_model) # 自由填模型名
            chat_resp = model.generate_content(prompt)
            translated_text = chat_resp.text
        else:
            # DeepSeek / OpenAI
            target_url = (base_url.rstrip('/') + "/chat/completions")
            payload = {
                "model": user_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
            headers = {"Authorization": f"Bearer {user_key}", "Content-Type": "application/json"}
            ai_resp = requests.post(target_url, json=payload, headers=headers, timeout=60)
            
            if ai_resp.status_code != 200:
                return jsonify({"error": f"AI 报错: {ai_resp.text}"}), 400
            
            ai_data = ai_resp.json()
            if 'choices' in ai_data:
                translated_text = ai_data['choices'][0]['message']['content']
            else:
                return jsonify({"error": f"API 返回未知格式: {ai_data}"}), 400

        return jsonify({"title": title, "content": translated_text, "length": len(raw_text)})

    except Exception as e:
        return jsonify({"error": f"程序内部错误: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
