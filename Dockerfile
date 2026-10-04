# Image de base : Python 3.12 version allegee
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# On copie d'abord requirements.txt : Docker met cette etape en cache
# et ne reinstalle les librairies que si ce fichier change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Bonne pratique de securite : ne pas executer l'appli en administrateur
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Docker verifie regulierement que l'appli repond
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
