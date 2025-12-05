import os
from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# ================= 配置区域 =================
# 姐姐提示：把这里换成你刚才复制的那个 AIza 开头的 API Key
my_api_key = os.environ.get("GEMINI_API_KEY", "这里填入你的API Key") 
# ===========================================

# 初始化 AI
genai.configure(api_key=my_api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

app = Flask(__name__)

# 这是我们的前端界面代码（HTML），为了方便你，我直接写在这里了
html_code = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>🌸 姐姐的轻小说翻译机</title>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; background: #fdf2f8; padding: 20px; color: #333; }
        .container { max-width: 600px; mx-auto; background: white; padding: 20px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin: 0 auto; }
        h1 { color: #db2777; text-align: center; font-size: 1.5rem; margin-bottom: 20px; }
        input { width: 100%; padding: 12px; border: 2px solid #fbcfe8; border-radius: 10px; margin-bottom: 10px; box-sizing: border-box; font-size: 16px; outline: none; }
        input:focus { border-color: #db2777; }
        button { width: 100%; background: #db2777; color: white; border: none; padding: 15px; border-radius: 10px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.2s; }
        button:active { transform: scale(0.98); }
        button:disabled { background: #f9a8d4; }
        #result { margin-top: 20px; line-height: 1.8; white-space: pre-wrap; font-size: 17px; }
        .loading { text-align: center; color: #888; display: none; }
        .tip { font-size: 12px; color: #666; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌸 轻小说 AI 翻译机</h1>
        <input type="text" id="urlInput" placeholder="请粘贴日本小说的链接 (例如 syosetu.com)...">
        <button onclick="startTranslate()" id="btn">开始魔法翻译 ✨</button>
        <p class="tip">第一次加载可能比较慢，请耐心等待姐姐翻译哦~</p>
        
        <div id="loading" class="loading">正在努力抓取并翻译中... (约需10-20秒)</div>
        <div id="result"></div>
    </div>

    <script>
        async function startTranslate() {
            const url = document.getElementById('urlInput').value;
            const btn = document.getElementById('btn');
            const loading = document.getElementById('loading');
            const result = document.getElementById('result');

            if (!url) { alert('要把链接告诉姐姐才行哦！'); return; }

            btn.disabled = true;
            loading.style.display = 'block';
            result.innerText = '';

            try {
                const response = await fetch('/translate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url})
                });
                const data = await response.json();
                
                if (data.error) {
                    result.innerText = "出错了呜呜呜：" + data.error;
                } else {
                    result.innerHTML = `<h3>${data.title}</h3><hr>${data.content}`;
                }
            } catch (e) {
                result.innerText = "网络好像有点问题，请重试一下吧~";
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
    
    try:
        # 1. 伪装浏览器去抓取网页
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers)
        response.encoding = response.apparent_encoding # 自动识别编码
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 简单粗暴地找正文：大部分小说网站正文都在 id="novel_honbun" 里
        # 如果是其他网站，可能需要调整这里，但先适配“成为小说家吧”
        content_div = soup.find(id="novel_honbun") or soup.find(class_="novel_view") or soup.find("div", class_="entry-content")
        title = soup.find('title').text
        
        if not content_div:
            return jsonify({"error": "哎呀，姐姐没找到正文在哪，可能这个网站结构比较特殊。"}), 400
            
        raw_text = content_div.get_text(separator="\n")
        
        # 2. 发给 Gemini 翻译
        prompt = f"""
        你是一位精通中日文化的轻小说翻译家。请将以下日语小说片段翻译成流畅、优美且符合中文轻小说阅读习惯的中文（保留二次元语感）。
        只输出翻译后的中文，不要输出任何其他解释。
        
        原文：
        {raw_text[:10000]} 
        """ 
        # 限制前10000字防止太长报错
        
        chat_response = model.generate_content(prompt)
        translated_text = chat_response.text
        
        return jsonify({"title": title, "content": translated_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
