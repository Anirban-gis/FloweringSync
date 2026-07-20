# 🌾 FloweringSync — Web App

Flowering Synchronisation Analysis Tool  
*Isolation vs. Surrounding Plot Flowering Overlap*  
Developed by **Anirban Das**

---

## Files in this project

```
FloweringSync/
├── app.py               ← Streamlit web interface (NEW — replaces gui.py)
├── analysis.py          ← Core analysis engine (UNCHANGED)
├── spatial.py           ← Spatial indexing & distance (UNCHANGED)
├── utils.py             ← Date parsing helpers (UNCHANGED)
├── excel_export.py      ← Excel writer (UNCHANGED)
├── shapefile_export.py  ← Shapefile exporter (UNCHANGED)
├── requirements.txt     ← Python dependencies
├── render.yaml          ← Render.com deployment config
└── .gitignore
```

---

## Deploying to GitHub + Render (step by step)

### Step 1 — Create GitHub repo

1. Go to https://github.com and sign in.
2. Click **New repository**.
3. Name it `FloweringSync`, set it to **Public** (or Private).
4. Click **Create repository**.

### Step 2 — Push this folder to GitHub

Open a terminal inside this folder and run:

```bash
git init
git add .
git commit -m "Initial commit — FloweringSync web app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/FloweringSync.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

### Step 3 — Deploy on Render

1. Go to https://render.com and **Sign in with GitHub**.
2. Click **New → Web Service**.
3. Click **Connect** next to the `FloweringSync` repository.
4. Fill in these settings:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
   - **Plan:** Free
5. Click **Create Web Service**.

Render will build and deploy your app. After a few minutes you'll get a URL like:

```
https://floweringsync.onrender.com
```

Anyone with that URL can use your app — no installation needed.

---

## How users use the app

1. Open the URL in any browser.
2. Upload Isolation shapefile (all parts: `.shp .dbf .shx .prj`).
3. Upload Surrounding shapefile (same).
4. Click **Load Shapefiles**.
5. Go to **Setup** tab — map the columns (ID, Crop, Start, End).
6. Set Distance limit and method.
7. Go to **Run Analysis** tab → click **RUN ANALYSIS**.
8. Go to **Results** tab → download Excel and/or Shapefile.

---

## Local development

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.
