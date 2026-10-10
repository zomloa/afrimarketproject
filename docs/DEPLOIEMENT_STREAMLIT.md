# Publier le dashboard sur Streamlit Community Cloud

Le dépôt est prêt : `requirements.txt` (dépendances du dashboard uniquement), `.streamlit/config.toml` (thème) et `.gitignore` sont déjà en place. Testé dans un environnement vierge, avec pandas 3 et pandas 2.

## 1. Mettre le projet sur GitHub
Depuis la racine du projet (`Python_Work`) :
```bash
git init
git add .
git commit -m "AfriMarket - analyse et dashboard"
git branch -M main
git remote add origin https://github.com/<votre-compte>/afrimarket-dashboard.git
git push -u origin main
```
(Créez d'abord le dépôt vide sur github.com. **Dépôt privé recommandé** : le CSV contient des identifiants clients, même pseudonymisés.)

## 2. Déployer
1. Aller sur https://share.streamlit.io et se connecter avec GitHub.
2. **Create app** → *Deploy a public app from GitHub*.
3. Renseigner :
   - **Repository** : `<votre-compte>/afrimarket-dashboard`
   - **Branch** : `main`
   - **Main file path** : `dashboard/app.py`
4. **Advanced settings** → Python **3.12** ou **3.13**.
5. **Deploy**. L'installation prend 2 à 3 minutes ; `requirements.txt` est détecté automatiquement à la racine.

## 3. Points d'attention
- `data/raw/afrimarket_dataset_senior.csv` **doit** être dans le dépôt : l'application le lit au démarrage.
- Aucun secret n'est utilisé : rien à configurer dans *Secrets*.
- Le premier chargement nettoie les données (quelques secondes), puis tout est mis en cache.
- Mise à jour : un simple `git push` redéploie l'application.
- Tester en local avant de publier : `python -m streamlit run dashboard/app.py`.

## Fichiers de dépendances
| Fichier | Usage |
|---|---|
| `requirements.txt` | **Déploiement** : streamlit, pandas, numpy, plotly |
| `requirements-dev.txt` | Poste de travail : ajoute matplotlib, seaborn, scipy, jupyter pour le notebook |
