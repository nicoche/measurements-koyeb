# Use a lightweight Python base image
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr (ensures logs appear immediately)
ENV PYTHONUNBUFFERED=1

# Create and set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY monitor.py .

# Expose the port Prometheus uses
EXPOSE 7777

# Command to run the script
CMD ["python", "monitor.py"]
