import streamlit as st
# import sqlite3
import math
import pandas as pd
import folium
from streamlit_folium import folium_static
from datetime import datetime
from PIL import Image
import requests
import geocoder
from folium import IFrame
from streamlit_folium import st_folium
import base64
import psycopg2
from io import BytesIO
from pyxlsb import open_workbook as open_xlsb


authenticate = False
if authenticate:
    import streamlit_authenticator as Authenticate
    import yaml
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=yaml.SafeLoader)
    authenticator = Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
        config['preauthorized']
    )

    name, authentication_status, username = authenticator.login('Login', 'main')
    if authentication_status:
        authenticator.logout('Logout', 'main')
        st.write(f'Benvenuto *{name}*')
        st.title('Some content')
    elif authentication_status == False:
        st.error('Username/password Non sono corretti')
    elif authentication_status == None:
        st.warning('Please enter your username and password')

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
    
DB_PWD = st.secrets["db_password"]
class WasteCollectionDB:
    def __init__(self):
        # conn = psycopg2.connect(
        #     host="db.jvpsgftgvhkvxxachpew.supabase.co",
        #     database="postgres",
        #     user="postgres",
        #     password=DB_PWD,
        #     port="5432"
        # )
        self.conn_params = dict(host="aws-0-eu-central-1.pooler.supabase.com",
                                database="postgres",
                                user="postgres.jvpsgftgvhkvxxachpew",
                                password=DB_PWD,
                                port="6543",)
        self.init()
        
    def execute(self, query):
        conn = psycopg2.connect(**self.conn_params)
        c = conn.cursor()
        c.execute(query)
        conn.commit()
        conn.close()
    
    def execute_with_params(self, query, params):
        conn = psycopg2.connect(**self.conn_params)
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        conn.close()
    
    def init(self):
        self.execute('''CREATE TABLE IF NOT EXISTS collection_points (
                        id SERIAL PRIMARY KEY,
                        latitude REAL,
                        longitude REAL,
                        address TEXT,
                        username TEXT,
                        image BYTEA,
                        creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        size TEXT,
                        collected BOOLEAN DEFAULT FALSE,
                        notes TEXT)''')  

    def query(self, query="SELECT * FROM collection_points"):
        conn = psycopg2.connect(**self.conn_params)
        df = pd.read_sql_query(query, conn)
        conn.close()   
        return df   
    

db = WasteCollectionDB()
st.session_state.utente = "anonimo"

def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Sheet1')
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']
    format1 = workbook.add_format({'num_format': '0.00'}) 
    worksheet.set_column('A:A', None, format1)  
    writer.close()
    processed_data = output.getvalue()
    return processed_data

# Sidebar - Upload image
st.sidebar.header("Carica un'immagine")
uploaded_file = st.sidebar.file_uploader("Scegli immagine...", type=["jpg", "jpeg", "png"])

def insert_collection_point(latitude, longitude, user, img_blob, size_option, notes):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    address = get_address_from_coordinates(latitude, longitude)
    collected = False

    db.execute_with_params("INSERT INTO collection_points (latitude, longitude, address, username, image, creation_date, last_check, size, collected, notes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
              (latitude, longitude, address, user, img_blob, current_time, current_time, size_option, collected, notes))
    st.sidebar.success("Rifiuto aggiunto!")

if uploaded_file is not None:
    size_option = st.sidebar.selectbox("Dimensioni", ["Piccolo", "Medio", "Grande"])
    
    user = st.sidebar.text_input("Nome utente", value=st.session_state.utente)
    if user != "" and user != "anonimo":
        st.session_state.utente = user
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
        img_bytes = BytesIO()
        image.save(img_bytes, format='PNG')
        img_blob = img_bytes.getvalue()

        # Add button to insert collection point
        if st.sidebar.button("Aggiungi Rifiuto"):
            insert_collection_point(latitude, longitude, user, img_blob, size_option, notes)
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
css = '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">'
st.write(css, unsafe_allow_html=True)
# Main page - Show collection points


