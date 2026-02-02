# Use a lightweight Python base
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install the required libraries (Flask for the web, Requests for Spoolman)
RUN pip install flask requests

# Copy all files from your folder into the container
COPY . /app

# Expose the port we are using
EXPOSE 8000

# The new command to start the server (pointing to the NEW file)
CMD ["python", "app.py"]