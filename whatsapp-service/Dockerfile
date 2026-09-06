FROM node:22-slim

WORKDIR /app

# Default image is mock-capable and lightweight: skip optional deps so the huge
# @open-wa/wa-automate (Puppeteer/Chromium) isn't pulled. For a LIVE WhatsApp
# image, drop `--omit=optional`, add the Chromium runtime libs, and run with
# WHATSAPP_MOCK unset.
COPY package.json ./
RUN npm install --omit=dev --omit=optional

COPY . .

EXPOSE 3100
CMD ["node", "src/index.js"]
