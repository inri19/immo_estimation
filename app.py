import streamlit as st
import requests
import pandas as pd
import numpy as np
import psycopg2
from datetime import datetime
import os

st.set_page_config(page_title="EstimIA", layout="centered")

# -----------------------------
# FUNCTIONS
# -----------------------------

def geocode(adresse):
    url = f"https://api-adresse.data.gouv.fr/search/?q={adresse}"
    res = requests.get(url).json()
    if res["features"]:
        lon, lat = res["features"][0]["geometry"]["coordinates"]
        city = res["features"][0]["properties"]["city"]
        cp = res["features"][0]["properties"]["postcode"]
        return lat, lon, city, cp
    return None, None, None, None


def get_dvf(lat, lon):
    try:
        url = f"https://api.dvf.etalab.gouv.fr/api/geoapi/mutations/?lat={lat}&lon={lon}&dist=500"
        res = requests.get(url).json()

        prix_m2 = []
        for m in res.get("features", []):
            p = m["properties"]
            if p["surface_reelle_bati"] and p["valeur_fonciere"]:
                prix = p["valeur_fonciere"] / p["surface_reelle_bati"]
                if 500 < prix < 30000:
                    prix_m2.append(prix)

        if not prix_m2:
            return None

        return {
            "moyenne": int(np.mean(prix_m2)),
            "min": int(np.min(prix_m2)),
            "max": int(np.max(prix_m2)),
            "nb": len(prix_m2)
        }
    except:
        return None


def estimate(surface, type_bien, etat, dvf):
    prix_m2 = dvf["moyenne"] if dvf else 2000

    if type_bien == "Maison":
        prix_m2 += 300

    if "Neuf" in etat:
        prix_m2 += 500
    elif "rénover" in etat.lower():
        prix_m2 -= 400

    prix = int(surface * prix_m2)

    return prix, prix_m2


def save_lead(data):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        query = """
        INSERT INTO leads (
            date, adresse, ville, cp, surface,
            type, etat, email, tel, prix
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cur.execute(query, (
            data["date"],
            data["adresse"],
            data["city"],
            data["cp"],
            data["surface"],
            data["type"],
            data["etat"],
            data["email"],
            data["tel"],
            data["prix"]
        ))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("Erreur DB :", e)


# -----------------------------
# UI
# -----------------------------

st.title("🏠 Estimation Immobilière IA")
st.markdown("Obtenez une estimation fiable basée sur les ventes réelles (DVF)")

# -----------------------------
# FORMULAIRE
# -----------------------------

adresse = st.text_input("📍 Adresse du bien")

col1, col2 = st.columns(2)

with col1:
    surface = st.slider("Surface (m²)", 10, 300, 70)
    pieces = st.selectbox("Pièces", ["1", "2", "3", "4", "5+"])

with col2:
    type_bien = st.selectbox("Type", ["Appartement", "Maison"])
    etat = st.selectbox("État", ["À rénover", "Correct", "Bon état", "Neuf"])

st.markdown("### 📞 Recevoir l’estimation")
email = st.text_input("Email")
tel = st.text_input("Téléphone")

consent = st.checkbox("J'accepte d'être recontacté")

# -----------------------------
# BUTTON
# -----------------------------

if st.button("Estimer mon bien"):
    if not adresse or not email or not consent:
        st.error("Remplis les champs obligatoires")
    else:
        with st.spinner("Analyse du marché en cours..."):

            lat, lon, city, cp = geocode(adresse)

            if not lat:
                st.error("Adresse invalide")
            else:
                dvf = get_dvf(lat, lon)

                prix, prix_m2 = estimate(surface, type_bien, etat, dvf)

                # SAVE LEAD
                save_lead({
                    "date": datetime.now(),
                    "adresse": adresse,
                    "city": city,
                    "cp": cp,
                    "surface": surface,
                    "type": type_bien,
                    "etat": etat,
                    "email": email,
                    "tel": tel,
                    "prix": prix
                })

                # RESULT
                st.success("✅ Estimation prête")

                st.metric("💰 Prix estimé", f"{prix:,.0f} €".replace(",", " "))

                st.metric("📊 Prix au m²", f"{prix_m2} €/m²")

                if dvf:
                    st.info(f"""
📍 Données marché :
- Prix moyen : {dvf['moyenne']} €/m²  
- Fourchette : {dvf['min']} - {dvf['max']} €/m²  
- Transactions analysées : {dvf['nb']}
""")
                else:
                    st.warning("Peu de données dans cette zone")

                st.markdown("### 🤖 Analyse IA")
                st.write(f"""
Ce bien est estimé en fonction des ventes récentes à {city}.  
Le marché est {'dynamique' if dvf and dvf['nb'] > 20 else 'modéré'}.

Pour optimiser votre prix :
- Bon état → valorisation
- Surface cohérente avec le marché local
""")