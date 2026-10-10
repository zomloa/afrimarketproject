"""
AfriMarket - pipeline de données (audit, nettoyage, feature engineering).

Ce module est la source de vérité partagée par :
  - le notebook d'analyse (notebooks/Analyse_AfriMarket.ipynb)
  - le dashboard Streamlit (dashboard/app.py)
  - le script de génération du résumé exécutif

Toutes les règles de nettoyage et toutes les hypothèses économiques sont
définies ici, une seule fois, et documentées.
"""
from __future__ import annotations

import glob
import os
import unicodedata

import numpy as np
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)                  # racine du projet (parent de src/)
RAW_DIR = os.path.join(PROJECT_DIR, "data", "raw")      # CSV brut : jamais modifié
CLEAN_DIR = os.path.join(PROJECT_DIR, "data", "clean")  # jeux de données nettoyés (df_clean)
FIG_DIR = os.path.join(PROJECT_DIR, "figures")

# --------------------------------------------------------------------------
# Référentiels de standardisation
# --------------------------------------------------------------------------
VILLES = {
    "kinshasa": "Kinshasa", "kinshassa": "Kinshasa",  # faute de frappe détectée à l'audit
    "abidjan": "Abidjan", "douala": "Douala", "dakar": "Dakar",
    "lome": "Lomé", "cotonou": "Cotonou", "libreville": "Libreville",
    "brazzaville": "Brazzaville",
}
CATEGORIES = {
    "electronique": "Électronique", "mode": "Mode",
    "beaute": "Beauté", "maison": "Maison",
}
STATUTS = {"livree": "Livrée", "retournee": "Retournée", "annulee": "Annulée"}

# --------------------------------------------------------------------------
# Hypothèses économiques (le dataset ne contient pas les coûts d'achat)
# Coût d'achat des marchandises (COGS) en % du prix catalogue (avant remise).
# Ce sont des ordres de grandeur sectoriels, modifiables dans le dashboard.
# --------------------------------------------------------------------------
COGS_RATE_DEFAUT = {"Électronique": 0.72, "Mode": 0.45, "Beauté": 0.35, "Maison": 0.55}
# Couleurs fixes par entité (palette catégorielle validée : une couleur = une entité, partout)
COULEURS = {
    "Électronique": "#2a78d6", "Maison": "#eb6834", "Mode": "#1baf7a", "Beauté": "#eda100",
    "Instagram Ads": "#2a78d6", "Google Ads": "#eb6834", "Email": "#1baf7a", "Influenceur": "#eda100",
    "neutre": "#898781", "texte": "#0b0b0b", "texte2": "#52514e", "grille": "#e1e0d9",
    "bon": "#0ca30c", "alerte": "#d03b3b",
}
# Un retour coûte un aller-retour de livraison (le produit est supposé remis en stock).
FACTEUR_LIVRAISON_RETOUR = 2.0


def _cle(s: pd.Series) -> pd.Series:
    """Clé de rapprochement : sans accents, minuscules, sans espaces parasites."""
    def norm(x):
        x = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode()
        return x.strip().lower()
    return s.map(norm)


def _categorie_du_produit(noms: pd.Series) -> pd.Series:
    """Catégorie déduite du nom du produit (format Produit_<Catégorie>_<n>)."""
    return _cle(noms.str.split("_").str[1]).map(CATEGORIES)


# --------------------------------------------------------------------------
# Chargement
# --------------------------------------------------------------------------
def trouver_csv(raw_dir: str = RAW_DIR) -> str:
    fichiers = sorted(glob.glob(os.path.join(raw_dir, "*.csv")))
    if not fichiers:
        raise FileNotFoundError(f"Aucun CSV dans {raw_dir}")
    return fichiers[0]


