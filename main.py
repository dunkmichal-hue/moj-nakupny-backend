import os, requests, json, re
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List

app = FastAPI()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

class SearchReq(BaseModel):
    items: List[str]
    city: str

def volaj_gemini(items: List[str], mode: str):
    if not GEMINI_API_KEY:
        return {"error": "Chýba API kľúč"}
    
    zoznam = ", ".join(items)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    Si nákupný asistent Dunko. Používateľ chce kúpiť: {zoznam}. Mesto: Skalica. Režim: {mode}.
    Vráť IBA čistý JSON bez akýchkoľvek rečí okolo:
    {{
      "total_price": 10.5,
      "stores": {{
        "Tesco Skalica": [{{ "name": "názov", "price": 1.2, "category": "kategória" }}],
        "Lidl": [],
        "Kaufland": []
      }}
    }}
    Ak režim='split', daj veci tam, kde sú najlacnejšie. Ak 'single', daj všetko do 1 obchodu.
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        
        # EXTRÉMNE ČISTENIE: Nájdeme v texte iba to, čo je medzi { a }
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(raw_text)
    except Exception as e:
        print(f"Chyba Gemini: {e}")
        return {"error": "Zlý formát dát"}

@app.post("/compare")
async def compare(req: SearchReq, mode: str = "split"):
    return volaj_gemini(req.items, mode)

@app.get("/", response_class=HTMLResponse)
async def home():
    # Frontend zostáva, len v JS pridáme lepšiu chybu
    return """
    ... (tvoj predošlý HTML kód) ...
    <script>
        // V JS funkcií search pridaj tento riadok pre ladenie:
        // console.log("Data od Dunka:", data); 
    </script>
    """
