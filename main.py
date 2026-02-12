import os
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from rapidfuzz import fuzz
import re

app = FastAPI()

def is_match(user_item: str, found_item: str) -> bool:
    u, f = user_item.lower().strip(), found_item.lower().strip()
    if u in f or f in u: return True
    return fuzz.partial_ratio(u, f) > 75

def get_zlacnene_data(query: str):
    # Hľadáme na slovenskej verzii zlacnene.sk
    url = f"https://www.zlacnene.sk/hladaj/?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        products = []
        
        # Zlacnene.sk používa divy s triedou 'dila' alebo 'item'
        items = soup.find_all("div", class_="polozka") or soup.select(".vypis-akcii .item")
        
        for item in items:
            name_el = item.find("h2") or item.find("h3") or item.find(class_="nazov")
            price_el = item.find(class_="cena") or item.find(class_="price")
            shop_el = item.find(class_="obchod") or item.find(class_="shop")
            
            if name_el and price_el:
                name = name_el.get_text(strip=True)
                p_text = price_el.get_text(strip=True).replace(",", ".")
                
                try:
                    # Vytiahneme len čísla pre cenu
                    price_val = float(re.sub(r'[^\d.]', '', p_text))
                    store = shop_el.get_text(strip=True) if shop_el else "Akcia"
                    
                    products.append({
                        "name": name,
                        "price": price_val,
                        "store": store
                    })
                except: continue
        return products
    except:
        return []

@app.get("/", response_class=HTMLResponse)
def get_gui():
    return """
    <!DOCTYPE html>
    <html lang="sk">
    <head>
        <title>Dunko Porovnávač 2026</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #eef2f3; padding: 10px; }
            .main-card { background: white; max-width: 500px; margin: auto; padding: 20px; border-radius: 20px; shadow: 0 10px 25px rgba(0,0,0,0.1); }
            h2 { text-align: center; color: #2c3e50; margin-top: 0; }
            textarea { width: 100%; height: 80px; border-radius: 12px; border: 1px solid #ddd; padding: 10px; box-sizing: border-box; font-size: 16px; }
            .btn-go { width: 100%; background: #27ae60; color: white; padding: 15px; border: none; border-radius: 12px; font-weight: bold; cursor: pointer; margin-top: 10px; font-size: 16px; }
            .shop-group { background: #fff; margin-top: 15px; border-radius: 12px; border: 1px solid #dcdde1; overflow: hidden; }
            .shop-head { background: #2f3640; color: white; padding: 10px 15px; display: flex; justify-content: space-between; font-weight: bold; }
            .prod-row { padding: 10px 15px; border-bottom: 1px solid #f1f2f6; display: flex; justify-content: space-between; font-size: 14px; }
            .prod-row:last-child { border-bottom: none; }
            .loader { display: none; text-align: center; padding: 15px; font-weight: bold; color: #27ae60; }
        </style>
    </head>
    <body>
        <div class="main-card">
            <h2>🛒 Dunko Porovnávač</h2>
            <textarea id="list" placeholder="pivo, mlieko, kuracie prsia..."></textarea>
            <button class="btn-go" onclick="runSearch()">POROVNAŤ OBCHODY</button>
            <div id="loading" class="loader">Prehľadávam Zlacnene.sk... 🔍</div>
            <div id="results"></div>
        </div>
        <p style="text-align:center; color:#7f8c8d; font-size:12px;">Aktuálne dáta zo slovenských letákov</p>

        <script>
            async function runSearch() {
                const val = document.getElementById('list').value;
                if(!val) return;
                document.getElementById('loading').style.display = 'block';
                document.getElementById('results').innerHTML = '';

                const items = val.split(',').map(i => i.strip());
                try {
                    const res = await fetch('/compare', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items, city: "SR", radiusKm: 0})
                    });
                    const data = await res.json();
                    
                    const byShop = {};
                    data.results.forEach(r => {
                        if(r.matches.length > 0) {
                            const m = r.matches[0];
                            if(!byShop[m.store]) byShop[m.store] = { products: [], total: 0 };
                            byShop[m.store].products.push({ user: r.item, found: m.name, price: m.price });
                            byShop[m.store].total += m.price;
                        }
                    });

                    let html = '';
                    for (const [shop, info] of Object.entries(byShop)) {
                        html += `<div class="shop-group">
                            <div class="shop-head"><span>🏢 ${shop}</span><span>${info.total.toFixed(2)}€</span></div>`;
                        info.products.forEach(p => {
                            html += `<div class="prod-row"><span>${p.found}</span><b>${p.price.toFixed(2)}€</b></div>`;
                        });
                        html += `</div>`;
                    }
                    document.getElementById('results').innerHTML = html || "Žiadne akcie sa nenašli.";
                } catch(e) { alert("Chyba spojenia!"); }
                document.getElementById('loading').style.display = 'none';
            }
        </script>
    </body>
    </html>
    """

class Req(BaseModel):
    items: List[str]
    city: str
    radiusKm: int

@app.post("/compare")
def compare(data: Req):
    results = []
    for item in data.items:
        # Pre každú vec prehľadáme zlacnene.sk
        found = get_zlacnene_data(item)
        matches = [p for p in found if is_match(item, p["name"])]
        matches.sort(key=lambda x: x["price"])
        results.append({"item": item, "matches": matches})
    return {"results": results}
