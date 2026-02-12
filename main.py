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

# Oprava pre Postgres (Render niekedy posiela 'postgres://', ale SQLAlchemy potrebuje 'postgresql://')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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

Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- POMOCNÉ FUNKCIE ---

def analyzuj_cez_gemini(text_z_ocr, obchod):
    """Použije Gemini AI na vyčistenie a štruktúrovanie dát z letáku."""
    if not GEMINI_API_KEY:
        return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
    Si nákupný asistent Dunko. Z textu letáku obchodu {obchod} vytiahni zoznam produktov.
    Vráť IBA čistý zoznam vo formáte: Názov produktu|Cena
    Ignoruj reklamy, omáčky a šum. Ak je tam akcia 1+1, vypočítaj cenu za kus.
    Text: {text_z_ocr}
    """
    
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
    <!DOCTYPE html>
    <html lang="sk">
    <head>
        <title>Dunko 2.0 - Inteligentný Nákup</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            :root { --primary: #2563eb; --secondary: #7c3aed; --bg: #f8fafc; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg); margin: 0; padding: 20px; color: #1e293b; }
            .container { max-width: 600px; margin: auto; background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }
            h2 { text-align: center; margin-bottom: 25px; color: #2563eb; }
            .settings { display: flex; gap: 10px; margin-bottom: 15px; }
            input, select, textarea { width: 100%; padding: 12px; border: 1px solid #e2e8f0; border-radius: 12px; font-size: 15px; box-sizing: border-box; }
            textarea { height: 100px; resize: none; margin-bottom: 15px; }
            .btn { width: 100%; padding: 15px; border: none; border-radius: 12px; font-weight: bold; cursor: pointer; color: white; margin-bottom: 10px; transition: 0.2s; }
            .btn-blue { background: var(--primary); }
            .btn-purple { background: var(--secondary); }
            .btn:hover { opacity: 0.9; transform: scale(0.99); }
            .shop-card { margin-top: 20px; border: 1px solid #e2e8f0; border-radius: 15px; overflow: hidden; background: #fff; }
            .shop-head { background: #f1f5f9; padding: 12px 15px; display: flex; justify-content: space-between; font-weight: bold; border-bottom: 1px solid #e2e8f0; }
            .prod-row { padding: 10px 15px; border-bottom: 1px solid #f8fafc; display: flex; justify-content: space-between; font-size: 14px; }
            .loader { text-align: center; display: none; padding: 20px; font-weight: bold; color: #2563eb; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🐕 Dunko 2.0 Porovnávač</h2>
            <div class="settings">
                <input type="text" id="city" placeholder="Mesto (napr. Skalica)" value="Skalica">
                <select id="radius"><option value="10">10 km</option><option value="20">20 km</option></select>
            </div>
            <textarea id="list" placeholder="Napíš zoznam (napr. pivo, maslo, mlieko...)"></textarea>
            <button class="btn btn-blue" onclick="search('multi')">KDE JE ČO NAJLACNEJŠIE?</button>
            <button class="btn btn-purple" onclick="search('single')">NAJLEPŠÍ NÁKUP V JEDNOM OBCHODE</button>
            <div id="loader" class="loader">Dunko beží do skladu pre letáky... 🐾</div>
            <div id="results"></div>
        </div>
        <script>
            async function search(mode) {
                const input = document.getElementById('list').value;
                if(!input) return;
                document.getElementById('loader').style.display = 'block';
                document.getElementById('results').innerHTML = '';
                
                const items = input.split(',').map(i => i.trim());
                try {
                    const res = await fetch('/compare', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items, city: document.getElementById('city').value})
                    });
                    const data = await res.json();
                    render(data.results, mode);
                } catch (e) { alert("Chyba spojenia!"); }
                document.getElementById('loader').style.display = 'none';
            }

            function render(results, mode) {
                const resultsDiv = document.getElementById('results');
                let byShop = {};

                results.forEach(r => {
                    if(r.matches && r.matches.length > 0) {
                        const m = r.matches[0];
                        if(!byShop[m.store]) byShop[m.store] = { items: [], total: 0 };
                        byShop[m.store].items.push(m);
                        byShop[m.store].total += m.price;
                    }
                });

                let html = '';
                for (const [shop, info] of Object.entries(byShop)) {
                    html += `<div class="shop-card"><div class="shop-head"><span>🏢 ${shop}</span><span>${info.total.toFixed(2)}€</span></div>`;
                    info.items.forEach(i => {
                        html += `<div class="prod-row"><span>${i.name}</span><b>${i.price.toFixed(2)}€</b></div>`;
                    });
                    html += '</div>';
                }
                resultsDiv.innerHTML = html || '<p style="text-align:center">Nenašli sa žiadne akcie.</p>';
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
            # Fuzzy match pre lepšie hľadanie (napr. "pivo" nájde "Pilsner pivo")
            if fuzz.partial_ratio(user_item.lower().strip(), p.name.lower()) > 80:
                matches.append(p)
        matches.sort(key=lambda x: x.price)
        results.append({"item": user_item, "matches": matches[:3]})
    return {"results": results}

@app.get("/update-flyers")
def update_flyers():
    """Funkcia, ktorá naplní databázu. Môžeš ju spustiť cez URL."""
    db = SessionLocal()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # Zoznam obchodov
    sources = [
        {"name": "Lidl", "url": "https://www.zlacnene.sk/obchod/lidl/"},
        {"name": "Kaufland", "url": "https://www.zlacnene.sk/obchod/kaufland/"},
        {"name": "Tesco", "url": "https://www.zlacnene.sk/obchod/tesco/"},
        {"name": "Billa", "url": "https://www.zlacnene.sk/obchod/billa/"}
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
                    try:
                        name = name_el.get_text(strip=True)
                        price = float(re.sub(r'[^\d.]', '', price_el.get_text(strip=True).replace(",", ".")))
                        
                        # Generovanie unikátneho ID
                        p_id = f"{src['name']}_{name}_{price}"[:100].replace(" ", "_")
                        
                        new_p = Product(id=p_id, name=name, price=price, store=src["name"])
                        db.merge(new_p)
                        added_count += 1
                    except: continue
        except: continue
    
    db.commit()
    db.close()
    return {"status": f"Úspešne pridaných {added_count} produktov do skladu!"}
