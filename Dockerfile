# PDFim web sürümü — docker build -t pdfim . && docker run -p 8000:8000 pdfim
FROM python:3.12-slim

# Metin yazarken gömülecek fontlar (Türkçe karakterler dahil). Microsoft fontları dağıtılamaz;
# aynı harf genişliklerindeki açık karşılıkları: Liberation (Arial/Times/Courier),
# Carlito (Calibri), Caladea (Cambria) — datasheet'te değer değişince hizalar kaymasın.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fontconfig fonts-liberation fonts-dejavu-core \
      fonts-crosextra-carlito fonts-crosextra-caladea \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY bridge.py editor.py fonts.py page_server.py server.py ./
COPY ui ./ui

# Yüklenen PDF'ler yabancı girdi: root olmayan kullanıcı, yazılabilir tek yer veri klasörü
RUN useradd --system --uid 10001 pdfim && mkdir -p /data && chown pdfim /data
USER pdfim
ENV PDFIM_DATA_DIR=/data PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ui/index.html')"

# Tek süreç: oturumlar (açık belgeler) bellekte tutulur, süreçler arasında paylaşılmaz.
# --proxy-headers: Coolify/Traefik arkasında gerçek şema (https) ve istemci IP'si.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
