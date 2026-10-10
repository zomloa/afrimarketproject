"""
AfriMarket - Dashboard décisionnel (Streamlit).

Lancer (depuis la racine du projet) :  python -m streamlit run dashboard/app.py
Les règles de nettoyage et les définitions de KPI sont celles du notebook
(module partagé afrimarket_pipeline.py) : mêmes chiffres partout.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # module partagé : src/afrimarket_pipeline.py
import afrimarket_pipeline as ap

st.set_page_config(page_title="AfriMarket - Dashboard", page_icon="📊", layout="wide")

C = ap.COULEURS
BLEU, ORANGE, GRIS, ROUGE = C["Électronique"], C["Maison"], C["neutre"], "#e34948"
ORDRE_CAT = ["Électronique", "Maison", "Mode", "Beauté"]
CANAUX = ["Instagram Ads", "Google Ads", "Email", "Influenceur"]
MOIS_FR = {"2025-07": "Juil", "2025-08": "Août", "2025-09": "Sept", "2025-10": "Oct", "2025-11": "Nov", "2025-12": "Déc"}
SEGMENTS = ["VIP", "Fidèles", "Occasionnels", "Nouveaux (1 achat)"]


# ----------------------------------------------------------------------------- formats
def nf(v, d=0):
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def pct(v, d=1):
    return f"{v * 100:.{d}f}".replace(".", ",") + " %"


def pcs(v, d=0):
    return f"{v * 100:+.{d}f}".replace(".", ",") + " %"


def kfmt(v, d=0):
    return nf(v / 1e3, d) + " k"


def style(fig, h=380):
    fig.update_layout(template="simple_white", height=h, margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15, title_text=""), title_font=dict(size=15))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e1e0d9")
    return fig


# ----------------------------------------------------------------------------- données
@st.cache_data(show_spinner="Chargement et nettoyage des données…")
def charger():
    raw = ap.charger_brut()
    clean, journal = ap.nettoyer(raw)
    return raw, clean, journal


raw, df_clean, journal = charger()


@st.cache_data(show_spinner=False, max_entries=32)
def calculer_base(cogs_items: tuple):
    """Features, table clients et chiffrage des recommandations : recalculés seulement si les hypothèses de coût changent."""
    df_all = ap.ajouter_features(df_clean, dict(cogs_items))
    cl_all = ap.table_clients(df_all)
    return df_all, cl_all, ap.chiffrer_recommandations(df_all, cl_all)


# ----------------------------------------------------------------------------- barre latérale
st.sidebar.title("Filtres")
dmin, dmax = df_clean["date_commande"].min().date(), df_clean["date_commande"].max().date()
periode = st.sidebar.date_input("Période", (dmin, dmax), min_value=dmin, max_value=dmax)
villes = st.sidebar.multiselect("Villes", sorted(df_clean["ville"].unique()), default=sorted(df_clean["ville"].unique()))
cats = st.sidebar.multiselect("Catégories", ORDRE_CAT, default=ORDRE_CAT)
canaux = st.sidebar.multiselect("Canaux marketing", CANAUX, default=CANAUX)

with st.sidebar.expander("Hypothèses de coût d'achat (% du prix)"):
    st.caption("Absents des données : hypothèses sectorielles, modifiables. Elles ne changent pas les classements (voir notebook §6).")
    cogs = {c: st.slider(c, 20, 90, int(ap.COGS_RATE_DEFAUT[c] * 100), 1, key=f"cogs_{c}") / 100 for c in ORDRE_CAT}

if isinstance(periode, tuple) and len(periode) == 2:
    d0, d1 = pd.Timestamp(periode[0]), pd.Timestamp(periode[1])
else:
    d0, d1 = pd.Timestamp(dmin), pd.Timestamp(dmax)

df_all, cl_all, rap = calculer_base(tuple(sorted(cogs.items())))      # base complète (pour les recommandations)
df = df_all[df_all["date_commande"].between(d0, d1) & df_all["ville"].isin(villes)
            & df_all["categorie"].isin(cats) & df_all["canal_marketing"].isin(canaux)]

st.title("AfriMarket - Pilotage de la performance")
st.caption(f"Période {d0:%d/%m/%Y} - {d1:%d/%m/%Y} · montants en UM (unité monétaire du dataset) · "
           f"CA = commandes livrées uniquement (annulations et retours remboursés)")

if df.empty:
    st.warning("Aucune commande ne correspond aux filtres sélectionnés.")
    st.stop()

kp = ap.kpis_globaux(df)
clients = ap.table_clients(df)

tabs = st.tabs(["Synthèse", "Catégories", "Villes", "Marketing", "Clients", "Recommandations", "Qualité des données"])

# ============================================================================= SYNTHÈSE
with tabs[0]:
    c = st.columns(6)
    c[0].metric("CA net", f"{nf(kp['ca_total'])} UM")
    c[1].metric("Profit net estimé", f"{nf(kp['profit_net'])} UM", pct(kp["profit_net"] / kp["ca_total"]) + " du CA", delta_color="off")
    c[2].metric("Panier moyen", f"{nf(kp['panier_moyen'], 1)} UM")
    c[3].metric("Taux d'annulation", pct(kp["taux_annulation"]))
    c[4].metric("Taux de retour", pct(kp["taux_retour"]))
    c[5].metric("Clients acheteurs", nf(kp["nb_clients"]))

    left, right = st.columns([1.15, 1])
    m = df.groupby("mois_label").agg(ca=("ca_net", "sum"), profit=("profit_net", "sum")).reset_index()
    m["mois"] = m["mois_label"].map(MOIS_FR)
    fig = go.Figure()
    fig.add_bar(x=m["mois"], y=m["ca"], name="CA net", marker_color=BLEU, text=[kfmt(v) for v in m["ca"]], textposition="outside")
    fig.add_scatter(x=m["mois"], y=m["profit"], name="Profit net", mode="lines+markers+text", line=dict(color=ORANGE, width=3),
                    text=[kfmt(v) for v in m["profit"]], textposition="top center")
    fig.update_layout(title="CA net et profit net par mois")
    fig.update_yaxes(tickformat=",.0f", range=[0, m["ca"].max() * 1.18])
    left.plotly_chart(style(fig), width="stretch")

    ca_fact = df["chiffre_affaires"].sum()
    vals = [ca_fact, -df["ca_perdu_annulation"].sum(), -df["ca_perdu_retour"].sum(), None, -df["cout_achat"].sum(), None,
            -df["cout_livraison_effectif"].sum(), -df["cout_marketing"].sum(), None]
    wf = go.Figure(go.Waterfall(
        x=["CA facturé", "Annulations", "Retours", "CA net", "Coût d'achat", "Marge brute", "Livraison", "Marketing", "Profit net"],
        measure=["absolute", "relative", "relative", "total", "relative", "total", "relative", "relative", "total"],
        y=vals, text=[kfmt(v) if v is not None else "" for v in vals], textposition="outside",
        increasing=dict(marker_color=BLEU), decreasing=dict(marker_color=ROUGE), totals=dict(marker_color=BLEU), connector=dict(line_color=GRIS)))
    wf.update_layout(title="De la vente facturée au profit net", showlegend=False)
    right.plotly_chart(style(wf), width="stretch")

    st.info(f"**Lecture** : sur {kfmt(ca_fact)} UM facturées, {pct(kp['profit_net'] / ca_fact)} deviennent du profit. "
            f"Les retours en font disparaître {kfmt(kp['ca_perdu_retour'])} UM, bien plus que les annulations ({kfmt(df['ca_perdu_annulation'].sum())} UM).")

# ============================================================================= CATÉGORIES
with tabs[1]:
    cat = ap.agg_dimension(df, "categorie").reindex([c for c in ORDRE_CAT if c in df["categorie"].unique()])
    cat["part_ca"] = cat["ca_net"] / cat["ca_net"].sum()
    cat["part_profit"] = cat["profit_net"] / cat["profit_net"].sum()
    st.subheader("Quelle catégorie prioriser ou optimiser ?")
    t = cat[["commandes", "ca_net", "part_ca", "marge_brute", "taux_marge", "profit_net", "taux_profit", "panier_moyen", "taux_retour"]].copy()
    st.dataframe(t.style.format({"commandes": "{:,.0f}", "ca_net": "{:,.0f}", "part_ca": "{:.1%}", "marge_brute": "{:,.0f}", "taux_marge": "{:.1%}",
                                 "profit_net": "{:,.0f}", "taux_profit": "{:.1%}", "panier_moyen": "{:,.0f}", "taux_retour": "{:.1%}"}),
                 width="stretch")
    a, b = st.columns(2)
    fig = px.bar(cat.reset_index(), x="categorie", y="taux_retour", color="categorie", color_discrete_map={k_: C[k_] for k_ in ORDRE_CAT},
                 text=cat["taux_retour"].map(pct), title="Taux de retour par catégorie", labels={"categorie": "", "taux_retour": ""})
    fig.update_yaxes(tickformat=".0%"); fig.update_layout(showlegend=False); fig.update_traces(textposition="outside")
    a.plotly_chart(style(fig), width="stretch")
    fig = px.bar(cat.reset_index(), x="categorie", y="taux_profit", color="categorie", color_discrete_map={k_: C[k_] for k_ in ORDRE_CAT},
                 text=cat["taux_profit"].map(pct), title="Profit net / CA par catégorie", labels={"categorie": "", "taux_profit": ""})
    fig.update_yaxes(tickformat=".0%"); fig.update_layout(showlegend=False); fig.update_traces(textposition="outside")
    b.plotly_chart(style(fig), width="stretch")

    pm = df.pivot_table(index="mois_label", columns="categorie", values="ca_net", aggfunc="sum")
    pm.index = [MOIS_FR[i] for i in pm.index]
    fig = px.line(pm.reset_index().melt(id_vars="index", var_name="Catégorie", value_name="CA net"), x="index", y="CA net", color="Catégorie", markers=True,
                  color_discrete_map={k_: C[k_] for k_ in ORDRE_CAT}, title="Évolution mensuelle du CA net par catégorie", labels={"index": ""})
    fig.update_traces(line=dict(width=3))
    st.plotly_chart(style(fig, 400), width="stretch")

    exp = df[df["statut_commande"] != "Annulée"]
    if not exp.empty:
        hm = exp.pivot_table(index="categorie", columns="ville", values="indicateur_retour", aggfunc="mean")
        fig = px.imshow(hm, text_auto=".1%", color_continuous_scale=["#cde2fb", "#2a78d6", "#0d366b"], aspect="auto", title="Taux de retour catégorie × ville")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style(fig, 330), width="stretch")

# ============================================================================= VILLES
with tabs[2]:
    vil = ap.agg_dimension(df, "ville").sort_values("ca_net", ascending=False)
    vil["part_ca"] = vil["ca_net"] / vil["ca_net"].sum()
    st.subheader("Où investir davantage ?")
    if df["date_commande"].nunique() > 60:
        vil["croissance_t4_t3"] = ap.croissance_t4_t3(df, "ville")
    cols = [c_ for c_ in ["commandes", "ca_net", "part_ca", "profit_net", "taux_profit", "panier_moyen", "taux_annulation", "taux_retour", "croissance_t4_t3"] if c_ in vil]
    fmt = {"commandes": "{:,.0f}", "ca_net": "{:,.0f}", "part_ca": "{:.1%}", "profit_net": "{:,.0f}", "taux_profit": "{:.1%}", "panier_moyen": "{:,.0f}",
           "taux_annulation": "{:.1%}", "taux_retour": "{:.1%}", "croissance_t4_t3": "{:+.1%}"}
    st.dataframe(vil[cols].style.format({k_: v for k_, v in fmt.items() if k_ in cols}), width="stretch")
    a, b = st.columns(2)
    fig = px.bar(vil.reset_index().sort_values("ca_net"), x="ca_net", y="ville", orientation="h", title="CA net par ville", labels={"ca_net": "", "ville": ""},
                 color_discrete_sequence=[BLEU], text=[kfmt(v) for v in vil.reset_index().sort_values("ca_net")["ca_net"]])
    fig.update_traces(textposition="outside"); fig.update_xaxes(tickformat=",.0f")
    a.plotly_chart(style(fig, 400), width="stretch")
    ann = vil["taux_annulation"].sort_values().reset_index()
    fig = px.bar(ann, x="taux_annulation", y="ville", orientation="h", title="Taux d'annulation par ville", labels={"taux_annulation": "", "ville": ""},
                 text=ann["taux_annulation"].map(pct))
    fig.update_traces(marker_color=[ROUGE if v > .05 else GRIS for v in ann["taux_annulation"]], textposition="outside")
    fig.update_xaxes(tickformat=".0%")
    b.plotly_chart(style(fig, 400), width="stretch")

    cv = df.pivot_table(index="ville", columns="mois_label", values="ca_net", aggfunc="sum").reindex(vil.index)
    if cv.shape[1] > 1:
        mom = cv.pct_change(axis=1).iloc[:, 1:]
        mom.columns = [MOIS_FR[c_] for c_ in mom.columns]
        fig = px.imshow(mom, text_auto=".0%", color_continuous_scale=[[0, ROUGE], [.5, "#f0efec"], [1, BLEU]], zmin=-.6, zmax=.6, aspect="auto",
                        title="Croissance mensuelle du CA par ville (mois sur mois)")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style(fig, 400), width="stretch")

# ============================================================================= MARKETING
with tabs[3]:
    st.subheader("Quel canal financer, optimiser ou réduire ?")
    mk = ap.agg_dimension(df, "canal_marketing")
    mk["cout_par_commande"] = mk["cout_marketing"] / mk["commandes"]
    mk["part_budget"] = mk["cout_marketing"] / mk["cout_marketing"].sum()
    mk["part_profit"] = mk["profit_net"] / mk["profit_net"].sum()
    ret = clients.groupby("canal_acquisition").agg(clients=("id_client", "count"), taux_retention=("recurrent", "mean"))
    mk = mk.join(ret).reindex([c_ for c_ in CANAUX if c_ in mk.index])
    st.caption("ROI = (Revenus − Coût marketing) / Coût marketing, revenus = CA net du canal. ROI profit = profit net / coût marketing. "
               "Rétention = % de clients ≥ 2 commandes parmi ceux acquis par ce canal.")
    st.dataframe(mk[["ca_net", "cout_marketing", "part_budget", "roi", "roi_profit", "cout_par_commande", "part_profit", "clients", "taux_retention"]]
                 .style.format({"ca_net": "{:,.0f}", "cout_marketing": "{:,.0f}", "part_budget": "{:.1%}", "roi": "{:,.1f}", "roi_profit": "{:,.1f}",
                                "cout_par_commande": "{:.2f}", "part_profit": "{:.1%}", "clients": "{:,.0f}", "taux_retention": "{:.1%}"}),
                 width="stretch")
    a, b = st.columns(2)
    mesure = a.radio("Mesure de ROI", ["ROI sur CA (formule de l'énoncé)", "ROI sur profit net"], horizontal=True)
    col = "roi" if mesure.startswith("ROI sur CA") else "roi_profit"
    d_ = mk[col].sort_values().reset_index()
    fig = px.bar(d_, x=col, y="canal_marketing", orientation="h", color="canal_marketing", color_discrete_map={k_: C[k_] for k_ in CANAUX},
                 text=d_[col].map(lambda v: nf(v, 1)), labels={col: "", "canal_marketing": ""}, title=mesure)
    fig.update_layout(showlegend=False); fig.update_traces(textposition="outside")
    a.plotly_chart(style(fig, 330), width="stretch")
    share = mk[["part_budget", "part_profit"]].reset_index().melt(id_vars="canal_marketing", var_name="Part", value_name="v")
    share["Part"] = share["Part"].map({"part_budget": "Part du budget", "part_profit": "Part du profit net"})
    fig = px.bar(share, x="canal_marketing", y="v", color="Part", barmode="group", color_discrete_sequence=["#b9b8b0", "#3d3c39"], text=share["v"].map(lambda v: pct(v, 0)),
                 labels={"canal_marketing": "", "v": ""}, title="Qui consomme le budget, qui crée le profit")
    fig.update_yaxes(tickformat=".0%"); fig.update_traces(textposition="outside")
    b.plotly_chart(style(fig, 330), width="stretch")

    st.markdown("#### Simulateur de réallocation Instagram + Influenceur → Google Ads")
    s1, s2 = st.columns(2)
    part = s1.slider("Part du budget Instagram + Influenceur déplacée", 0, 50, 25, 5, format="%d %%") / 100
    eff = s2.slider("Efficacité marginale de Google Ads (vs sa moyenne)", 10, 100, 50, 5, format="%d %%") / 100
    sim = ap.simuler_reallocation(df_all, part, eff)
    r1, r2, r3 = st.columns(3)
    r1.metric("Budget déplacé", f"{nf(sim['montant'])} UM")
    r2.metric("Gain net de profit estimé (6 mois)", f"{nf(sim['gain_net'])} UM", delta="rentable" if sim["gain_net"] > 0 else "destructeur de valeur")
    r3.metric("Seuil de rentabilité", pct(sim["seuil_efficacite"], 0), help="Google doit conserver au moins cette part de son efficacité moyenne.")
    st.caption("Calculé sur la période complète, tous filtres ignorés. Hypothèse prudente : rendements décroissants ; l'attribution est « un canal par commande » (ROI moyens, non incrémentaux).")

# ============================================================================= CLIENTS
with tabs[4]:
    st.subheader("Comment améliorer la rétention ?")
    nb = len(clients)
    if nb == 0:
        st.warning("Aucun client acheteur sur ce périmètre.")
    else:
        cs = clients.sort_values("ca_net", ascending=False).reset_index(drop=True)
        cs["part_cum"] = cs["ca_net"].cumsum() / cs["ca_net"].sum()
        n80 = int((cs["part_cum"] < 0.8).sum() + 1)
        c = st.columns(5)
        c[0].metric("Clients acheteurs", nf(nb))
        c[1].metric("Clients récurrents (≥ 2 cmd)", pct(clients["recurrent"].mean()))
        c[2].metric("Clients à 1 seul achat", nf((clients["nb_commandes"] == 1).sum()))
        c[3].metric("Pareto : clients pour 80 % du CA", pct(n80 / nb))
        c[4].metric("Clients à risque (> 90 j)", nf(clients["a_risque"].sum()))
        a, b = st.columns(2)
        fig = go.Figure()
        fig.add_scatter(x=np.arange(1, nb + 1) / nb, y=cs["part_cum"], mode="lines", line=dict(color=BLEU, width=3), name="CA cumulé", fill="tozeroy", fillcolor="rgba(42,120,214,.08)")
        fig.add_scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=GRIS, dash="dash"), name="Répartition égale")
        fig.add_hline(y=.8, line_dash="dot", line_color=GRIS); fig.add_vline(x=n80 / nb, line_dash="dot", line_color=GRIS)
        fig.update_layout(title=f"Courbe de Pareto : {pct(n80 / nb, 0)} des clients = 80 % du CA")
        fig.update_xaxes(tickformat=".0%", title="Part des clients"); fig.update_yaxes(tickformat=".0%", title="Part cumulée du CA")
        a.plotly_chart(style(fig, 380), width="stretch")
        sg = clients.groupby("segment").agg(clients=("id_client", "count"), ca=("ca_net", "sum"), profit=("profit_net", "sum")).reindex([s for s in SEGMENTS if s in clients["segment"].unique()])
        sg["Part des clients"] = sg["clients"] / sg["clients"].sum(); sg["Part du CA"] = sg["ca"] / sg["ca"].sum()
        sh = sg[["Part des clients", "Part du CA"]].reset_index().melt(id_vars="segment", var_name="Mesure", value_name="v")
        fig = px.bar(sh, x="segment", y="v", color="Mesure", barmode="group", color_discrete_sequence=["#b9b8b0", BLEU], text=sh["v"].map(lambda v: pct(v, 0)), labels={"segment": "", "v": ""}, title="Segments : poids dans la base vs dans le CA")
        fig.update_yaxes(tickformat=".0%"); fig.update_traces(textposition="outside")
        b.plotly_chart(style(fig, 380), width="stretch")
        st.caption("VIP = top 10 % du CA et ≥ 3 commandes · Fidèles = ≥ 3 commandes · Occasionnels = 2 commandes · Nouveaux = 1 commande")
        st.markdown("**Top 10 clients**")
        top = cs.head(10)[["id_client", "nb_commandes", "ca_net", "profit_net", "ville_principale", "canal_acquisition", "segment"]]
        st.dataframe(top.style.format({"ca_net": "{:,.0f}", "profit_net": "{:,.0f}"}), width="stretch", hide_index=True)
        risque = clients[clients["a_risque"]].sort_values("ca_net", ascending=False)[["id_client", "nb_commandes", "ca_net", "jours_inactivite", "canal_acquisition", "segment"]]
        with st.expander(f"Clients à risque à réactiver ({len(risque)})"):
            st.dataframe(risque.style.format({"ca_net": "{:,.0f}"}), width="stretch", hide_index=True)
            st.download_button("Télécharger la liste (CSV)", risque.to_csv(index=False).encode("utf-8-sig"), "clients_a_risque.csv", "text/csv")

# ============================================================================= RECOMMANDATIONS
with tabs[5]:
    st.subheader("5 recommandations stratégiques")
    st.caption("Chiffrées sur la période et le périmètre complets (filtres ignorés), avec vos hypothèses de coût d'achat.")
    mk_all = ap.agg_dimension(df_all, "canal_marketing")
    reco = pd.DataFrame([
        ["1. Corriger les annulations à Douala", f"{pct(rap['r1']['taux_douala'])} d'annulations vs {pct(rap['r1']['taux_ref'])} ailleurs ({kfmt(rap['r1']['ca_annule'])} UM perdus)",
         "Audit opérationnel sous 30 jours (stock, livraison, confirmation, paiement)", "Annulation Douala < 3 %", rap["r1"]["impact"]],
        ["2. Réduire les retours Électronique", f"{pct(rap['r2']['taux'])} de retours ({kfmt(rap['r2']['ca_rembourse'])} UM remboursées)",
         "Qualité fournisseurs, fiches produit, contrôle avant expédition, motif de retour", f"Retours ≤ {pct(rap['r2']['cible'], 0)}", rap["r2"]["impact"]],
        ["3. Réallouer le marketing", f"Instagram {pct(mk_all.loc['Instagram Ads', 'cout_marketing'] / mk_all['cout_marketing'].sum(), 0)} du budget, ROI profit {nf(mk_all.loc['Instagram Ads', 'roi_profit'], 1)} vs Google {nf(mk_all.loc['Google Ads', 'roi_profit'], 1)}",
         "25 % d'Instagram+Influenceur → Google Ads par paliers testés ; Email/CRM ; Influenceur à la performance", f"Arrêt si efficacité Google < {pct(rap['r3']['seuil_efficacite'], 0)} de sa moyenne", rap["r3"]["impact"]],
        ["4. Prioriser Maison, redresser Mode", f"Maison {pcs(rap['r4']['maison_t4_t3'])} au T4, Mode {pcs(rap['r4']['mode_t4_t3'])}",
         "Stock/campagnes Maison pour le pic nov-déc, ventes croisées, diagnostic Mode", "Mode revient au niveau T3", rap["r4"]["impact"]],
        ["5. Programme de rétention", f"{rap['r5']['nb_un_achat']} clients à 1 achat, {rap['r5']['nb_risque']} à risque ({kfmt(rap['r5']['ca_risque'])} UM)",
         "Offre 2ᵉ achat sous 25 jours, réactivation J+60/J+90, programme VIP", "Récurrence 73 % → 78 %", rap["r5"]["impact"]],
    ], columns=["Recommandation", "Constat", "Action", "KPI cible", "Impact profit (UM, 6 mois)"])
    st.dataframe(reco.style.format({"Impact profit (UM, 6 mois)": "{:+,.0f}"}), width="stretch", hide_index=True)
    st.success(f"**Impact cumulé estimé : {nf(rap['total_impact'])} UM de profit sur 6 mois (+{rap['total_impact'] / rap['profit_base'] * 100:.0f} %)**, "
               f"soit ≈ {nf(2 * rap['total_impact'])} UM en année pleine, sans augmenter le budget total. Ordres de grandeur : voir hypothèses dans le notebook §7.")
    st.markdown("**Plan d'action** — **30 j** : audit Douala, revue qualité Électronique, suivi hebdo · **60 j** : 1er palier de réallocation (−10 % Instagram → Google), relances 2ᵉ achat/réactivation · **90 j** : programme VIP, ventes croisées Maison, plan stock Maison.")

# ============================================================================= QUALITÉ
with tabs[6]:
    st.subheader("Audit et nettoyage des données")
    st.markdown("Le fichier brut n'est jamais modifié. Chaque anomalie ci-dessous a été détectée à l'audit puis traitée dans `df_clean`.")
    audit = ap.audit_qualite(raw)
    st.dataframe(audit.style.format({"% du brut": "{:.2f} %"}), width="stretch", hide_index=True)
    a, b = st.columns(2)
    a.markdown("**Journal de nettoyage**")
    a.dataframe(journal, width="stretch", hide_index=True)
    b.markdown("**À retenir**")
    b.markdown("- **436 lignes « electronique »** étaient en réalité des produits Beauté/Mode/Maison (nom du produit et prix le prouvent) : reclassées.\n"
               "- **600 prix à −50** et 22 autres prix négatifs : imputés par la médiane du produit.\n"
               "- **600 quantités à 0** : supprimées. **600 remises à −10 %** : imputées par la médiane de la catégorie.\n"
               "- **100 doublons**, « Kinshassa », « retournée » : corrigés.")
    st.download_button("Télécharger df_clean (CSV)", df_all.to_csv(index=False).encode("utf-8-sig"), "df_clean_afrimarket.csv", "text/csv")
