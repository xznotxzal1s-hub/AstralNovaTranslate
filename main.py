import os
import time
import random
from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

app = Flask(__name__)

# 获取环境变量里的 Key
DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# 伪装头 (更强力版)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Referer': 'https://syosetu.com/',
    'Cookie': 'over18=yes; sas_c=1' # 加上这个 Cookie 可以绕过部分年龄验证
}

html_code = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌸 姐姐的轻小说翻译机 V3</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #fdf2f8; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 25px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { color: #db2777; text-align: center; }
        input { width: 100%; padding: 14px; border: 2px solid #fbcfe8; border-radius: 12px; margin-bottom: 15px; box-sizing: border-box; font-size: 16px; }
        button { width: 100%; background: #db2777; color: white; border: none; padding: 16px; border-radius: 12px; font-size: 17px; font-weight: bold; cursor: pointer; }
        button:disabled { background: #f9a8d4; }
        #result { margin-top: 30px; line-height: 1.8; font-size: 17px; color: #1f2937; }
        .error { color: #dc2626; background: #fee2e2; padding: 15px; border-radius: 10px; border: 1px solid #fecaca; }
        .loading { text-align: center; color: #db2777; display: none; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌸 轻小说翻译机 V3</h1>
        <input type="text" id="urlInput" placeholder="🔗 粘贴小说链接 (syosetu.com)...">
        <button onclick="startTranslate()" id="btn">开始魔法翻译 ✨</button>
        <div id="loading" class="loading">⏳ 正在突破结界抓取中...</div>
        <div id="result"></div>
    </div>
    <script>
        async function startTranslate() {
            const url = document.getElementById('urlInput').value;
            const btn = document.getElementById('btn');
            const loading = document.getElementById('loading');
            const result = document.getElementById('result');
            
            if (!url) return;
            btn.disabled = true; loading.style.display = 'block'; result.innerText = '';

            try {
                const response = await fetch('/translate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ url: url })
                });
                const data = await response.json();
                
                if (data.error) {
                    result.innerHTML = `<div class="error"><b>😭 抓取失败啦</b><br>${data.error}</div>`;
                } else {
                    result.innerHTML = `<h3>${data.title}</h3><hr>${data.content}`;
                }
            } catch (e) {
                result.innerHTML = `<div class="error">网络链接错误: ${e}</div>`;
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
    user_key = DEFAULT_GEMINI_KEY

    if not user_key:
        return jsonify({"error": "请检查 NAS 环境变量是否填了 GEMINI_API_KEY"}), 400

    try:
        # 1. 尝试抓取网页 (增加重试机制)
        resp = None
        for i in range(2): # 试2次
            try:
                # verify=False 有时候能解决 SSL 握手失败的问题
                resp = requests.get(url, headers=HEADERS, timeout=15) 
                if resp.status_code == 200:
                    break
            except Exception as e:
                print(f"Attempt {i+1} failed: {e}")
                time.sleep(1)
        
        # 检查是否真的请求成功
        if not resp:
            return jsonify({"error": "连接超时，无法连接到日本网站 (请检查 NAS 网络或是否需要代理)"}), 500
            
        if resp.status_code != 200:
            return jsonify({"error": f"网站拒绝了访问 (状态码: {resp.status_code})。<br>可能是 IP 被暂时封禁或触发了防火墙。"}), 400

        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 2. 提取正文 (增强版选择器)
        content_div = soup.find(id="novel_honbun") or \
                      soup.find(class_="novel_view") or \
                      soup.find("div", class_="entry-content") or \
                      soup.find(id="content")

        title = soup.find('title').text if soup.find('title') else "无标题"

        if not content_div:
            # 调试：如果没有找到正文，看看页面到底返回了什么 (取前100个字)
            debug_text = soup.get_text()[:200].replace("\n", " ")
            return jsonify({"error": f"成功连上了网站，但没找到小说正文。<br>页面可能显示为：{debug_text}..."}), 400

        raw_text = content_div.get_text(separator="\n")

        # 3. AI 翻译
        genai.configure(api_key=user_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"你是一位轻小说翻译家。请翻译以下日语片段为中文：\n\n{raw_text[:8000]}"
        
        chat_resp = model.generate_content(prompt)
        return jsonify({"title": title, "content": chat_resp.text})

    except Exception as e:
        return jsonify({"error": f"程序内部错误: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
