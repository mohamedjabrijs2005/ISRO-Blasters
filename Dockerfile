FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port Uvicorn will run on
EXPOSE 10000

# Render dynamically sets PORT environment variable, uvicorn needs to use it.
# We'll default to 10000 if not set.
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-10000}
