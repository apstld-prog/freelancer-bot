📦 DEPLOY ΟΔΗΓΙΕΣ - PeoplePerHour Proxy Service (με key 1211)

1️⃣ Ανέβασε το ZIP στο Render ως νέο Web Service.
   👉 https://render.com

2️⃣ Ρυθμίσεις:
   - Name: pph-proxy
   - Environment: Python 3.11
   - Build Command:
       pip install -r requirements.txt
   - Start Command:
       uvicorn app:app --host 0.0.0.0 --port 10000
   - Port: 10000

3️⃣ Μετά το deploy, δοκίμασε στο browser:
   https://<your-app-name>.onrender.com/api/pph?keyword=lighting&key=1211

4️⃣ Αν βλέπεις JSON αποτελέσματα (titles + URLs), δουλεύει σωστά ✅

5️⃣ Πήγαινε στο αρχείο του bot:
   platform_peopleperhour.py
   και άλλαξε:
       PROXY_URL = "https://<your-app-name>.onrender.com/api/pph"
       PROXY_KEY = "1211"

   και κάλεσε το έτσι:
       r = client.get(PROXY_URL, params={"keyword": kw, "limit": 10, "key": PROXY_KEY})
