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

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL and "?" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- UPRAVENÝ MODEL (Pridaná kategória) ---
class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String)
    price = Column(Float)
    store = Column(String)
    category = Column(String) # Sem Dunko uloží napr. "mäso" alebo "pivo"
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- INTELIGENTNÉ ROZPOZNÁVANIE CEZ GEMINI ---
def zisti_kategoriu(nazov_produktu):
    """Gemini určí, do akej kategórie produkt patrí."""
    if not GEMINI_API_KEY:
        return "ostatné"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Napíš jedno slovo (všeobecnú kategóriu) pre tento produkt: '{nazov_produktu}'. Príklad: 'Bravčová krkovička' -> mäso, 'Zlatý Bažant' -> pivo, 'Rajo Maslo' -> maslo. Odpovedaj len tým jedným slovom v malom písme."
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=5)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().lower()
    except:
        return "ostatné"

# --- TRASY ---
@app.get("/", response_class=HTMLResponse)
async def home():
    # Frontend ostáva podobný, Dunko bude hľadať v názve aj kategórii
    return """ ... (tvoj HTML kód) ... """

class SearchReq(BaseModel):
    items: List[str]
    city: str

@app.post("/compare")
def compare(req: SearchReq):
    db = SessionLocal()
    results = []
    for user_item in req.items:
        search_term = user_item.lower().strip()
        # Dunko hľadá zhodu v NÁZVE alebo v KATEGÓRII
        matches = db.query(Product).filter(
            (Product.name.ilike(f"%{search_term}%")) | 
            (Product.category == search_term)
        ).order_by(Product.price).limit(5).all()
        results.append({"item": user_item, "matches": matches})
    db.close()
    return {"results": results}

@app.get("/update-flyers")
def update_flyers():
    db = SessionLocal()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
            # Opravené hľadanie produktov (hľadáme širšie spektrum prvkov)
            items = soup.select(".polozka, .produkt, [class*='item']") 
            
            for item in items:
                name_el = item.find(["h2", "h3", "h4"])
                price_el = item.select_one(".cena, [class*='price']")
                
                if name_el and price_el:
                    name = name_el.get_text(strip=True)
                    price_text = price_el.get_text(strip=True).replace(",", ".")
                    price = float(re.sub(r'[^\d.]', '', price_text))
                    
                    # DUNKO AKTIVUJE MOZOG (Gemini)
                    kategoria = zisti_kategoriu(name)
                    
                    p_id = f"{src['name']}_{name}_{price}"[:100]
                    db.merge(Product(id=p_id, name=name, price=price, store=src["name"], category=kategoria))
                    added_count += 1
        except Exception as e:
            print(f"Chyba pri {src['name']}: {e}")
            continue
            
    db.commit()
    db.close()
    return {"status": f"Dunko inteligentne roztriedil {added_count} produktov!"}
