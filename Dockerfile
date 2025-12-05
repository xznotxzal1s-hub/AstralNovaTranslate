# 使用轻量级的 Python 环境
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装必要的库 (就是我们在 Replit 里装的那些积木)
RUN pip install flask requests beautifulsoup4 google-generativeai

# 把当前目录下的文件都复制进去
COPY . .

# 告诉外界我们要用 8080 端口
EXPOSE 8080

# 启动命令
CMD ["python", "main.py"]
