# Buy Setup - refonte complete

Application refaite de zero pour automatiser ton flux d'achat-revente
Japon -> France : import des factures Buyee, calcul du prix de revient
(douane + TVA), aide a la strategie d'enchere WhatNot, fiche produit
telechargeable, et suivi des ventes multi-plateformes.


## Structure du projet

```
buy-setup/
  backend/     API FastAPI (Python) : scraping Buyee (Scrapling), calculs,
               generation de la fiche PDF, stockage des articles/ventes.
  frontend/    Interface web (React + Vite) qui pilote le backend.
```

## Ce que l'appli fait aujourd'hui

1. **Import des factures Buyee** (page "Import factures") : tu entres ton
   identifiant/mot de passe Buyee, l'appli se connecte et recupere pour
   chaque article commande : la photo, le nom, le prix, et le frais de
   port domestique Japon indiques par Buyee.
   - Un bouton "Charger des donnees de demo" permet de tester tout le
     reste de l'appli sans identifiants reels, avec 2 articles d'exemple.
2. **Fiche article** (clique sur un article) : tu indiques le taux de
   change JPY->EUR du jour, le cout de la livraison internationale
   Japon -> France, et la categorie douaniere. L'appli calcule alors :
   - le prix de revient complet (article + port Japon + port France +
     droits de douane + TVA),
   - la strategie d'enchere WhatNot : peux-tu ouvrir a 1 EUR sans risque,
     quel est le prix de depart conseille si non, et les paliers x2/x3.
   - un bouton genere une **fiche PDF telechargeable**, prete a servir de
     base pour ta fiche produit WhatNot (photo + toutes les infos de prix).
3. **Suivi des ventes** (page "Ventes") : pour chaque article, tu notes sur
   quelle plateforme (WhatNot, Vinted, eBay, Leboncoin, autre) il est en
   vente ou vendu, a quel prix, et son statut.
4. **Reglages** : les taux de douane par categorie (droits de douane + TVA)
   sont modifiables a tout moment.

## A faire avant la premiere utilisation reelle

**Le scraper Buyee doit etre ajuste contre ton vrai compte.** Je n'ai pas pu
me connecter a ton compte Buyee pour verifier la structure exacte des
pages (identifiants necessaires que je n'ai pas). Le fichier
`backend/app/buyee_scraper.py` contient :
- le bon enchainement (connexion -> liste des commandes -> detail de
  chaque facture -> extraction article/photo/prix/port),
- des selecteurs CSS "meilleure estimation" a verifier/corriger une fois
  que tu testes avec tes vrais identifiants (le fichier explique pas a
  pas comment retrouver le bon selecteur avec l'inspecteur du navigateur).

En attendant, utilise le bouton "donnees de demo" pour valider que tout le
reste (calcul du prix de revient, strategie WhatNot, fiche PDF, suivi des
ventes) fonctionne comme tu veux -- j'ai teste ce parcours de bout en bout
et il fonctionne.

## Lancer l'application en local

Terminal 1 (backend) :
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
scrapling install
uvicorn app.main:app --reload --port 8000
```

Terminal 2 (frontend) :
```bash
cd frontend
npm install
npm run dev
```

Ouvre ensuite http://localhost:5173

## Securite

- Tes identifiants Buyee ne sont jamais stockes sur disque : ils partent
  une seule fois vers le backend pour la connexion, restent en memoire le
  temps du scraping, puis sont jetes.
- Les taux de douane par defaut sont indicatifs (voir `backend/README.md`)
  -- a verifier sur le simulateur officiel des douanes francaises pour tes
  categories d'articles precises avant de t'y fier pour une vraie
  declaration.

## Pistes d'evolution (pas encore faites)

- Integrer directement le taux de change JPY/EUR du jour via une API au
  lieu de le saisir a la main.
- Remplacer le stockage JSON par une vraie base de donnees si le volume
  d'articles augmente beaucoup.
- Ajouter l'upload direct de la fiche PDF vers WhatNot si leur interface
  le permet via une API (a verifier, WhatNot n'a pas d'API publique connue
  a ce jour -- pour l'instant la fiche est a re-uploader a la main).
