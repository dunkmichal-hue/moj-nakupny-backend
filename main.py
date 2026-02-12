import os
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from rapidfuzz import fuzz

app = FastAPI()

# --- SYNONYMÁ A MATCHING ---
SYNONYMS = {
    "kuracie prsia": ["kuracie prsné rezne", "kuracie prsia bez kosti", "kuracie filety", "kuracie rezne"],
    "mlieko": ["polotučné mlieko", "trvanlivé mlieko", "čerstvé mlieko", "mlieko 1,5%"],
    "maslo": ["tradičné maslo", "viba maslo", "čerstvé maslo", "maslo 250g"],
    "vajcia": ["vajíčka", "vajcia m", "vajcia l", "čerstvé vajcia"],
    "pivo": ["pilsner", "zlatý bažant", "corgoň", "kozel", "svetlé pivo"],
    "cukor": ["kryštálový cukor", "trstinový cukor"],
    "olej": ["slnečnicový olej", "repkový olej"]
}

def is_match(user_item: str, flyer_item: str) -> bool:
    u, f = user_item.lower().strip(), flyer_item.lower().strip()
    if u in f: return True
    if u in SYNONYMS:
        for syn in SYNONYMS[u]:
            if syn in f or fuzz.partial_ratio(syn, f) > 85: return True
    return fuzz.partial_ratio(u, f) > 85

def get_live_data():
    url = "https://www.akcneletaky.sk/akcie/"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        products = []
        for item in soup.select(".item-list .item"):
            name = item.select_one(".item__title")
            price_tag = item.select_one(".price")
            shop = item.select_one(".item__shop")
            if name and price_tag:
                p_text = price_tag.get_text(strip=True).replace("€", "").replace(",", ".").strip()
                try: price = float(p_text)
                except: price = 0.0
                products.append({
                    "name": name.get_text(strip=True),
                    "price": price,
                    "store": shop.get_text(strip=True) if shop else "Ostatné"
                })
        return products
    except: return []

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
            .shop-section { margin-top: 20px; background: white; border-radius: 12px; border: 1px solid #e0e0e0; overflow: hidden; }
            .shop-header { background: #28a745; color: white; padding: 12px 15px; font-weight: bold; display: flex; justify-content: space-between; align-items: center; }
            .shop-header.single { background: #6f42c1; }
            .item-row { padding: 12px 15px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; }
            .item-row input[type="checkbox"] { margin-right: 15px; transform: scale(1.3); }
            .item-info { flex-grow: 1; }
            .item-name { font-size: 14px; color: #333; }
            .item-price { font-weight: bold; color: #d9534f; margin-left: 10px; }
            .strikethrough { text-decoration: line-through; opacity: 0.5; }
            footer { text-align: center; margin-top: 30px; color: #888; font-size: 0.9em; padding-bottom: 20px; }
            .loader { display: none; text-align: center; margin: 20px; font-weight: bold; color: #007bff; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🛒 Nákupný Asistent</h2>
            <textarea id="items" placeholder="mlieko, maslo, kuracie prsia..."></textarea>
            <div class="controls">
                <button class="btn-all" onclick="search('multi')">KDE JE ČO NAJLACNEJŠIE? (Viac obchodov)</button>
                <button class="btn-single" onclick="search('single')">NAJLEPŠÍ NÁKUP V JEDNOM OBCHODE</button>
                <button class="btn-mic" onclick="startVoice()">🎤 DIKTOVAŤ</button>
                <button class="btn-clear" onclick="clearAll()">🗑️ VYMAZAŤ</button>
            </div>
            <div id="loader" class="loader">Hľadám v letákoch... 📑</div>
            <div id="results"></div>
        </div>
        <footer>Created by <b>Dunko</b></footer>
        <script>
            const textarea = document.getElementById('items');
            window.onload = () => { textarea.value = localStorage.getItem('myList') || ''; };
            textarea.oninput = () => { localStorage.setItem('myList', textarea.value); };
            function clearAll() { if(confirm("Naozaj vymazať zoznam?")) { textarea.value = ''; localStorage.removeItem('myList'); document.getElementById('results').innerHTML = ''; } }
            function startVoice() {
                const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
                recognition.lang = 'sk-SK';
                recognition.onresult = (event) => {
                    const text = event.results[0][0].transcript;
                    textarea.value += (textarea.value ? ', ' : '') + text;
                    localStorage.setItem('myList', textarea.value);
                };
                recognition.start();
            }
            async function search(mode) {
                const input = textarea.value;
                if(!input) return alert("Napíš zoznam!");
                document.getElementById('loader').style.display = 'block';
                document.getElementById('results').innerHTML = '';
                const items = input.split(',').map(i => i.trim());
                try {
                    const res = await fetch('/compare', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({items, city: "Skalica", radiusKm: 10})
                    });
                    const data = await res.json();
                    renderResults(data.results, mode);
                } catch (e) { alert("Chyba servera!"); }
                document.getElementById('loader').style.display = 'none';
            }
            function renderResults(results, mode) {
                const byShop = {};
                if (mode === 'multi') {
                    results.forEach(r => {
                        if(r.matches.length > 0) {
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
                            if(!shopScores[m.store]) shopScores[m.store] = { count: 0, total: 0, items: [] };
                            shopScores[m.store].count++;
                            shopScores[m.store].total += m.price;
                            shopScores[m.store].items.push({ orig: r.item, found: m.name, price: m.price });
                        });
                    });
                    let winnerShop = Object.keys(shopScores).sort((a,b) => shopScores[b].count - shopScores[a].count || shopScores[a].total - shopScores[b].total)[0];
                    if(winnerShop) byShop[winnerShop] = shopScores[winnerShop];
                }
                let html = '';
                for (const [shop, info] of Object.entries(byShop)) {
                    html += `<div class="shop-section"><div class="shop-header ${mode === 'single' ? 'single' : ''}"><span>🏢 ${shop}</span><span>${info.total.toFixed(2)}€</span></div>`;
                    info.items.forEach(i => {
                        html += `<div class="item-row"><input type="checkbox" onclick="this.parentElement.classList.toggle('strikethrough')"><div class="item-info"><div class="item-name"><b>${i.orig}</b> <small>(${i.found})</small></div></div><div class="item-price">${i.price.toFixed(2)}€</div></div>`;
                    });
                    html += `</div>`;
                }
                document.getElementById('results').innerHTML = html || '<p style="text-align:center; padding:20px;">Nenašli sa žiadne akcie.</p>';
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
        matches = [p for p in live_products if is_match(user_item, p["name"])]
        matches.sort(key=lambda x: x["price"])
        results.append({"item": user_item, "matches": matches})
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
