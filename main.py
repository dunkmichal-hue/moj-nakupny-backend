import os, re, requests, datetime, time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, String, Float, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from bs4 import BeautifulSoup

# --- 1. INICIALIZÁCIA APP (MUSÍ BYŤ PRVÁ) ---
app = FastAPI()
Base = declarative_base()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- 2. SCHÉMY A MODELY ---
class SearchReq(BaseModel):
    items: List[str]
    city: str

class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String)
    price = Column(Float)
    store = Column(String)
    category = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

# --- 3. DATABÁZA A OPRAVA STĹPCA ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Vytvoríme tabuľky a následne poistka pre stĺpec category
Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE products ADD COLUMN category VARCHAR"))
        conn.commit()
    except Exception:
        pass # Ak už existuje, nič sa nedeje

# --- 4. POMOCNÉ FUNKCIE ---
def zisti_kategoriu(nazov):
    if not GEMINI_API_KEY: return "ostatné"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Zarď produkt '{nazov}' do 1 kategórie (mäso, pečivo, pivo, mliečne, ovocie, drogéria). Odpovedaj 1 slovom."
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=5)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().lower()
    except: return "ostatné"

# --- 5. TRASY (ROUTES) ---

@app.get("/update-flyers")
def update_flyers():
    db = SessionLocal()
    # Čistý stôl: vymažeme staré nekompletné záznamy
    db.query(Product).delete()
    db.commit()
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    sources = [
        {"name": "Tesco Skalica", "url": "https://www.tesco.sk/akciove-ponuky/akciove-produkty/tesco-hypermarket-skalica", "sel": ".product-list--list-item"},
        {"name": "Kaufland", "url": "https://predajne.kaufland.sk/aktualna-ponuka/prehlad.html", "sel": ".m-offer-tile"},
        {"name": "Lidl", "url": "https://www.lidl.sk/q/query/zlavy", "sel": ".product-grid__item"}
    ]
    
    added_total = 0
    for src in sources:
        try:
            res = requests.get(src["url"], headers=headers, timeout=12)
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select(src["sel"])
            
            for item in items[:25]:
                name_el = item.select_one("h2, h3, .product-title, .offer-tile__title")
                price_el = item.select_one(".price, .product-price, .offer-tile__price")
                
                if name_el and price_el:
                    name = name_el.get_text(strip=True)
                    price_raw = price_el.get_text(strip=True).replace(",", ".")
                    price = float(re.sub(r'[^\d.]', '', price_raw))
                    
                    # AI kategorizácia pre lepšie hľadanie
                    kat = zisti_kategoriu(name)
                    
                    p_id = f"{src['name']}_{abs(hash(name+str(price)))}"
                    db.add(Product(id=p_id, name=name, price=price, store=src["name"], category=kat))
                    added_total += 1
                    time.sleep(0.3)
            db.commit()
        except: continue
            
    db.close()
    return {"status": f"Dunko vyčistil databázu a nahral {added_total} nových akcií!"}

@app.post("/compare")
def compare(req: SearchReq):
    db = SessionLocal()
    q_items = [i.strip() for i in req.items if i.strip()]
    
    # Možnosť A: Rozdelený nákup (Najlacnejšie kúsky)
    split_data = {"stores": {}, "total": 0.0}
    for item in q_items:
        match = db.query(Product).filter((Product.name.ilike(f"%{item}%")) | (Product.category == item.lower())).order_by(Product.price).first()
        if match:
            if match.store not in split_data["stores"]: split_data["stores"][match.store] = []
            split_data["stores"][match.store].append({"n": match.name, "p": match.price, "c": match.category})
            split_data["total"] += match.price

    # Možnosť B: Jeden obchod (Pohodlie)
    single_data = {}
    for s in ["Tesco Skalica", "Kaufland", "Lidl"]:
        total, count, missing = 0.0, 0, []
        for item in q_items:
            m = db.query(Product).filter(Product.store == s).filter((Product.name.ilike(f"%{item}%")) | (Product.category == item.lower())).order_by(Product.price).first()
            if m:
                total += m.price
                count += 1
            else: missing.append(item)
        single_data[s] = {"total": round(total, 2), "count": count, "missing": missing}

    db.close()
    return {"split": split_data, "single": single_data}

@app.get("/", response_class=HTMLResponse)
async def home():
    # Tu zostáva tvoj HTML kód s tlačidlami
    return "..."
