# Buy Setup - Backend

API FastAPI qui fait tout le travail cote serveur : import des factures
Buyee (via Scrapling), calcul du prix de revient (douane France + TVA),
strategie d'enchere WhatNot, generation de la fiche produit PDF, et suivi
des ventes multi-plateformes.

## Installation

```bash
cd backend
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
scrapling install   # installe le navigateur headless utilise par Scrapling
```

## Lancer le serveur

```bash
uvicorn app.main:app --reload --port 8000
```

L'API est alors disponible sur http://localhost:8000, et la doc interactive
(Swagger) sur http://localhost:8000/docs.

## Important - le scraper Buyee

`app/buyee_scraper.py` contient le flux de connexion + extraction des
factures. Les selecteurs CSS utilises sont des estimations car ils n'ont
pas pu etre verifies contre un compte reel. **Avant la premiere utilisation
reelle**, il faudra probablement ajuster `LOGIN_SELECTORS`,
`ORDER_LIST_SELECTORS` et `INVOICE_SELECTORS` en inspectant les pages de ton
compte Buyee (F12 dans le navigateur -> clic droit sur l'element -> Inspecter
-> clic droit sur le HTML surligne -> "Copier le selecteur"). Le fichier
contient un guide detaille en commentaire en haut.

En attendant, utilise `/invoices/demo` (bouton "Charger des donnees de
demo" dans l'interface) pour tester tout le reste de l'appli (calculs,
fiche PDF, suivi des ventes) avec des articles d'exemple.

## Securite des identifiants Buyee

Tes identifiants Buyee ne sont jamais stockes : ils sont envoyes une seule
fois vers `/invoices/import`, utilises en memoire pour la duree de la
connexion, puis jetes. Rien n'est ecrit sur le disque ni dans les logs.

## Taux de douane

Modifiables dans l'interface (page Reglages) ou directement dans
`app/config/customs_rates.json`. Les valeurs par defaut sont indicatives ;
verifie le taux exact applicable a chaque type d'article sur le simulateur
officiel des douanes francaises avant de t'y fier pour une declaration
reelle.
