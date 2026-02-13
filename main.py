import os, requests, json, re
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List

# 1. ŠTART A KONFIGURÁCIA (Oprava NameError)
app = FastAPI()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

class SearchReq(BaseModel):
    items: List[str]
    city: str

# 2. KOMUNIKÁCIA S GEMINI (Ošetrená proti chybám formátu)
def volaj_gemini(items: List[str], mode: str):
    if not GEMINI_API_KEY: return {"error": "Chýba API kľúč"}
    zoznam = ", ".join(items)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Si nákupný asistent Dunko pre Skalicu. Režim: {mode}. Používateľ chce: {zoznam}. Vráť LEN čistý JSON: {{\"total_price\": 10.0, \"stores\": {{\"Tesco Skalica\": [{{\"name\": \"tovar\", \"price\": 1.0, \"category\": \"kat\"}}], \"Lidl\": [], \"Kaufland\": []}}}}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        match = re.search(r'\{.*\}', raw_text, re.DOTALL) # Vyberie len JSON
        return json.loads(match.group() if match else raw_text)
    except: return {"error": "Nepodarilo sa spracovať dáta"}

# 3. LOGIKA A CESTY
@app.post("/compare")
async def compare(req: SearchReq, mode: str = "split"):
    return volaj_gemini(req.items, mode)

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
                .store-card { background: #fff; margin: 15px 0; padding: 15px; border-radius: 10px; border-left: 5px solid #2563eb; text-align: left; }
                .item { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #eee; }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🐕 Dunko AI Agent (Skalica)</h2>
                <textarea id="list" placeholder="Napíš zoznam (napr. maslo, mlieko, pivo)"></textarea>
                <div class="btn-box">
                    <button onclick="search('split')">Rozdelený nákup</button>
                    <button style="background:white; color:#2563eb; border:2px solid #2563eb;" onclick="search('single')">Jeden obchod</button>
                </div>
                <div id="results"></div>
            </div>
            <script>
                async function search(mode) {
                    const input = document.getElementById('list').value;
                    const resDiv = document.getElementById('results');
                    if(!input) return;
                    resDiv.innerHTML = "Dunko premýšľa... 🐾";
                    try {
                        const response = await fetch(`/compare?mode=${mode}`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({items: input.split(','), city: 'Skalica'})
                        });
                        const data = await response.json();
                        let html = `<h3>Celková cena: ${data.total_price.toFixed(2)}€</h3>`;
                        for (const [store, prods] of Object.entries(data.stores)) {
                            if (prods.length === 0) continue;
                            html += `<div class="store-card"><b>📍 ${store}</b>`;
                            prods.forEach(p => {
                                html += `<div class="item"><span>${p.name}</span><b>${p.price.toFixed(2)}€</b></div>`;
                            });
                            html += `</div>`;
                        }
                        resDiv.innerHTML = html;
                    } catch(e) { resDiv.innerHTML = "Chyba pripojenia."; }
                }
            </script>
        </body>
    </html>
    """
