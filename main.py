from fastapi import FastAPI, HTTPException
from datetime import datetime
import yfinance as yf
import urllib.request
import xml.etree.ElementTree as ET
import google.generativeai as genai
import json

app = FastAPI(title="Gemini Destekli Finansal Analiz API")

GOOGLE_API_KEY = "AIzaSyCJYrBExMl5U7B8jmj4V0t_-IC44uBz3S8" 
genai.configure(api_key=GOOGLE_API_KEY)

model = genai.GenerativeModel(
    'gemini-2.5-flash',
    generation_config={"response_mime_type": "application/json"}
)

def haber_verilerini_getir(hisse_kodu: str):
    """
    Hem Amerikan hem de Türk (BİST) hisselerini otomatik tanır.
    Hem İngilizce hem Türkçe haber araması yapar.
    """
    haber_basliklari = []
    hisse_kodu = hisse_kodu.upper()
    
    kodlar_denenecek = [hisse_kodu]
    if not hisse_kodu.endswith(".IS"):
        kodlar_denenecek.append(f"{hisse_kodu}.IS")
        
    for kod in kodlar_denenecek:
        try:
            hisse = yf.Ticker(kod)
            haberler = hisse.news
            if haberler:
                return [haber['title'] for haber in haberler]
        except Exception:
            continue 

    aramalar = [
        (f"{hisse_kodu}+hisse+haber", "hl=tr&gl=TR&ceid=TR:tr"), 
        (f"{hisse_kodu}+stock+news", "hl=en-US&gl=US&ceid=US:en") 
    ]
    
    for sorgu, dil_ayari in aramalar:
        try:
            url = f"https://news.google.com/rss/search?q={sorgu}&{dil_ayari}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req) as response:
                xml_data = response.read()
            
            root = ET.fromstring(xml_data)
            for item in root.findall('.//item'):
                haber_basliklari.append(item.find('title').text)
                if len(haber_basliklari) >= 15:
                    break
            
            if haber_basliklari:
                return haber_basliklari
        except Exception:
            continue
            
    return []

@app.get("/analiz/{hisse_kodu}")
async def hisse_analiz_et(hisse_kodu: str):
    haberler = haber_verilerini_getir(hisse_kodu)
    
    if not haberler:
        raise HTTPException(status_code=404, detail="Bu hisse için hiçbir kaynakta haber bulunamadı.")

    haber_metni = "\n".join(haberler)
    
    prompt = f"""
    Sen uzman bir Wall Street finansal analistisin. 
    Aşağıda '{hisse_kodu}' hissesine ait en güncel haber başlıkları verilmiştir:
    
    {haber_metni}
    
    Lütfen bu haberlerin şirketin geleceği üzerindeki genel duyarlılığını (sentiment) analiz et. 
    Sadece aşağıdaki yapıda, geçerli bir JSON döndür:
    {{
        "sayisal_skor": [Haberlerin geneli piyasa için çok olumsuz ise -1.0, çok olumlu ise 1.0, nötr ise 0.0 arasında ondalıklı bir sayı],
        "kullanici_raporu": "[Bu hisse için haberlerin genel durumunu özetleyen, yatırımcılar için 2-3 cümlelik profesyonel Türkçe bir piyasa raporu]"
    }}
    """

    try:
        response = model.generate_content(prompt)
        
        gemini_analizi = json.loads(response.text)
        
    except Exception as e:
        print(f"Gemini analiz hatası: {e}")
        raise HTTPException(status_code=500, detail="Yapay zeka analizi sırasında bir hata oluştu.")

    return {
        "hisse_kodu": hisse_kodu.upper(),
        "incelenen_haber_sayisi": len(haberler),
        "sayisal_skor": gemini_analizi.get("sayisal_skor", 0.0), 
        "kullanici_raporu": gemini_analizi.get("kullanici_raporu", "Rapor oluşturulamadı."),               
        "tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
