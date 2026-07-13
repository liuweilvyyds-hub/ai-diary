import os
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import sqlalchemy

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'diary.db')}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def column_exists(table_name, column_name):
    insp = sqlalchemy.inspect(engine)
    cols = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in cols

class DiaryEntry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), default="")
    content = Column(Text, nullable=False)
    mood = Column(String(50), default="")
    mood_score = Column(Float, default=0.0)
    keywords = Column(JSON, default=list)
    summary = Column(Text, default="")
    images = Column(JSON, default=list)
    evidence = Column(JSON, default=dict)
    author = Column(String(50), default="user")
    weather = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    app_name = Column(String(200), default="")
    window_title = Column(Text, default="")
    started_at = Column(DateTime, default=datetime.datetime.now, index=True)
    ended_at = Column(DateTime, default=datetime.datetime.now, index=True)
    duration_seconds = Column(Integer, default=0)
    source = Column(String(50), default="window")
    note = Column(Text, default="")

class PersonalMemory(Base):
    __tablename__ = "personal_memories"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(80), default="general", index=True)
    content = Column(Text, nullable=False)
    source = Column(String(80), default="manual")
    confidence = Column(Float, default=1.0)
    pinned = Column(Integer, default=0)
    active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), unique=True, index=True)
    summary = Column(Text, default="")
    highlights = Column(JSON, default=list)
    categories = Column(JSON, default=list)
    top_apps = Column(JSON, default=list)
    events = Column(JSON, default=list)
    dayparts = Column(JSON, default=list)
    total_seconds = Column(Integer, default=0)
    source = Column(String(50), default="activity")
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Migration: add weather column if not exists
if not column_exists("entries", "weather"):
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("ALTER TABLE entries ADD COLUMN weather VARCHAR(50) DEFAULT ''"))
        conn.commit()

if not column_exists("entries", "evidence"):
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("ALTER TABLE entries ADD COLUMN evidence JSON DEFAULT '{}'"))
        conn.commit()

if not column_exists("daily_summaries", "events"):
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("ALTER TABLE daily_summaries ADD COLUMN events JSON DEFAULT '[]'"))
        conn.commit()

if not column_exists("daily_summaries", "dayparts"):
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("ALTER TABLE daily_summaries ADD COLUMN dayparts JSON DEFAULT '[]'"))
        conn.commit()