st.title("🗑️ Raccolta Rifiuti")
df = db.query()

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
    from folium import plugins
    st.subheader("Mappa")
    fg = folium.FeatureGroup(name="Rifiuti")
    marker_cluster = plugins.MarkerCluster().add_to(fg)
    m = folium.Map(location=[45.244, 8.034], zoom_start=12.5)
    # m = folium.Map(location=[45.236, 8.012], zoom_start=12.5)
    
    # folium.Marker(user_location, popup="La tua posizione", 
    #               icon=folium.Icon(color="blue", prefix='fa', icon='user')
    #               ).add_to(marker_cluster)
    for _, row in df.iterrows():
        img_data = base64.b64encode(row["image"]).decode()
        img_html = f'<img src="data:image/png;base64,{img_data}" width="150px">'
        popup_html = f"""
        <h3>{row['address']}</h3>
        <b>Dimensioni:</b> {row['size']}<br>
        <b>Raccolto:</b> <i class="fa-solid {'fa-circle-check' if row['collected'] else 'fa-circle-xmark'}" style="color: {'green' if row['collected'] else 'red'}"></i>
        <br>
        {f"<b>Note:</b> {row['notes']}<br>" if row['notes'] else ""}
        <b>Ultimo avvistamento:</b> {row['last_check'].strftime("%d/%m/%Y %H:%M")}<br>
        {img_html}
        """
        popup = folium.Popup(IFrame(popup_html, width=200, height=250), max_width=200)
        # fg.add_child(
        # folium.Marker(
        #     [row["latitude"], row["longitude"]], icon=icon_from_size(row["size"]),
        #     popup=popup
        # ))
        folium.Marker(
            [row["latitude"], row["longitude"]], icon=icon_from_size(row["size"]),
            popup=popup
        ).add_to(marker_cluster)
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

    # create a button do download the database as XLSX and the image as zip with all metadata
    st.download_button(
        label="Scarica Excel",
        data=to_excel(df.drop(columns=["image"])),
        file_name='Rifiuti.xlsx',
    )
    # create a zip file with all images
    import zipfile
    import os
    zip_file = BytesIO()
    with zipfile.ZipFile(zip_file, 'w') as zf:
        for index, row in df.iterrows():
            image = Image.open(BytesIO(row["image"]))
            image_path = f"image_{index}.png"
            image.save(image_path)
            zf.write(image_path, arcname=image_path)
            os.remove(image_path)  # Remove the file after adding to the zip
    zip_file.seek(0)  # Reset the pointer to the beginning of the BytesIO object
    # create a download button for the zip file
    st.download_button(
        label="Scarica ZIP",
        data=zip_file,
        file_name='collection_points.zip',
        mime='application/zip',
    )
    for index, row in df.iterrows():
        expander = st.expander(f"Punto {index+1}: {row.address}", expanded=False)
        with expander:
            # st.write(f"**Data:** {row['creation_date']}")

            st.html(f'''
                    <strong>Dimensioni:</strong> {row['size']}<br>
                    <strong>Ultima verifica:</strong> {row.last_check.strftime("%d/%m/%Y %H:%M")}<br>
                    <i class="fa-solid fa-user"></i> <em>{row.username}</em>''')

            
            
            collected = st.checkbox("Già raccolto", value=row['collected'], key=f"collected_{index}")
            # st.write(f"**Collected:** {row['collected']}")
            if row['notes']:
                st.write(f"**Note:** {row['notes']}")
            image = Image.open(BytesIO(row["image"]))
            st.image(image)

            if collected != row['collected']:
                db.execute(f"UPDATE collection_points SET collected = {collected} WHERE id = {row['id']}")
                st.success("Status aggiornato!")
            
            if st.button(f"È ancora lì?", key=f"update_{index}"):
                db.execute(f"UPDATE collection_points SET last_check = CURRENT_TIMESTAMP WHERE id = {row['id']}")
                st.success("Ultimo controllo aggiornato!")
