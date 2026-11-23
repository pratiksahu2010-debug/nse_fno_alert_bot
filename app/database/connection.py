from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,DeclarativeBase
class Base(DeclarativeBase): pass
def make_engine(url):
    if not url: raise ValueError('DATABASE_URL is required (Neon PostgreSQL for deployment)')
    if url.startswith('sqlite'): return create_engine(url,connect_args={'check_same_thread':False},pool_pre_ping=True)
    return create_engine(url,pool_pre_ping=True,pool_recycle=300,pool_size=3,max_overflow=2,connect_args={'sslmode':'require','connect_timeout':10})
