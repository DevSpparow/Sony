
FROM nikolaik/python-nodejs:python3.11-nodejs20

# Install FFmpeg + required system deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       git \
       wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version

COPY . /app/
WORKDIR /app/
RUN pip3 install --no-cache-dir -U -r requirements.txt

CMD bash start
