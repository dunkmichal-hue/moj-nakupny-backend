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

# --- ROZŠÍRENÉ SYNONYMÁ ---
SYNONYMS = {
    "kuracie prsia": ["kuracie prsné rezne", "kuracie prsia", "kuracie filety", "prsné rezne"],
    "mlieko": ["polotučné mlieko", "trvanlivé mlieko", "čerstvé mlieko", "mlieko 1,5%", "mlieko 3,5%"],
    "maslo": ["tradičné maslo", "viba maslo", "čerstvé maslo", "maslo 250g", "roztierateľný tuk"],
    "vajcia": ["vajíčka", "vajcia m", "vajcia l", "čerstvé vajcia", "podstielkové vajcia"],
    "pivo": ["pilsner", "zlatý bažant", "corgoň", "kozel", "svetlé pivo", "desiatka", "dvanástka"],
    "cukor": ["kryštálový cukor", "trstinový cukor", "práškový cukor"],
    "olej": ["slnečnicový olej", "repkový olej", "olivový olej"],
    "hrozno": ["hrozno biele", "hrozno červené", "hrozno tmavé"],
    "pomaranč": ["pomaranče", "pomaranč voľný"]
}

def is_match(user_item: str, flyer_item: str) -> bool:
    u, f = user_item.lower().strip(), flyer_item.lower().strip()
    # Priama zhoda
    if u in f or f in u: return True
    # Zhoda cez synonymá
    if u in SYNONYMS:
        for syn in SYNONYMS[u]:
            if syn in f or fuzz.partial_ratio(syn, f) > 80: return True
    # Fuzzy zhoda (preklepy)
    return fuzz.partial_ratio(u, f) > 85

