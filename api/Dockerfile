#Using official Python image
FROM python:3.10-slim

#Set workdir
WORKDIR /app

#Install system dependencies
RUN apt-get update && apt-get install -y build-essential

#Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copy the rest of the backend code
COPY . .

#Expose port
EXPOSE 8000

#Run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]