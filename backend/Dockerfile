# Image officielle Playwright : navigateurs Chromium deja installes avec
# toutes les dependances systeme necessaires (indispensable pour Scrapling,
# qui pilote un vrai navigateur headless pour se connecter a Buyee).
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installe/verifie les navigateurs utilises par Scrapling (les binaires
# Playwright sont deja presents dans l'image de base, cette commande
# complete la configuration propre a Scrapling).
RUN scrapling install || true

COPY app ./app

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
