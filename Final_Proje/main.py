import os
import json
import pika
import mammoth
from fastapi import FastAPI, Request, Form, Depends, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from database import SessionLocal, MasterTable
import redis
from typing import List
import aiofiles
import magic

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Redis bağlantısı (isteğe bağlı cache)
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# RabbitMQ log gönderici (RPC beklemez, sadece log atar)
def send_log(group: str, action: str):
    try:
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
        channel = connection.channel()
        channel.queue_declare(queue='task_logs', durable=True)
        message = json.dumps({"group": group, "action": action})
        channel.basic_publish(exchange='', routing_key='task_logs', body=message)
        connection.close()
    except Exception as e:
        print(f"RabbitMQ Log Hatası: {e}")

# Ana sayfa
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Admin panel (grup bazlı)
@app.get("/admin/{group_type}", response_class=HTMLResponse)
def admin_panel(request: Request, group_type: str, db: Session = Depends(get_db)):
    # Redis cache kontrolü (opsiyonel)
    cache_key = f"admin_{group_type}"
    records_json = redis_client.get(cache_key)
    if records_json:
        records = [MasterTable(**json.loads(r)) for r in json.loads(records_json)]
    else:
        records = db.query(MasterTable).filter(MasterTable.group_type == group_type).all()
        # cache 30 saniye
        redis_client.setex(cache_key, 30, json.dumps([{"id": r.id, "data": r.data} for r in records]))
    send_log(group_type, "Panel görüntülendi")
    return templates.TemplateResponse("admin.html", {"request": request, "group": group_type, "records": records})

# Kaydet (CRUD Create)
@app.post("/save/{group_type}")
def save_record(group_type: str, content: str = Form(...), db: Session = Depends(get_db)):
    new_record = MasterTable(
        group_type=group_type,
        data={"content": content, "status": "active"}
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    send_log(group_type, f"Yeni kayıt eklendi: {content[:20]}")
    # Cache temizle
    redis_client.delete(f"admin_{group_type}")
    return {"status": "success", "message": "Kayıt JSONB olarak yüklendi!", "id": new_record.id}

# Sil (CRUD Delete)
@app.get("/delete/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(MasterTable).filter(MasterTable.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    group = record.group_type
    db.delete(record)
    db.commit()
    send_log(group, f"ID:{record_id} silindi")
    redis_client.delete(f"admin_{group}")
    return {"status": "deleted"}

# Güncelleme (CRUD Update)
@app.post("/update/{record_id}")
def update_record(record_id: int, content: str = Form(...), db: Session = Depends(get_db)):
    record = db.query(MasterTable).filter(MasterTable.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    record.data = {"content": content, "status": "updated"}
    db.commit()
    send_log(record.group_type, f"ID:{record_id} güncellendi: {content[:20]}")
    redis_client.delete(f"admin_{record.group_type}")
    return {"status": "updated"}

# Dosya yükleme analizi (Word -> HTML) + kısıtlama (izinli uzantılar)
ALLOWED_EXTENSIONS = {".txt", ".png", ".jpg", ".jpeg", ".pdf", ".docx", ".xlsx"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

@app.post("/upload-word/")
async def upload_word(file: UploadFile = File(...)):
    # Uzantı kontrolü
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen dosya türü. İzin verilenler: {ALLOWED_EXTENSIONS}")
    # Boyut kontrolü
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dosya boyutu 5MB'ı geçemez")
    
    # Sadece .docx için mammoth analizi, diğerleri için basit bilgi
    if ext == ".docx":
        try:
            from io import BytesIO
            result = mammoth.convert_to_html(BytesIO(content))
            html_output = result.value
            send_log("AI_Engine", f"Word analiz edildi: {file.filename}")
            return {"status": "Analiz Bitti", "html_preview": html_output[:1000]}
        except Exception as e:
            return {"status": "Hata", "details": str(e)}
    else:
        # Diğer dosyalar için sadece log tut
        send_log("AI_Engine", f"Dosya yüklendi (analiz yok): {file.filename} ({ext})")
        return {"status": "Dosya kabul edildi", "filename": file.filename, "size": len(content)}