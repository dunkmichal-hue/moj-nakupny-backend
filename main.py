import os
import re
import requests
import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

# --- KONFIGURÁCIA ---
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Oprava pre Postgres: Render posiela 'postgres://', ale SQLAlchemy vyžaduje 'postgresql://'
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    # Render Postgres vyžaduje SSL šifrovanie
    if "?" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"

# Vytvorenie pripojenia k databáze
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DATABÁZOVÝ MODEL ---
class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String)
    price = Column(Float)
    store = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

# Automatické vytvorenie tabuliek pri štarte
Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- POMOCNÉ FUNKCIE ---

def analyzuj_cez_gemini(text_z_ocr, obchod):
    """Použije Gemini AI na vyčistenie dát z letáku."""
    if not GEMINI_API_KEY:
        return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Si Dunko. Z textu letáku {obchod} vytiahni: Názov produktu|Cena. Text: {text_z_ocr}"
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=15)
        raw_output = res.json()['candidates'][0]['content']['parts'][0]['text']
        vysledky = []
        for line in raw_output.strip().split('\n'):
            if '|' in line:
                n, c = line.split('|')
                try:
                    price_val = float(re.sub(r'[^\d.]', '', c.replace(',', '.')))
                    vysledky.append({"name": n.strip(), "price": price_val})
                except: continue
        return vysledky
    except Exception as e:
        print(f"Gemini Error: {e}")
        return []

# --- TRASY (ROUTES) ---

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Dunko 2.0</title>
            <meta charset="UTF-8">
            <style>
                body { font-family: sans-serif; padding: 20px; background: #f0f2f5; }
                .card { background: white; padding: 20px; border-radius: 15px; max-width: 500px; margin: auto; }
                button { width: 100%; padding: 10px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer; }
                .loader { display: none; color: blue; font-weight: bold; text-align: center; }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🐕 Dunko Porovnávač</h2>
                <textarea id="list" style="width:100%; height:100px;" placeholder="pivo, maslo..."></textarea><br><br>
                <button onclick="search()">POROVNAŤ CENY</button>
                <div id="loader" class="loader"><br>Dunko hľadá... 🐾</div>
                <div id="res"></div>
            </div>
            <script>
                async function search() {
                    const input = document.getElementById('list').value;
                    document.getElementById('loader').style.display = 'block';
                    const res = await fetch('/compare', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items: input.split(','), city: 'Skalica'})
                    });
                    const data = await res.json();
                    let html = '';
                    data.results.forEach(r => {
                        if(r.matches.length > 0) {
                            html += `<p><b>${r.item}:</b> ${r.matches[0].name} - ${r.matches[0].price}€ (${r.matches[0].store})</p>`;
                        }
                    });
                    document.getElementById('res').innerHTML = html || 'Nič sa nenašlo.';
                    document.getElementById('loader').style.display = 'none';
                }
            </script>
        </body>
    </html>
    """

class SearchReq(BaseModel):
    items: List[str]
    city: str

@app.post("/compare")
def compare(req: SearchReq):
    db = SessionLocal()
    all_prods = db.query(Product).all()
    db.close()
    results = []
    for user_item in req.items:
        matches = []
        for p in all_prods:
            if fuzz.partial_ratio(user_item.lower().strip(), p.name.lower()) > 80:
                matches.append(p)
        matches.sort(key=lambda x: x.price)
        results.append({"item": user_item, "matches": matches[:3]})
    return {"results": results}

@app.get("/update-flyers")
def update_flyers():
    db = SessionLocal()
    headers = {"User-Agent": "Mozilla/5.0"}
    sources = [
        {"name": "Lidl", "url": "https://www.zlacnene.sk/obchod/lidl/"},
        {"name": "Kaufland", "url": "https://www.zlacnene.sk/obchod/kaufland/"},
        {"name": "Tesco", "url": "https://www.zlacnene.sk/obchod/tesco/"}
    ]
    added_count = 0
    for src in sources:
        try:
            res = requests.get(src["url"], headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select(".polozka")
            for item in items:
                name_el = item.find(["h2", "h3"])
                price_el = item.select_one(".cena")
                if name_el and price_el:
                    name = name_el.get_text(strip=True)
                    price = float(re.sub(r'[^\d.]', '', price_el.get_text(strip=True).replace(",", ".")))
                    clean_name = re.sub(r'[^\w]', '_', name)
                    p_id = f"{src['name']}_{clean_name}_{price}"[:100]
                    db.merge(Product(id=p_id, name=name, price=price, store=src["name"]))
                    added_count += 1
        except: continue
    db.commit()
    db.close()
    return {"status": f"Pridaných {added_count} produktov!"}
