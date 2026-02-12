import os
import re
import requests
import datetime
import time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from bs4 import BeautifulSoup

# --- KONFIGURÁCIA ---
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL and "?" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODEL ---
class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String)
    price = Column(Float)
    store = Column(String)
    category = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)
app = FastAPI()

# --- AI KATEGORIZÁCIA ---
def zisti_kategoriu(nazov):
    if not GEMINI_API_KEY: return "ostatné"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Zarď produkt '{nazov}' do jednej kategórie (mäso, pivo, mliečne výrobky, ovocie, trvanlivé, drogéria). Ak je to akékoľvek mäso, napíš 'mäso'. Odpovedaj len 1 slovom."
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=5)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().lower()
    except: return "ostatné"

# --- TRASY ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head><title>Dunko Kompas</title><meta charset="UTF-8"></head>
        <body style="font-family:sans-serif; padding:20px; text-align:center; background:#f4f7f6;">
            <div style="background:white; padding:30px; border-radius:20px; max-width:500px; margin:auto; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <h2>🐕 Dunko + Kompas Zliav</h2>
                <input type="text" id="q" placeholder="Hľadaj napr. mäso" style="width:80%; padding:12px; border-radius:10px; border:1px solid #ddd;">
                <button onclick="search()" style="margin-top:10px; padding:10px 20px; background:#2563eb; color:white; border:none; border-radius:10px; cursor:pointer;">HĽADAŤ</button>
                <div id="r" style="margin-top:20px; text-align:left;"></div>
            </div>
            <script>
                async function search() {
                    const q = document.getElementById('q').value;
                    const rDiv = document.getElementById('r');
                    rDiv.innerHTML = "Dunko sliedi... 🐾";
                    const res = await fetch('/compare', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items: [q], city: 'Skalica'})
                    });
                    const data = await res.json();
                    let html = '';
                    data.results[0].matches.forEach(m => {
                        html += `<div style="border-bottom:1px solid #eee; padding:10px;">
                                    <b>${m.name}</b> (${m.store})<br>
                                    <span style="color:#2563eb; font-weight:bold;">${m.price.toFixed(2)}€</span> 
                                    <small style="background:#eee; padding:2px 5px; border-radius:5px;">${m.category}</small>
                                 </div>`;
                    });
                    rDiv.innerHTML = html || 'Nič sa nenašlo.';
                }
            </script>
        </body>
    </html>
    """

@app.post("/compare")
def compare(req: SearchReq):
    db = SessionLocal()
    q = req.items[0].lower().strip()
    matches = db.query(Product).filter(
        (Product.name.ilike(f"%{q}%")) | (Product.category == q)
    ).order_by(Product.price).all()
    db.close()
    return {"results": [{"item": q, "matches": matches}]}

@app.get("/update-flyers")
def update_flyers():
    db = SessionLocal()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    added_count = 0
    
    # DUNKO PREHĽADÁ PRVÝCH 5 STRÁNOK NA KOMPASZLIEV
    for page in range(1, 6):
        url = f"https://kompaszliav.sk/vsetky-akcie?page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200: break
            
            soup = BeautifulSoup(res.text, "html.parser")
            # Selektory pre KompasZliav (treba priebežne overovať)
            items = soup.select(".product-card, .item-list__item, .offer-card")
            
            if not items: break

            for item in items:
                name_el = item.select_one(".product-card__title, .offer-card__title, h3")
                price_el = item.select_one(".product-card__price, .offer-card__price, .price")
                store_el = item.select_one(".product-card__shop, .offer-card__shop-name")

                if name_el and price_el:
                    name = name_el.get_text(strip=True)
                    store = store_el.get_text(strip=True) if store_el else "Leták"
                    try:
                        price_str = price_el.get_text(strip=True).replace(",", ".")
                        price = float(re.sub(r'[^\d.]', '', price_str))
                        
                        kat = zisti_kategoriu(name)
                        p_id = f"kompas_{abs(hash(name+str(price)))}"
                        
                        db.merge(Product(id=p_id, name=name, price=price, store=store, category=kat))
                        added_count += 1
                        time.sleep(0.2)
                    except: continue
            db.commit()
        except: break
            
    db.close()
    return {"status": f"Dunko prečesal Kompas a roztriedil {added_count} produktov!"}

class SearchReq(BaseModel):
    items: List[str]
    city: str
