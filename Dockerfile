# Use official Python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Copy only requirements first (caching trick)
COPY requirements.txt .

# Install all dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the bot
COPY . .

# Run the bot
CMD ["python", "bot.py"]
