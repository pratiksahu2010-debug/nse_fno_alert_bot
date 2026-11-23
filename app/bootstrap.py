from .config import Settings
from .database.connection import Base,make_engine
from .database import models  # register every table before create_all

def migrate():
    s=Settings();Base.metadata.create_all(make_engine(s.database_url))
