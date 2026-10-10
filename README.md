# AfriMarket — Projet d'analyse de données

```
Python_Work/
├── README.md
├── requirements.txt                           dépendances du dashboard (déploiement Streamlit)
├── requirements-dev.txt                       + notebook (matplotlib, seaborn, jupyter…)
├── .streamlit/config.toml                     thème du dashboard
├── data/
│   ├── raw/afrimarket_dataset_senior.csv      CSV brut (jamais modifié)
│   └── clean/df_clean.csv, df_analyse.csv     jeux nettoyés (produits par le notebook)
├── src/
│   └── afrimarket_pipeline.py                 nettoyage, features, KPI, chiffrage (source unique)
├── notebooks/
│   └── Analyse_AfriMarket.ipynb (+ .html)     Livrables 1, 4 et 5 : analyse, recommandations, conclusion
├── dashboard/
│   └── app.py                                 Livrable 3 : dashboard Streamlit
├── docs/
│   ├── Presentation_Direction_AfriMarket.pptx     présentation à la direction (16 diapositives)
│   ├── Rapport_Analyse_AfriMarket.pdf             rapport d'analyse complet (16 pages)
│   ├── Resume_Executif_AfriMarket.pdf             résumé exécutif (4 pages)
│   ├── DEPLOIEMENT_STREAMLIT.md                   guide de publication pas à pas
│   ├── Python - Analyse AfriMarket.docx           énoncé du projet
│   └── sources/                                   versions Word éditables (rapport, résumé)
└── figures/                                   graphiques exportés (notebook et résumé)
```

## Lancer (depuis la racine du projet)
```bash
pip install -r requirements-dev.txt
python -m streamlit run dashboard/app.py        # dashboard  ->  http://localhost:8501
```
Notebook : l'ouvrir dans VS Code/Jupyter (Run All), ou en ligne de commande :
```bash
cd notebooks
jupyter nbconvert --to notebook --execute --inplace Analyse_AfriMarket.ipynb
```
Le notebook et le dashboard retrouvent seuls la racine du projet : ils fonctionnent quel que soit le dossier de lancement.

## Publier le dashboard
Voir [docs/DEPLOIEMENT_STREAMLIT.md](docs/DEPLOIEMENT_STREAMLIT.md) (Streamlit Community Cloud, fichier principal : `dashboard/app.py`).

## Hypothèses à connaître
- Le coût d'achat n'existe pas dans les données : taux par catégorie (Électronique 72 %, Maison 55 %, Mode 45 %, Beauté 35 %), modifiables dans la barre latérale du dashboard.
- Montants en UM (devise non précisée dans le fichier).
- CA = commandes livrées uniquement ; profit net = marge brute − livraison (×2 si retour) − marketing.
