from shared.core.db.session import create_db

engine, SessionLocal, Base = create_db("ROOM_DB")