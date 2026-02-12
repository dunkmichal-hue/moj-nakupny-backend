import os
import re
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
from rapidfuzz import fuzz

# --- KONFIGURÁCIA ---
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODEL DATABÁZY ---
class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String)
    price = Column(Float)
    store = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- INTELIGENTNÝ MOZOG (GEMINI) ---
def spracuj_cez_gemini(surovy_text, obchod):
    if not GEMINI_API_KEY:
        return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Z nasledujúceho textu z letáku obchodu {obchod} vytiahni produkty. Vráť IBA zoznam v tvare 'Názov produktu|Cena'. Text: {surovy_text}"
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=10)
        odpoved = res.json()['candidates'][0]['content']['parts'][0]['text']
        vysledky = []
        for riadok in odpoved.strip().split('\n'):
            if '|' in riadok:
                n, c = riadok.split('|')
                try:
                    vysledky.append({"name": n.strip(), "price": float(re.sub(r'[^\d.]', '', c.replace(',', '.')))})
                except: continue
        return vysledky
    except:
        return []

# --- ROZHRANIE (HTML) ---
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="sk">
    <head>
        <title>Dunko 2.0 - Inteligentný Nákup</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            :root { --primary: #2563eb; --secondary: #7c3aed; --bg: #f8fafc; }
            body { font-family: sans-serif; background: var(--bg); margin: 0; padding: 20px; display: flex; justify-content: center; }
            .container { max-width: 600px; width: 100%; background: white; padding: 30px; border-radius: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
            h2 { text-align: center; color: #1e293b; }
            .settings { display: flex; gap: 10px; margin-bottom: 15px; }
            input, select, textarea { width: 100%; padding: 12px; border: 1px solid #e2e8f0; border-radius: 12px; font-size: 16px; box-sizing: border-box; }
            textarea { height: 100px; margin-bottom: 15px; }
            .btn { width: 100%; padding: 15px; border: none; border-radius: 12px; font-weight: bold; cursor: pointer; color: white; margin-bottom: 10px; transition: 0.3s; }
            .btn-blue { background: var(--primary); }
            .btn-purple { background: var(--secondary); }
            .btn-gray { background: #64748b; }
            .shop-card { margin-top: 20px; border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden; }
            .shop-head { background: #f1f5f9; padding: 10px 15px; display: flex; justify-content: space-between; font-weight: bold; }
            .prod-row { padding: 10px 15px; border-bottom: 1px solid #f8fafc; display: flex; justify-content: space-between; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🛒 Dunko 2.0</h2>
            <div class="settings">
                <input type="text" id="city" placeholder="Mesto" value="Skalica">
                <select id="radius"><option value="10">10 km</option><option value="20">20 km</option></select>
            </div>
            <textarea id="list" placeholder="pivo, mlieko, maslo..."></textarea>
            <button class="btn btn-blue" onclick="search('multi')">KDE JE ČO NAJLACNEJŠIE?</button>
            <button class="btn btn-purple" onclick="search('single')">NAJLEPŠÍ NÁKUP V JEDNOM OBCHODE</button>
            <div id="results"></div>
        </div>
        <script>
            async function search(mode) {
                const list = document.getElementById('list').value;
                if(!list) return;
                document.getElementById('results').innerHTML = '<p style="text-align:center">Dunko hľadá v sklade... 🐕</p>';
                
                const res = await fetch('/compare', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({items: list.split(','), city: document.getElementById('city').value})
                });
                const data = await res.json();
                render(data.results, mode);
            }

            function render(results, mode) {
                let html = '';
                const byShop = {};
                results.forEach(r => {
                    if(r.matches.length > 0) {
                        const m = r.matches[0];
                        if(!byShop[m.store]) byShop[m.store] = { items: [], total: 0 };
                        byShop[m.store].items.push(m);
                        byShop[m.store].total += m.price;
                    }
                });
                for (const [shop, info] of Object.entries(byShop)) {
                    html += `<div class="shop-card"><div class="shop-head"><span>${shop}</span><span>${info.total.toFixed(2)}€</span></div>`;
                    info.items.forEach(i => { html += `<div class="prod-row"><span>${i.name}</span><b>${i.price.toFixed(2)}€</b></div>`; });
                    html += '</div>';
                }
                document.getElementById('results').innerHTML = html || 'Nenašli sa žiadne akcie.';
            }
        </script>
    </body>
    </html>
    """

# --- API BODY ---
class SearchReq(BaseModel):
    items: List[str]
    city: str

@app.post("/compare")
def compare(req: SearchReq):
    db = SessionLocal()
    all_prods = db.query(Product).all()
    db.close()
    
    final_results = []
    for user_item in req.items:
        matches = []
        for p in all_prods:
            if fuzz.partial_ratio(user_item.lower().strip(), p.name.lower()) > 80:
                matches.append(p)
        matches.sort(key=lambda x: x.price)
        final_results.append({"item": user_item, "matches": matches[:3]})
    return {"results": final_results}

@app.get("/update-flyers")
def update_flyers():
    # Tu je základný zberač, ktorý môžeš rozširovať
    db = SessionLocal()
    # Simulácia zberu z viacerých zdrojov
    test_data = [
        Product(id="l1", name="Pivo Pilsner Urquell 0,5l", price=0.99, store="Lidl"),
        Product(id="k1", name="Pivo Pilsner Urquell 0,5l", price=1.09, store="Kaufland"),
        Product(id="t1", name="Mlieko čerstvé 1,5%", price=0.79, store="Tesco")
    ]
    for p in test_data:
        db.merge(p)
    db.commit()
    db.close()
    return {"status": "Sklad aktualizovaný!"}