def charger_brut(path: str | None = None) -> pd.DataFrame:
    """Lit le CSV tel quel (UTF-8), sans aucune correction."""
    return pd.read_csv(path or trouver_csv(), encoding="utf-8")


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
def audit_qualite(raw: pd.DataFrame) -> pd.DataFrame:
    """Tableau de synthèse des problèmes de qualité détectés dans le brut."""
    n = len(raw)
    dup = raw.duplicated().sum()
    dedup = raw.drop_duplicates()
    prix_m50 = (dedup["prix_unitaire"] == -50).sum()
    prix_neg_autre = ((dedup["prix_unitaire"] < 0) & (dedup["prix_unitaire"] != -50)).sum()
    cat_ok = set(CATEGORIES.values()); ville_ok = set(VILLES.values()); st_ok = set(STATUTS.values())
    lignes = [
        ("Doublons exacts (lignes entièrement identiques)", dup, "Supprimer"),
        ("Prix unitaire = -50 (valeur sentinelle)", prix_m50, "Imputer par la médiane du produit"),
        ("Autres prix négatifs", prix_neg_autre, "Imputer par la médiane du produit"),
        ("Quantité = 0", (dedup["quantite"] == 0).sum(), "Supprimer (vente impossible)"),
        ("Remise négative (-10 %)", (dedup["remise"] < 0).sum(), "Imputer par la médiane de la catégorie"),
        ("Ville mal orthographiée (Kinshassa)", (dedup["ville"].str.strip().str.lower() == "kinshassa").sum(), "Corriger -> Kinshasa"),
        ("Catégorie non standard (« electronique » en minuscules)", (~dedup["categorie"].isin(cat_ok)).sum(), "Uniformiser la casse"),
        ("Catégorie contredite par le nom du produit", int((_cle(dedup["categorie"]).map(CATEGORIES) != _categorie_du_produit(dedup["nom_produit"])).sum()),
         "Reclasser selon le produit (source fiable)"),
        ("Statut non standard (retournée)", (~dedup["statut_commande"].isin(st_ok)).sum(), "Uniformiser -> Retournée"),
        ("Valeurs manquantes (toutes colonnes)", int(raw.isna().sum().sum()), "Aucune action"),
    ]
    out = pd.DataFrame(lignes, columns=["Problème", "Lignes concernées", "Traitement"])
    out["% du brut"] = (out["Lignes concernées"] / n * 100).round(2)
    return out


