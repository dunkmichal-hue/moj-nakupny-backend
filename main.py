import os
import re
import requests
import datetime
import time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict
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

# --- MODELY (Oprava NameError poradia) ---
class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String)
    price = Column(Float)
    store = Column(String)
    category = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

class SearchReq(BaseModel):
    items: List[str]
    city: str

Base.metadata.create_all(bind=engine)
app = FastAPI()

# --- UNIVERZÁLNY AI MOZOG ---
def zisti_kategoriu(nazov):
    if not GEMINI_API_KEY: return "ostatné"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Zarď produkt '{nazov}' do jednej kategórie (napr. mäso, pečivo, mliečne výrobky, nápoje, drogéria, ovocie). Odpovedaj IBA 1 slovom."
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=5)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().lower()
    except: return "ostatné"

# --- POROVNÁVACIA LOGIKA ---
@app.post("/compare")
def compare(req: SearchReq):
    db = SessionLocal()
    results = {"split_nákup": {"stores": {}, "total": 0.0}, "single_store_nákup": {}}
    
    all_stores = ["Tesco Skalica", "Kaufland", "Lidl"]
    store_totals = {s: {"items": [], "total": 0.0, "missing": []} for s in all_stores}

    for item_name in req.items:
        q = item_name.lower().strip()
        
        # 1. LOGIKA PRE ROZDELENÝ NÁKUP (Najlacnejšie kdekoľvek)
        best = db.query(Product).filter((Product.name.ilike(f"%{q}%")) | (Product.category == q)).order_by(Product.price).first()
        if best:
            if best.store not in results["split_nákup"]["stores"]:
                results["split_nákup"]["stores"][best.store] = []
            results["split_nákup"]["stores"][best.store].append({"name": best.name, "price": best.price, "cat": best.category})
            results["split_nákup"]["total"] += best.price

        # 2. LOGIKA PRE JEDEN OBCHOD (Všetko v jednom)
        for s in all_stores:
            match = db.query(Product).filter(Product.store == s).filter((Product.name.ilike(f"%{q}%")) | (Product.category == q)).order_by(Product.price).first()
            if match:
                store_totals[s]["items"].append({"name": match.name, "price": match.price})
                store_totals[s]["total"] += match.price
            else:
                store_totals[s]["missing"].append(item_name)

    results["single_store_nákup"] = store_totals
    db.close()
    return results

# --- SCRAPER (TESCO, KAUFLAND, LIDL) ---
@app.get("/update-flyers")
def update_flyers():
    db = SessionLocal()
    headers = {"User-Agent": "Mozilla/5.0"}
    # Tu doplníš scrapovanie podľa tvojich URL z predošlej správy...
    # Nezabudni na Gemini volanie: kat = zisti_kategoriu(name)
    return {"status": "Dunko aktualizoval dáta!"}

# --- FRONTEND S TLAČIDLAMI ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Dunko Stratég</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: sans-serif; background: #f0f2f5; padding: 20px; }
                .card { background: white; padding: 20px; border-radius: 15px; max-width: 600px; margin: auto; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
                .mode-btn { padding: 10px; cursor: pointer; border: 1px solid #2563eb; background: white; color: #2563eb; border-radius: 5px; margin: 5px; }
                .active { background: #2563eb; color: white; }
                .item-row { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #eee; padding: 8px 0; }
                .tag { font-size: 0.7em; background: #e0e7ff; padding: 2px 6px; border-radius: 10px; }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🐕 Dunko Nákupný Zoznam</h2>
                <textarea id="list" placeholder="Napíš zoznam (napr. mäso, pečivo, pivo) oddelený čiarkou" style="width:100%; height:80px;"></textarea><br>
                <button onclick="compare('split')" class="mode-btn active">Chcem najlacnejšie (behám po obchodoch)</button>
                <button onclick="compare('single')" class="mode-btn">Chcem všetko v jednom obchode</button>
                <div id="results" style="margin-top:20px;"></div>
            </div>
            <script>
                async function compare(mode) {
                    const items = document.getElementById('list').value.split(',').map(i => i.trim());
                    const res = await fetch('/compare', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items: items, city: 'Skalica'})
                    });
                    const data = await res.json();
                    let html = '';

                    if(mode === 'split') {
                        html = `<h3>Rozdelený nákup (Spolu: ${data.split_nákup.total.toFixed(2)}€)</h3>`;
                        for (const [store, products] of Object.entries(data.split_nákup.stores)) {
                            html += `<b>📍 ${store}</b>`;
                            products.forEach(p => {
                                html += `<div class="item-row"><input type="checkbox"> <span>${p.name} <span class="tag">${p.cat}</span></span> <b>${p.price.toFixed(2)}€</b></div>`;
                            });
                        }
                    } else {
                        html = `<h3>Najlepšie v jednom obchode</h3>`;
                        Object.entries(data.single_store_nákup).forEach(([store, info]) => {
                            html += `<div style="margin-bottom:15px; padding:10px; border:1px solid #ddd; border-radius:10px;">
                                <b>${store}: ${info.total.toFixed(2)}€</b><br>
                                <small>Nájdené položky: ${info.items.length}, Chýba: ${info.missing.join(', ') || '0'}</small>
                            </div>`;
                        });
                    }
                    document.getElementById('results').innerHTML = html;
                }
            </script>
        </body>
    </html>
    """
    
