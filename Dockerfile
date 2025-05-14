# Use official Python 3.11 image
FROM docker.1ms.run/python:3.11.12-alpine

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 240 -r requirements.txt 


# Set default command to run eval.py
CMD ["python", "eval.py"]
