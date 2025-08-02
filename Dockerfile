# Use Xuanyuan's Python 3.11 image
FROM docker.xuanyuan.me/python:3.11-alpine

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 240 -r requirements.txt 


# Set default command to run eval.py
CMD ["python", "eval.py"]
