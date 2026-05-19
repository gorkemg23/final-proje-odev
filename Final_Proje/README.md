# Final Proje - Mikroservis Tabanlı Grup Yönetim Sistemi

## Özellikler
- FastAPI ile REST API
- PostgreSQL (JSONB, Trigger, Procedure)
- RabbitMQ ile loglama ve RPC worker
- Redis cache
- Dosya yükleme (Word -> HTML dönüşümü)
- CRUD işlemleri (Create, Read, Update, Delete)
- 3 farklı grup (öğrenci, okul, işletme)

## Docker ile Çalıştırma

```bash
docker compose up -d --build