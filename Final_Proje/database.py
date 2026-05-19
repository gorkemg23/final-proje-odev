import os
from sqlalchemy import create_engine, Column, Integer, DateTime, String, JSON, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secret@localhost:5432/finaldb")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class MasterTable(Base):
    __tablename__ = "master_table"

    id = Column(Integer, primary_key=True, index=True)
    group_type = Column(String, index=True)   # öğrenci, okul, işletme
    data = Column(JSON, nullable=False)       # JSONB alanı (içerik + status)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Log tablosu (trigger ile otomatik doldurulacak)
class LogTable(Base):
    __tablename__ = "log_table"
    id = Column(Integer, primary_key=True)
    table_name = Column(String)
    operation = Column(String)   # INSERT, UPDATE, DELETE
    record_id = Column(Integer)
    old_data = Column(JSON)
    new_data = Column(JSON)
    changed_at = Column(DateTime, default=datetime.utcnow)

# Trigger ve procedure oluşturma (bağlantı açılınca bir kere çalıştır)
def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        # Procedure: log_master_changes
        conn.execute(text("""
        CREATE OR REPLACE FUNCTION log_master_changes()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (TG_OP = 'DELETE') THEN
                INSERT INTO log_table (table_name, operation, record_id, old_data)
                VALUES ('master_table', 'DELETE', OLD.id, row_to_json(OLD));
                RETURN OLD;
            ELSIF (TG_OP = 'UPDATE') THEN
                INSERT INTO log_table (table_name, operation, record_id, old_data, new_data)
                VALUES ('master_table', 'UPDATE', NEW.id, row_to_json(OLD), row_to_json(NEW));
                RETURN NEW;
            ELSIF (TG_OP = 'INSERT') THEN
                INSERT INTO log_table (table_name, operation, record_id, new_data)
                VALUES ('master_table', 'INSERT', NEW.id, row_to_json(NEW));
                RETURN NEW;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """))

        # Trigger'ı oluştur (eğer yoksa)
        conn.execute(text("""
        DROP TRIGGER IF EXISTS master_audit_trigger ON master_table;
        CREATE TRIGGER master_audit_trigger
        AFTER INSERT OR UPDATE OR DELETE ON master_table
        FOR EACH ROW EXECUTE FUNCTION log_master_changes();
        """))
        conn.commit()

# İlk çağrıda tabloları ve trigger'ı oluştur
init_db()