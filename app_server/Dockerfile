FROM python:3.9-slim
WORKDIR /app

# 1. Copy the text file into the container
COPY requirements.txt .

# 2. Install the libraries listed in that file
RUN pip install -r requirements.txt

# 3. Copy the rest of your code
COPY app.py .

CMD ["python", "app.py"]