def get_live_data():
    # ZMENA ZDROJA NA KUPI.SK - stabilnejší pre tento typ scrapovania
    url = "https://www.kupi.sk/zlavove-letaky" 
    # Poznámka: Kupi.sk vyžaduje User-Agent, inak nás zablokuje
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "sk-SK,sk;q=0.9"
    }
    
    try:
        # Skúsime hlavnú stránku s akciami
        res = requests.get("https://www.kupi.sk/akcie", headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        products = []
        
        # Selektory pre Kupi.sk
        items = soup.find_all(class_="product-item") or soup.find_all(class_="item")
        
        for item in items:
            name_el = item.find(class_="product-name") or item.find("h3") or item.find("strong")
            price_el = item.find(class_="price-value") or item.find(class_="current-price") or item.find(class_="price")
            shop_el = item.find(class_="shop-name") or item.find(class_="store-logo")
            
            if name_el and price_el:
                name = name_el.get_text(strip=True)
                # Vyčistenie ceny (napr. "1,29 €" -> 1.29)
                p_text = price_el.get_text(strip=True).replace(",", ".").replace("€", "")
                p_text = "".join(re.findall(r"[\d.]+", p_text))
                
                try:
                    price = float(p_text)
                    # Získanie názvu obchodu (ak je v obrázku, vezmeme 'alt')
                    store = "Akcia"
                    if shop_el:
                        img = shop_el.find("img")
                        store = img.get("alt") if img and img.get("alt") else shop_el.get_text(strip=True)
                    
                    products.append({"name": name, "price": price, "store": store})
                except: continue
        
        return products
    except Exception as e:
        print(f"Chyba pripojenia: {e}")
        return []

# --- FRONTEND ---
@app.get("/", response_class=HTMLResponse)
def get_gui():
    return """
    <!DOCTYPE html>
    <html lang="sk">
    <head>
        <title>Nákupný Asistent od Dunka</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: 'Segoe UI', sans-serif; padding: 15px; background: #f0f2f5; color: #333; max-width: 700px; margin: auto; }
            .container { background: white; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
            h2 { text-align: center; color: #1a1a1a; margin-bottom: 10px; }
            textarea { width: 100%; height: 120px; padding: 12px; border-radius: 12px; border: 1px solid #ddd; font-size: 16px; resize: none; box-sizing: border-box; background: #fff; }
            .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
            button { padding: 14px; border: none; border-radius: 12px; font-weight: bold; cursor: pointer; font-size: 14px; transition: 0.3s; }
            .btn-all { background: #007bff; color: white; grid-column: span 2; }
            .btn-single { background: #6f42c1; color: white; grid-column: span 2; }
            .btn-mic { background: #dc3545; color: white; }
            .btn-clear { background: #6c757d; color: white; }
            button:hover { opacity: 0.8; }
            .shop-section { margin-top: 20px; background: white; border-radius: 12px; border: 1px solid #e0e0e0; overflow: hidden; animation: fadeIn 0.5s; }
            .shop-header { background: #28a745; color: white; padding: 12px 15px; font-weight: bold; display: flex; justify-content: space-between; align-items: center; }
            .shop-header.single { background: #6f42c1; }
            .item-row { padding: 12px 15px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; }
            .item-row:last-child { border-bottom: none; }
            .item-row input[type="checkbox"] { margin-right: 15px; transform: scale(1.3); }
            .item-info { flex-grow: 1; }
            .item-name { font-size: 14px; color: #333; }
            .item-price { font-weight: bold; color: #d9534f; margin-left: 10px; }
            .strikethrough { text-decoration: line-through; opacity: 0.4; background: #f8f9fa; }
            footer { text-align: center; margin-top: 30px; color: #888; font-size: 0.9em; padding-bottom: 20px; }
            .loader { display: none; text-align: center; margin: 20px; font-weight: bold; color: #007bff; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🛒 Nákupný Asistent</h2>
            <textarea id="items" placeholder="Napr: mlieko, maslo, kuracie prsia, vajcia, pivo..."></textarea>
            
            <div class="controls">
                <button class="btn-all" onclick="search('multi')">KDE JE ČO NAJLACNEJŠIE?</button>
                <button class="btn-single" onclick="search('single')">NAJLEPŠÍ NÁKUP V JEDNOM OBCHODE</button>
                <button class="btn-mic" onclick="startVoice()">🎤 DIKTOVAŤ</button>
                <button class="btn-clear" onclick="clearAll()">🗑️ VYMAZAŤ</button>
            </div>

            <div id="loader" class="loader">Prehľadávam letáky (Kupi.sk)... 🔍</div>
            <div id="results"></div>
        </div>
        <footer>Created by <b>Dunko</b></footer>

        <script>
            const textarea = document.getElementById('items');
            window.onload = () => { textarea.value = localStorage.getItem('myList') || ''; };
            textarea.oninput = () => { localStorage.setItem('myList', textarea.value); };

            function clearAll() { if(confirm("Vymazať zoznam?")) { textarea.value = ''; localStorage.removeItem('myList'); document.getElementById('results').innerHTML = ''; } }

            function startVoice() {
                const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
                recognition.lang = 'sk-SK';
                recognition.onresult = (e) => { textarea.value += (textarea.value ? ', ' : '') + e.results[0][0].transcript; localStorage.setItem('myList', textarea.value); };
                recognition.start();
            }

            async function search(mode) {
                const input = textarea.value;
                if(!input) return alert("Zadaj aspoň jednu položku!");
                document.getElementById('loader').style.display = 'block';
                document.getElementById('results').innerHTML = '';

                try {
                    const items = input.split(',').map(i => i.trim()).filter(i => i.length > 0);
                    const res = await fetch('/compare', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items, city: "Skalica", radiusKm: 10})
                    });
                    const data = await res.json();
                    renderResults(data.results, mode);
                } catch (e) { document.getElementById('results').innerHTML = '<p style="color:red; text-align:center;">Chyba spojenia so serverom.</p>'; }
                document.getElementById('loader').style.display = 'none';
            }

            function renderResults(results, mode) {
                const byShop = {};
                let foundAnything = false;

                if (mode === 'multi') {
                    results.forEach(r => {
                        if(r.matches.length > 0) {
                            foundAnything = true;
                            const best = r.matches[0];
                            if(!byShop[best.store]) byShop[best.store] = { items: [], total: 0 };
                            byShop[best.store].items.push({ orig: r.item, found: best.name, price: best.price });
                            byShop[best.store].total += best.price;
                        }
                    });
                } else {
                    const shopScores = {};
                    results.forEach(r => {
                        r.matches.forEach(m => {
                            foundAnything = true;
                            if(!shopScores[m.store]) shopScores[m.store] = { count: 0, total: 0, items: [] };
                            shopScores[m.store].count++;
                            shopScores[m.store].total += m.price;
                            shopScores[m.store].items.push({ orig: r.item, found: m.name, price: m.price });
                        });
                    });
                    let winner = Object.keys(shopScores).sort((a,b) => shopScores[b].count - shopScores[a].count || shopScores[a].total - shopScores[b].total)[0];
                    if(winner) byShop[winner] = shopScores[winner];
                }

                let html = '';
                for (const [shop, info] of Object.entries(byShop)) {
                    html += `<div class="shop-section">
                        <div class="shop-header ${mode === 'single' ? 'single' : ''}">
                            <span>🏢 ${shop}</span>
                            <span>${info.total.toFixed(2)}€</span>
                        </div>`;
                    info.items.forEach(i => {
                        html += `
                        <div class="item-row">
                            <input type="checkbox" onclick="this.parentElement.classList.toggle('strikethrough')">
                            <div class="item-info">
                                <div class="item-name"><b>${i.orig}</b> <small style="color:#666">(${i.found})</small></div>
                            </div>
                            <div class="item-price">${i.price.toFixed(2)}€</div>
                        </div>`;
                    });
                    html += `</div>`;
                }
                document.getElementById('results').innerHTML = foundAnything ? html : '<p style="text-align:center; padding:20px;">Nenašli sa žiadne akcie pre váš zoznam. Skúste všeobecnejšie názvy (napr. "pivo" namiesto "pilsner").</p>';
            }
        </script>
    </body>
    </html>
    """

class SearchRequest(BaseModel):
    items: List[str]
    city: str
    radiusKm: int

@app.post("/compare")
def compare_prices(req: SearchRequest):
    live_products = get_live_data()
    results = []
    for user_item in req.items:
        # Hľadáme všetky zhody v dátach
        matches = [p for p in live_products if is_match(user_item, p["name"])]
        # Zoradíme od najlacnejšieho
        matches.sort(key=lambda x: x["price"])
        results.append({"item": user_item, "matches": matches})
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
