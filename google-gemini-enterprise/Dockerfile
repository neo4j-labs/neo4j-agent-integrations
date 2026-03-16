# Use the official, lightweight Python 3.11 slim image
FROM python:3.11-slim

# Force Python logs to show up immediately in Cloud Logging
ENV PYTHONUNBUFFERED=True

# Create a dedicated, non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set the working directory inside the container
WORKDIR /app

# Copy the dependencies file first to leverage Docker layer caching
COPY requirements.txt .

# Install the dependencies without storing cache to keep the image small
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY app/ ./app
COPY main.py .

# Change ownership of the working directory to our non-root user
RUN chown -R appuser:appuser /app

# Explicitly switch to the non-root user before running the application
USER appuser

# Expose port 8080 (the default port expected by Google Cloud Run)
EXPOSE 8080

# Start the FastAPI server using Uvicorn on port 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]