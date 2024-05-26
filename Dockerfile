# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install Tesseract-OCR and other necessary packages
RUN apt-get update && \
    apt-get install -y tesseract-ocr libtesseract-dev libleptonica-dev pkg-config wget && \
    apt-get clean

# Download additional language data files for Tesseract
RUN wget -P /usr/share/tesseract-ocr/4.00/tessdata/ \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata && \
    wget -P /usr/share/tesseract-ocr/4.00/tessdata/ \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/hin.traineddata && \
    wget -P /usr/share/tesseract-ocr/4.00/tessdata/ \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/urd.traineddata

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install the Python packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Define environment variable
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# Run ocr_script.py when the container launches
CMD ["python", "video_ocr_service.py"]
