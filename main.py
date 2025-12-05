import os
import time
from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

app = Flask(__name__)

# 获取环境变量里的默认 Key (你在 NAS 里填的那个)
DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# 前端 HTML 代码 (威力加强版 UI)
html_code = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>🌸 姐姐的轻小说翻译机 Pro</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #fdf2f8; padding: 20px; color: #333; margin: 0; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 25px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { color: #db2777; text-align: center; margin-bottom: 25px; font-size: 1.6rem; }
        
        /* 设置区域样式 */
        .settings-box { background: #fff1f2; border: 2px dashed #fbcfe8; border-radius: 15px; padding: 15px; margin-bottom: 20px; }
        .settings-title { font-weight: bold; color: #be185d; margin-bottom: 10px; display: flex; align-items: center; cursor: pointer; }
        .settings-content { display: none; margin-top: 10px; }
        .settings-content.show { display: block; }
        
        .form-group { margin-bottom: 12px; }
        label { display: block; font-size: 0.9rem; color: #831843; margin-bottom: 4px; font-weight: 500; }
        input, select { width: 100%; padding: 10px; border: 1px solid #fbcfe8; border-radius: 8px; box-sizing: border-box; font-size: 14px; outline: none; }
        input:focus, select:focus { border-color: #db2777; ring: 2px solid #fce7f3; }
        
        /* 主操作区 */
        .main-input { margin-bottom: 20px; }
        .url-input { border: 2px solid #db2777; padding: 14px; font-size: 16px; border-radius: 12px; }
        
        button { width: 100%; background: #db2777; color: white; border: none; padding: 16px; border-radius: 12px; font-size: 17px; font-weight: bold; cursor: pointer; transition: 0.2s; box-shadow: 0 4px 6px rgba(219, 39, 119, 0.2); }
        button:active { transform: scale(0.98); }
        button:disabled { background: #f9a8d4; cursor: not-allowed; }
        
        #result { margin-top: 30px; line-height: 1.8; white-space: pre-wrap; font-size: 17px; color: #1f2937; }
        .loading { text-align: center; color: #db2777; display: none; margin-top: 20px; font-weight: bold; }
        
        .toggle-icon { margin-right: 5px; transition: transform 0.3s; }
        .rotate { transform: rotate(90deg); }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌸 轻小说翻译机 Pro</h1>
        
        <div class="settings-box">
            <div class="settings-title" onclick="toggleSettings()">
                <span class="toggle-icon">⚙️</span> 翻译模型设置 (点我展开)
            </div>
            <div class="settings-content" id="settingsContent">
                <div class="form-group">
                    <label>选择 AI 服务商：</label>
                    <select id="provider" onchange="updateDefaults()">
                        <option value="gemini">Google Gemini (默认)</option>
                        <option value="deepseek">DeepSeek (深度求索)</option>
                        <option value="openai">其他 OpenAI 兼容接口</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label>模型名称 (Model)：</label>
                    <input type="text" id="modelName" value="gemini-1.5-flash" placeholder="例如 gemini-1.5-pro">
                </div>
                
                <div class="form-group">
                    <label>API Key (留空则使用 NAS 预设)：</label>
                    <input type="password" id="customKey" placeholder="想用 DeepSeek 就填 DeepSeek 的 Key">
                </div>
                
                <div class="form-group" id="baseUrlGroup" style="display:none;">
                    <label>API 地址 (Base URL)：</label>
                    <input type="text" id="baseUrl" value="https://api.deepseek.com/v1">
                </div>
            </div>
        </div>

        <div class="main-input">
            <input type="text" class="url-input" id="urlInput" placeholder="🔗 粘贴小说链接 (syosetu.com / kakuyomu 等)...">
        </div>
        
        <button onclick="startTranslate()" id="btn">开始魔法翻译 ✨</button>
        <div id="loading" class="loading">⏳ 正在召唤 AI 娘努力翻译中...</div>
        <div id="result"></div>
    </div>

    <script>
        // 切换设置面板显示
        function toggleSettings() {
            const content = document.getElementById('settingsContent');
            content.classList.toggle('show');
        }

        // 根据服务商自动填入默认值
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
                baseUrlInput.value = 'https://api.deepseek.com/v1'; // DeepSeek 标准地址
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
            
            // 获取设置信息
            const provider = document.getElementById('provider').value;
            const model = document.getElementById('modelName').value;
            const apiKey = document.getElementById('customKey').value;
            const baseUrl = document.getElementById('baseUrl').value;

            if (!url) { alert('要把链接告诉姐姐才行哦！'); return; }

            btn.disabled = true;
            loading.style.display = 'block';
            result.innerText = '';

            try {
                const response = await fetch('/translate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        url: url,
                        provider: provider,
                        model: model,
                        api_key: apiKey,
                        base_url: baseUrl
                    })
                });
                const data = await response.json();
                
                if (data.error) {
                    result.innerText = "出错了呜呜呜：" + data.error;
                } else {
                    result.innerHTML = `<h3>${data.title}</h3><hr>${data.content}`;
                }
            } catch (e) {
                result.innerText = "网络请求失败: " + e;
            } finally {
                btn.disabled = false;
                loading.style.display = 'none';
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
    
    # 获取用户设置，如果没有则使用默认
    provider = data.get('provider', 'gemini')
    user_model = data.get('model', 'gemini-1.5-flash')
    user_key = data.get('api_key') or DEFAULT_GEMINI_KEY # 优先用网页填的，没有就用环境变量
    base_url = data.get('base_url')

    if not user_key:
        return jsonify({"error": "没有找到 API Key！请在设置里填入，或者检查 NAS 环境变量。"}), 400

    try:
        # 1. 抓取小说正文 (和之前一样)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 兼容多个网站的提取逻辑
            content_div = soup.find(id="novel_honbun") or soup.find(class_="novel_view") or soup.find("div", class_="entry-content") or soup.find(id="content")
            title = soup.find('title').text
            
            if not content_div:
                return jsonify({"error": "无法自动提取正文，这个网站可能不支持。"}), 400
            
            raw_text = content_div.get_text(separator="\n")
        except Exception as e:
             return jsonify({"error": f"抓取网页失败: {str(e)}"}), 400

        # 准备 Prompt
        prompt = f"""
        你是一位精通中日文化的轻小说翻译家。请将以下日语小说片段翻译成流畅、优美且符合中文轻小说阅读习惯的中文（保留二次元语感）。
        只输出翻译后的中文，不要输出任何解释或Markdown标记。
        
        原文：
        {raw_text[:12000]} 
        """

        translated_text = ""

        # 2. 根据服务商调用不同的 AI
        if provider == 'gemini':
            # --- 使用 Google Gemini SDK ---
            genai.configure(api_key=user_key)
            # 修正用户可能输入的 2.5 为 1.5 (如果用户真的填了 2.5)
            model_name = user_model.replace("2.5", "1.5") 
            model = genai.GenerativeModel(model_name)
            chat_resp = model.generate_content(prompt)
            translated_text = chat_resp.text

        else:
            # --- 使用 OpenAI 兼容模式 (DeepSeek 等) ---
            # 如果是 DeepSeek，必须确保 URL 正确
            target_url = base_url.rstrip('/') + "/chat/completions"
            
            payload = {
                "model": user_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
            
            api_headers = {
                "Authorization": f"Bearer {user_key}",
                "Content-Type": "application/json"
            }
            
            ai_resp = requests.post(target_url, json=payload, headers=api_headers, timeout=60)
            
            if ai_resp.status_code != 200:
                return jsonify({"error": f"AI 服务商报错: {ai_resp.text}"}), 400
                
            ai_data = ai_resp.json()
            translated_text = ai_data['choices'][0]['message']['content']

        return jsonify({"title": title, "content": translated_text})

    except Exception as e:
        return jsonify({"error": f"翻译过程出错: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
