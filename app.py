import streamlit as st
import sqlite3
import math
import pandas as pd
import folium
from streamlit_folium import folium_static
from datetime import datetime
from PIL import Image
import requests
import geocoder
import io
from folium import IFrame
from streamlit_folium import st_folium
import base64

# Function to get address from coordinates
def get_address_from_coordinates(lat, lon):
    headers = {
        "User-Agent": "YourAppName/1.0 (contact@yourdomain.com)",  # Ensure this is a valid identifier
        "Referer": "https://yourwebsite.com"  # Add a Referer if necessary (your app's URL)
    }
    try:
        response = requests.get(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&addressdetails=1&format=json", headers=headers)
        data = response.json()
        return data.get("name", "Unknown Location")
    except Exception as e:
        return "Unknown Location"
    
# Database setup
def init_db():
    conn = sqlite3.connect("collection_points.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS collection_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    latitude REAL,
                    longitude REAL,
                    address TEXT,
                    image BLOB,
                    creation_date TEXT,
                    last_check TEXT,
                    size TEXT,
                    collected BOOLEAN,
                    notes TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Sidebar - Upload image
st.sidebar.header("Carica un'immagine")
uploaded_file = st.sidebar.file_uploader("Scegli immagine...", type=["jpg", "jpeg", "png"])

def insert_collection_point(latitude, longitude, img_blob, size_option, notes):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    address = get_address_from_coordinates(latitude, longitude)
    collected = False
    conn = sqlite3.connect("collection_points.db")
    c = conn.cursor()
    c.execute("INSERT INTO collection_points (latitude, longitude, address, image, creation_date, last_check, size, collected, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (latitude, longitude, address, img_blob, current_time, current_time, size_option, collected, notes))
    conn.commit()
    conn.close()
    st.sidebar.success("Rifiuto aggiunto!")

if uploaded_file is not None:
    size_option = st.sidebar.selectbox("Dimensioni", ["Piccolo", "Medio", "Grande"])
    # collected = st.sidebar.checkbox("Già raccolto", value=False)
    notes = st.sidebar.text_area("Note")

    image = Image.open(uploaded_file)
    exif_data = image._getexif()
    
    if exif_data and 34853 in exif_data:  # GPS Info exists
        gps_info = exif_data[34853]
        lat_ref = gps_info[1]
        lat = gps_info[2]
        lon_ref = gps_info[3]
        lon = gps_info[4]
        
        def convert_to_degrees(value):
            d, m, s = value
            return d + (m / 60.0) + (s / 3600.0)
        
        latitude = convert_to_degrees(lat)
        if lat_ref != "N":
            latitude = -latitude
        
        longitude = convert_to_degrees(lon)
        if lon_ref != "E":
            longitude = -longitude
        
        # Convert image to blob, reshaping it if greater than 480px of width
        if image.width > 480:
            image = image.resize((480, int(480 * image.height / image.width)))
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_blob = img_bytes.getvalue()

        # Add button to insert collection point
        if st.sidebar.button("Aggiungi Rifiuto"):
            insert_collection_point(latitude, longitude, img_blob, size_option, notes)
    else:
        st.sidebar.error("Ness GPS metadata found in the image!")

# Get user location every 2 minutes
@st.cache_data(ttl=120)
def get_user_location():
    return [45.236, 8.012]  # Default to Saluggia

    g = geocoder.ip("me")
    if g.latlng:
        return g.latlng
    return [45.236, 8.012]  # Default to Saluggia

user_location = get_user_location()
# Main page - Show collection points
st.title("🗑️ Raccolta Rifiuti")
conn = sqlite3.connect("collection_points.db")
df = pd.read_sql_query("SELECT * FROM collection_points", conn)
conn.close()

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of the Earth in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c  # Distance in kilometers

df["distance"] = df.apply(lambda row: calculate_distance(user_location[0], user_location[1], row["latitude"], row["longitude"]), axis=1)
df = df.sort_values("distance")

st.subheader("Filtri")
selected_size = st.selectbox("Filtra per dimensione", ["Tutte", "Piccolo", "Medio", "Grande"], index=0)
show_collected = st.checkbox("Mostra solo i già raccolti", value=False)

# Apply filters
if selected_size != "Tutte":
    df = df[df["size"] == selected_size]
if show_collected:
    df = df[df["collected"] == 1]

# Layout with two columns
tab1, tab2 = st.tabs(["Mappa", "Lista punti"])

# Column 1 - Display Map centered in Saluggia (VC), Italy

def icon_from_size(size):
    if size == "Piccolo":
        return folium.Icon(color="darkgreen", prefix='fa', icon="sack-xmark")
    if size == "Medio":
        return folium.Icon(color="orange", prefix='fa', icon="dumpster")
    if size == "Grande":
        return folium.Icon(color="darkred", prefix='fa', icon="truck")
    
with tab1:
    st.subheader("Mappa")
    fg = folium.FeatureGroup(name="Rifiuti")
    m = folium.Map(location=[45.236, 8.012], zoom_start=13.5)
    fg.add_child(folium.Marker(user_location, popup="La tua posizione", 
                  icon=folium.Icon(color="blue", prefix='fa', icon='user')
                  ))
    for _, row in df.iterrows():
        img_data = base64.b64encode(row["image"]).decode()
        img_html = f'<img src="data:image/png;base64,{img_data}" width="150px">'
        popup_html = f"""
        <h3>{row['address']}</h3>
        <b>Dimensioni:</b> {row['size']}<br>
        <b>Collected:</b> {row['collected']}<br>
        {f"<b>Notes:</b> {row['notes']}<br>" if row['notes'] else ""}
        <b>Last Check:</b> {row['last_check']}<br>
        {img_html}
        """
        popup = folium.Popup(IFrame(popup_html, width=200, height=250), max_width=200)
        fg.add_child(
        folium.Marker(
            [row["latitude"], row["longitude"]], icon=icon_from_size(row["size"]),
            popup=popup
        ))
    # print len of fg children
    # folium_static(m)
    out = st_folium(
        m,
        feature_group_to_add=fg,
        # center=center,
        width=1200,
        height=600,
    )




# Column 2 - Clickable list
with tab2:
    st.subheader("Punti da raccogliere")
    for index, row in df.iterrows():
        expander = st.expander(f"Punto {index+1}: {row['address']}", expanded=False)
        with expander:
            # st.write(f"**Data:** {row['creation_date']}")
            st.write(f"**Dimensioni:** {row['size']}")
            st.write(f"**Ultima verifica:** {row['last_check']}")
            collected = st.checkbox("Già raccolto", value=row['collected'], key=f"collected_{index}")
            # st.write(f"**Collected:** {row['collected']}")
            if row['notes']:
                st.write(f"**Note:** {row['notes']}")
            image = Image.open(io.BytesIO(row["image"]))
            st.image(image)

            if collected != row['collected']:
                conn = sqlite3.connect("collection_points.db")
                c = conn.cursor()
                c.execute("UPDATE collection_points SET collected = ? WHERE id = ?", (collected, row['id']))
                conn.commit()
                conn.close()
                st.success("Status aggiornato!")
            
            if st.button(f"È ancora lì?", key=f"update_{index}"):
                conn = sqlite3.connect("collection_points.db")
                c = conn.cursor()
                new_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("UPDATE collection_points SET last_check = ? WHERE id = ?", (new_time, row['id']))
                conn.commit()
                conn.close()
                st.success("Ultimo controllo aggiornato!")
