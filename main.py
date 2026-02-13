@app.get("/update-flyers")
def update_flyers():
    db = SessionLocal()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 1. KROK: VYMAZANIE STARÝCH AKCIÍ (Čistý stôl)
    try:
        db.query(Product).delete()
        db.commit()
        print("Staré akcie vymazané.")
    except Exception as e:
        print(f"Chyba pri mazaní: {e}")
        db.rollback()

    sources = [
        {"name": "Tesco Skalica", "url": "https://www.tesco.sk/akciove-ponuky/akciove-produkty/tesco-hypermarket-skalica", "sel": ".product-list--list-item"},
        {"name": "Kaufland", "url": "https://predajne.kaufland.sk/aktualna-ponuka/prehlad.html", "sel": ".m-offer-tile"},
        {"name": "Lidl", "url": "https://www.lidl.sk/q/query/zlavy", "sel": ".product-grid__item"}
    ]
    
    added_count = 0
    for src in sources:
        try:
            res = requests.get(src["url"], headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select(src["sel"])
            
            for item in items[:30]: # Limit 30 produktov na obchod pre stabilitu
                name_el = item.select_one("h2, h3, .product-title, .offer-tile__title")
                price_el = item.select_one(".price, .product-price, .offer-tile__price")
                
                if name_el and price_el:
                    name = name_el.get_text(strip=True)
                    price_text = price_el.get_text(strip=True).replace(",", ".")
                    # Vyčistenie ceny (odstránenie meny a pod.)
                    price = float(re.sub(r'[^\d.]', '', price_text))
                    
                    # AI URČÍ KATEGÓRIU (mäso, pečivo, atď.)
                    kat = zisti_kategoriu(name)
                    
                    p_id = f"{src['name']}_{abs(hash(name+str(price)))}"
                    new_product = Product(id=p_id, name=name, price=price, store=src["name"], category=kat)
                    db.add(new_product)
                    added_count += 1
                    time.sleep(0.4) # Pauza pre Gemini API a ochranu pred banom
            db.commit()
        except Exception as e:
            print(f"Chyba pri sťahovaní z {src['name']}: {e}")
            
    db.close()
    return {"status": f"Dunko vyčistil databázu a nanovo nahral {added_count} aktuálnych akcií!"}
