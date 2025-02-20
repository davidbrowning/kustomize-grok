FROM python:3.9-slim

# Install dependencies
RUN pip install pyyaml

# Copy the tool
COPY my_tool.py /app/my_tool.py

# Set working directory
WORKDIR /app

# Make the script executable
RUN chmod +x my_tool.py

# Entry point
ENTRYPOINT ["python", "kustomize-grok.py"]