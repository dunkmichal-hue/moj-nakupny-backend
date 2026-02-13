import os, requests, json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List

# --- 1. ZÁKLADNÁ INICIALIZÁCIA ---
app = FastAPI()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

class SearchReq(BaseModel):
    items: List[str]
    city: str

# --- 2. AI MOZOG (GEMINI) ---
def volaj_gemini(items: List[str], mode: str):
    if not GEMINI_API_KEY:
        return {"error": "Chýba API kľúč"}
    
    zoznam = ", ".join(items)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    # Prompt vyžaduje od Gemini čistý JSON formát, aby ho frontend vedel spracovať
    prompt = f"""
    Si nákupný asistent Dunko pre mesto Skalica. 
    Používateľ chce nakúpiť: {zoznam}. Režim: {mode}.
    Vráť IBA čistý JSON objekt (nič iné!) v tomto formáte:
    {{
      "total_price": 0.0,
      "stores": {{
        "Tesco Skalica": [{{ "name": "názov", "price": 1.2, "category": "kategória" }}],
        "Lidl": [...],
        "Kaufland": [...]
      }}
    }}
    Ak je režim 'split', rozdeľ položky tam, kde sú najlacnejšie. Ak 'single', daj všetky do jedného obchodu, ktorý je celkovo najlacnejší.
    Použi svoje vedomosti o aktuálnych akciách pre február 2026.
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        # Vyčistenie textu od prípadných markdown značiek ```json
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        return {"error": str(e)}

# --- 3. TRASY (ROUTES) ---
@app.post("/compare")
async def compare(req: SearchReq, mode: str = "split"):
    # Dunko teraz namiesto DB volá priamo Gemini
    vysledok = volaj_gemini(req.items, mode)
    return vysledok

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Dunko AI Strategist</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: sans-serif; background: #f0f2f5; padding: 20px; text-align: center; }
                .card { background: white; padding: 25px; border-radius: 15px; max-width: 600px; margin: auto; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
                textarea { width: 100%; height: 80px; padding: 10px; border-radius: 10px; border: 1px solid #ddd; margin-bottom: 10px; }
                .btn-box { display: flex; gap: 10px; margin-bottom: 20px; }
                button { flex: 1; padding: 12px; cursor: pointer; border-radius: 8px; border: none; font-weight: bold; background: #2563eb; color: white; }
                .btn-outline { background: white; color: #2563eb; border: 2px solid #2563eb; }
                .store-card { background: #fff; margin: 15px 0; padding: 15px; border-radius: 10px; border-left: 5px solid #2563eb; text-align: left; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
                .item { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #eee; }
                .tag { font-size: 10px; background: #e0e7ff; padding: 2px 6px; border-radius: 10px; margin-left: 5px; }
                input[type="checkbox"] { transform: scale(1.2); margin-right: 10px; }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🐕 Dunko Nákupný Zoznam (AI)</h2>
                <textarea id="list" placeholder="Napíš zoznam (napr. mäso, pečivo, pivo...)"></textarea>
                <div class="btn-box">
                    <button onclick="search('split')">Rozdelený nákup</button>
                    <button class="btn-outline" onclick="search('single')">Jeden obchod</button>
                </div>
                <div id="results"></div>
            </div>

            <script>
                async function search(mode) {
                    const input = document.getElementById('list').value;
                    const resDiv = document.getElementById('results');
                    if(!input) return;
                    
                    resDiv.innerHTML = "Dunko prehľadáva letáky... 🐾";
                    const items = input.split(',').map(i => i.trim());
                    
                    try {
                        const response = await fetch(`/compare?mode=${mode}`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({items: items, city: 'Skalica'})
                        });
                        const data = await response.json();
                        
                        let html = `<h3>Celková cena: ${data.total_price.toFixed(2)}€</h3>`;
                        for (const [store, prods] of Object.entries(data.stores)) {
                            if (prods.length === 0) continue;
                            html += `<div class="store-card"><b>📍 ${store}</b>`;
                            prods.forEach(p => {
                                html += `<div class="item">
                                    <span><input type="checkbox"> ${p.name} <span class="tag">${p.category}</span></span>
                                    <b>${p.price.toFixed(2)}€</b>
                                </div>`;
                            });
                            html += `</div>`;
                        }
                        resDiv.innerHTML = html;
                    } catch(e) {
                        resDiv.innerHTML = "Chyba: Gemini je preťažená alebo zlyhalo pripojenie.";
                    }
                }
            </script>
        </body>
    </html>
    """