# --------------------------------------------------------------------------
# Nettoyage
# --------------------------------------------------------------------------
def nettoyer(raw: pd.DataFrame, quantite_zero: str = "supprimer") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (df_clean, journal). Chaque étape est tracée dans le journal.

    quantite_zero : "supprimer" (défaut, traitement retenu) ou "imputer" (médiane de la
    catégorie) - utilisé uniquement pour le test de robustesse.
    """
    journal = []
    df = raw.copy()
    journal.append(("Lignes brutes", len(df)))

    # 1. Doublons
    avant = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    journal.append(("Doublons supprimés", avant - len(df)))

    # 2. Dates -> datetime
    df["date_commande"] = pd.to_datetime(df["date_commande"], format="%Y-%m-%d", errors="coerce")
    journal.append(("Dates invalides", int(df["date_commande"].isna().sum())))

    # 3. Villes / catégories / statuts
    df["ville"] = _cle(df["ville"]).map(VILLES)
    df["categorie"] = _cle(df["categorie"]).map(CATEGORIES)
    df["statut_commande"] = _cle(df["statut_commande"]).map(STATUTS)
    # Le libellé « electronique » écrase la vraie catégorie sur 600 lignes : le nom du
    # produit (et son niveau de prix) prouve que la majorité sont Beauté/Mode/Maison.
    # On reclasse donc d'après le produit, qui est la source fiable.
    df["nom_produit"] = df["nom_produit"].str.strip()
    cat_produit = _categorie_du_produit(df["nom_produit"])
    df["categorie_corrigee"] = df["categorie"] != cat_produit
    journal.append(("Catégories reclassées d'après le nom du produit", int(df["categorie_corrigee"].sum())))
    df["categorie"] = cat_produit
    non_mappes = int(df[["ville", "categorie", "statut_commande"]].isna().sum().sum())
    journal.append(("Valeurs non rapprochées (ville/catégorie/statut)", non_mappes))

    # 4. Quantités nulles -> suppression
    avant = len(df)
    if quantite_zero == "imputer":
        med_q = df.loc[df["quantite"] > 0].groupby("categorie")["quantite"].median()
        nul = df["quantite"] == 0
        df.loc[nul, "quantite"] = df.loc[nul, "categorie"].map(med_q).astype(int)
        journal.append(("Lignes quantité = 0 imputées (médiane catégorie)", int(nul.sum())))
    else:
        df = df[df["quantite"] > 0].reset_index(drop=True)
        journal.append(("Lignes quantité = 0 supprimées", avant - len(df)))

    # 5. Prix aberrants (négatifs) -> médiane du produit (prix valides)
    df["prix_corrige"] = df["prix_unitaire"] <= 0
    med_produit = df.loc[~df["prix_corrige"]].groupby("nom_produit")["prix_unitaire"].median()
    med_cat = df.loc[~df["prix_corrige"]].groupby("categorie")["prix_unitaire"].median()
    imput = df["nom_produit"].map(med_produit).fillna(df["categorie"].map(med_cat))
    df.loc[df["prix_corrige"], "prix_unitaire"] = imput[df["prix_corrige"]]
    journal.append(("Prix négatifs imputés (médiane produit)", int(df["prix_corrige"].sum())))

    # 6. Remises négatives -> médiane des remises valides de la catégorie
    df["remise_corrigee"] = df["remise"] < 0
    med_rem = df.loc[~df["remise_corrigee"]].groupby("categorie")["remise"].median()
    df.loc[df["remise_corrigee"], "remise"] = df.loc[df["remise_corrigee"], "categorie"].map(med_rem)
    journal.append(("Remises négatives imputées (médiane catégorie)", int(df["remise_corrigee"].sum())))

    journal.append(("Lignes dans df_clean", len(df)))
    return df, pd.DataFrame(journal, columns=["Étape", "Lignes"])


# --------------------------------------------------------------------------
# Feature engineering
# --------------------------------------------------------------------------
def ajouter_features(df_clean: pd.DataFrame, cogs_rate: dict | None = None) -> pd.DataFrame:
    """
    Définitions :
      chiffre_affaires : CA facturé de la ligne = prix x quantité x (1 - remise)
      ca_net           : CA réellement encaissé = chiffre_affaires si Livrée, sinon 0
                         (une commande annulée ou retournée est remboursée)
      marge_brute      : ca_net - coût d'achat (COGS) des produits livrés
      profit_net       : marge_brute - livraison - coût marketing
                         * livraison : due si non annulée, x2 si retournée (aller-retour)
                         * marketing : toujours dépensé (coût d'acquisition perdu)
    """
    cogs_rate = cogs_rate or COGS_RATE_DEFAUT
    df = df_clean.copy()
    df["mois"] = df["date_commande"].dt.to_period("M").dt.to_timestamp()
    df["mois_label"] = df["date_commande"].dt.strftime("%Y-%m")

    df["chiffre_affaires"] = df["prix_unitaire"] * df["quantite"] * (1 - df["remise"])
    df["indicateur_retour"] = (df["statut_commande"] == "Retournée").astype(int)
    df["indicateur_annulation"] = (df["statut_commande"] == "Annulée").astype(int)
    livree = df["statut_commande"] == "Livrée"
    df["ca_net"] = np.where(livree, df["chiffre_affaires"], 0.0)
    df["ca_perdu_retour"] = np.where(df["indicateur_retour"] == 1, df["chiffre_affaires"], 0.0)
    df["ca_perdu_annulation"] = np.where(df["indicateur_annulation"] == 1, df["chiffre_affaires"], 0.0)

    df["cout_achat"] = np.where(livree, df["prix_unitaire"] * df["quantite"] * df["categorie"].map(cogs_rate), 0.0)
    df["marge_brute"] = df["ca_net"] - df["cout_achat"]
    facteur = np.select(
        [df["statut_commande"] == "Annulée", df["statut_commande"] == "Retournée"],
        [0.0, FACTEUR_LIVRAISON_RETOUR], default=1.0)
    df["cout_livraison_effectif"] = df["cout_livraison"] * facteur
    df["profit_net"] = df["marge_brute"] - df["cout_livraison_effectif"] - df["cout_marketing"]

    # Features client (commandes "valides" = non annulées)
    valide = df["statut_commande"] != "Annulée"
    nb_cmd = df[valide].groupby("id_client").size()
    df["nombre_commandes_par_client"] = df["id_client"].map(nb_cmd).fillna(0).astype(int)
    clv = df.groupby("id_client")["profit_net"].sum()
    df["valeur_vie_client"] = df["id_client"].map(clv)
    return df


def table_clients(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par client : fréquence, CA, profit, CLV, segment."""
    ref = df["date_commande"].max()
    valide = df[df["statut_commande"] != "Annulée"]
    g = df.groupby("id_client")
    cl = pd.DataFrame({
        "nb_commandes": valide.groupby("id_client").size(),
        "ca_net": g["ca_net"].sum(),
        "profit_net": g["profit_net"].sum(),
        "derniere_commande": valide.groupby("id_client")["date_commande"].max(),
        "premiere_commande": valide.groupby("id_client")["date_commande"].min(),
    }).fillna({"nb_commandes": 0})
    cl["nb_commandes"] = cl["nb_commandes"].astype(int)
    cl["jours_inactivite"] = (ref - cl["derniere_commande"]).dt.days
    # canal de la 1re commande valide (pour la rétention par canal)
    prem = valide.sort_values(["id_client", "date_commande", "id_commande"]).groupby("id_client").first()
    cl["canal_acquisition"] = prem["canal_marketing"]
    cl["categorie_1er_achat"] = prem["categorie"]
    cl["ville_principale"] = valide.groupby("id_client")["ville"].agg(lambda s: s.mode().iat[0])
    cl = cl[cl["nb_commandes"] >= 1].copy()          # clients acheteurs (au moins 1 commande non annulée)
    cl["recurrent"] = cl["nb_commandes"] >= 2

    seuil_vip = cl["ca_net"].quantile(0.90)
    def seg(r):
        if r["ca_net"] >= seuil_vip and r["nb_commandes"] >= 3:
            return "VIP"
        if r["nb_commandes"] >= 3:
            return "Fidèles"
        if r["nb_commandes"] == 2:
            return "Occasionnels"
        return "Nouveaux (1 achat)"
    cl["segment"] = cl.apply(seg, axis=1)
    cl["a_risque"] = (cl["jours_inactivite"] > 90) & (cl["nb_commandes"] >= 2)
    return cl.reset_index()


def charger_clean(path: str | None = None, cogs_rate: dict | None = None, quantite_zero: str = "supprimer"):
    """Raccourci : brut -> nettoyé -> features. Retourne (df, journal, raw)."""
    raw = charger_brut(path)
    clean, journal = nettoyer(raw, quantite_zero)
    return ajouter_features(clean, cogs_rate), journal, raw


# --------------------------------------------------------------------------
# Agrégats réutilisés partout (une seule définition par KPI)
# --------------------------------------------------------------------------
def kpis_globaux(df: pd.DataFrame) -> dict:
    n = len(df)
    livrees = (df["statut_commande"] == "Livrée").sum()
    retours = df["indicateur_retour"].sum()
    annul = df["indicateur_annulation"].sum()
    expediees = livrees + retours
    return {
        "nb_commandes": n,
        "ca_total": df["ca_net"].sum(),
        "ca_facture": df.loc[df["statut_commande"] != "Annulée", "chiffre_affaires"].sum(),
        "marge_brute": df["marge_brute"].sum(),
        "profit_net": df["profit_net"].sum(),
        "panier_moyen": df["ca_net"].sum() / livrees if livrees else np.nan,
        "taux_annulation": annul / n if n else np.nan,
        "taux_retour": retours / expediees if expediees else np.nan,
        "cout_marketing": df["cout_marketing"].sum(),
        "ca_perdu_retour": df["ca_perdu_retour"].sum(),
        "nb_clients": df.loc[df["statut_commande"] != "Annulée", "id_client"].nunique(),
    }


def agg_dimension(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """KPI standard par dimension (catégorie, ville, canal...)."""
    g = df.groupby(col)
    out = pd.DataFrame({
        "commandes": g.size(),
        "ca_net": g["ca_net"].sum(),
        "marge_brute": g["marge_brute"].sum(),
        "profit_net": g["profit_net"].sum(),
        "cout_marketing": g["cout_marketing"].sum(),
        "livraisons": g["cout_livraison_effectif"].sum(),
        "retours": g["indicateur_retour"].sum(),
        "annulations": g["indicateur_annulation"].sum(),
    })
    livrees = g["statut_commande"].apply(lambda s: (s == "Livrée").sum())
    out["livrees"] = livrees
    out["panier_moyen"] = out["ca_net"] / out["livrees"]
    out["taux_marge"] = out["marge_brute"] / out["ca_net"]
    out["taux_profit"] = out["profit_net"] / out["ca_net"]
    out["taux_retour"] = out["retours"] / (out["livrees"] + out["retours"])
    out["taux_annulation"] = out["annulations"] / out["commandes"]
    out["roi"] = (out["ca_net"] - out["cout_marketing"]) / out["cout_marketing"]
    out["roi_profit"] = out["profit_net"] / out["cout_marketing"]
    return out


# --------------------------------------------------------------------------
# Chiffrage des recommandations (ordres de grandeur sur la période observée : 6 mois)
# --------------------------------------------------------------------------
def croissance_t4_t3(df: pd.DataFrame, col: str, valeur: str = "ca_net") -> pd.Series:
    """Croissance du T4 (oct-déc) vs T3 (juil-sept) par dimension : plus robuste que le mois à mois."""
    t = np.where(df["date_commande"] >= "2025-10-01", "T4", "T3")
    p = df.assign(t=t).pivot_table(index=col, columns="t", values=valeur, aggfunc="sum")
    return (p["T4"] / p["T3"] - 1).rename("croissance_t4_t3")


def simuler_reallocation(df: pd.DataFrame, part_deplacee: float = 0.25, efficacite_marginale: float = 0.5) -> dict:
    """
    Déplace `part_deplacee` du budget Instagram+Influenceur vers Google Ads.
    Rendement brut d'un canal = profit avant marketing par unité dépensée.
    Hypothèse prudente : la 1re unité ajoutée sur Google rapporte `efficacite_marginale` x sa moyenne
    (rendements décroissants). Le budget total est inchangé.
    """
    mk = agg_dimension(df, "canal_marketing")
    rend = (mk["profit_net"] + mk["cout_marketing"]) / mk["cout_marketing"]
    src = ["Instagram Ads", "Influenceur"]
    budget_src = mk.loc[src, "cout_marketing"].sum()
    rend_src = (mk.loc[src, "profit_net"] + mk.loc[src, "cout_marketing"]).sum() / budget_src
    montant = part_deplacee * budget_src
    gain = montant * efficacite_marginale * rend["Google Ads"]
    perte = montant * rend_src
    return {"montant": montant, "rend_source": rend_src, "rend_google": rend["Google Ads"],
            "gain_net": gain - perte, "seuil_efficacite": rend_src / rend["Google Ads"]}


def chiffrer_recommandations(df: pd.DataFrame, cl: pd.DataFrame) -> dict:
    """Impact estimé de chaque recommandation (en UM de profit sur 6 mois) + indicateurs de départ."""
    out = {}
    # R1 - Douala : annulations
    dou = df[df["ville"] == "Douala"]
    ref = df.loc[df["ville"] != "Douala", "indicateur_annulation"].mean()
    n_ann = dou["indicateur_annulation"].sum()
    exces = n_ann - ref * len(dou)
    non_ann = dou[dou["statut_commande"] != "Annulée"]
    profit_par_cmd = (non_ann["marge_brute"] - non_ann["cout_livraison_effectif"]).mean()
    recup = 0.70 * exces
    out["r1"] = {"taux_douala": dou["indicateur_annulation"].mean(), "taux_ref": ref, "annulations": int(n_ann),
                 "ca_annule": dou["ca_perdu_annulation"].sum(), "cmd_recuperees": recup, "impact": recup * profit_par_cmd}
    # R2 - Retours Électronique : 15,6 % -> 10 %
    el = df[(df["categorie"] == "Électronique") & (df["statut_commande"] != "Annulée")]
    taux = el["indicateur_retour"].mean(); cible = 0.10
    evites = max(taux - cible, 0) * len(el)
    liv = el[el["statut_commande"] == "Livrée"]
    gain_cmd = liv["marge_brute"].mean() + el["cout_livraison"].mean()
    out["r2"] = {"taux": taux, "cible": cible, "retours_evites": evites,
                 "ca_rembourse": df.loc[df["categorie"] == "Électronique", "ca_perdu_retour"].sum(),
                 "ca_conserve": evites * liv["ca_net"].mean(), "impact": evites * gain_cmd}
    # R3 - Marketing
    sim = simuler_reallocation(df)
    out["r3"] = {**sim, "impact": sim["gain_net"]}
    # R4 - Mix : redresser Mode au niveau T3 (Maison : sécuriser le pic de T4)
    g = df.assign(t=np.where(df["date_commande"] >= "2025-10-01", "T4", "T3")).pivot_table(
        index="categorie", columns="t", values=["ca_net", "profit_net"], aggfunc="sum")
    taux_profit_mode = g.loc["Mode", ("profit_net", "T3")] / g.loc["Mode", ("ca_net", "T3")]
    manque_mode = g.loc["Mode", ("ca_net", "T3")] - g.loc["Mode", ("ca_net", "T4")]
    out["r4"] = {"mode_t4_t3": g.loc["Mode", ("ca_net", "T4")] / g.loc["Mode", ("ca_net", "T3")] - 1,
                 "maison_t4_t3": g.loc["Maison", ("ca_net", "T4")] / g.loc["Maison", ("ca_net", "T3")] - 1,
                 "maison_profit_t4": g.loc["Maison", ("profit_net", "T4")],
                 "maison_gain_t4": g.loc["Maison", ("profit_net", "T4")] - g.loc["Maison", ("profit_net", "T3")],
                 "impact": max(manque_mode, 0) * taux_profit_mode}
    # R5 - Rétention : réactiver 30 % des clients à risque, convertir 15 % des clients 1 achat
    risque = cl[cl["a_risque"]]
    un = cl[cl["nb_commandes"] == 1]
    taux_profit_cl = cl["profit_net"].sum() / cl["ca_net"].sum()
    ca_react = 0.30 * risque["ca_net"].sum() * 0.5            # 3 mois d'activité au rythme historique
    ca_conv = 0.15 * len(un) * (un["ca_net"].mean())          # une 2e commande de valeur équivalente
    out["r5"] = {"nb_risque": len(risque), "ca_risque": risque["ca_net"].sum(), "nb_un_achat": len(un),
                 "ca_gagne": ca_react + ca_conv, "impact": (ca_react + ca_conv) * taux_profit_cl}
    out["total_impact"] = sum(out[k]["impact"] for k in ["r1", "r2", "r3", "r4", "r5"])
    out["profit_base"] = df["profit_net"].sum()
    return out


if __name__ == "__main__":
    df, journal, raw = charger_clean()
    print(journal.to_string(index=False))
    print({k: round(float(v), 4) for k, v in kpis_globaux(df).items()})
