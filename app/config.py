from pydantic_settings import BaseSettings,SettingsConfigDict
from pydantic import Field,field_validator,model_validator
from zoneinfo import ZoneInfo
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file='.env',extra='ignore',case_sensitive=False)
    upstox_access_token:str=''; telegram_bot_token:str=''; telegram_chat_id:str=''; database_url:str=''
    log_level:str='INFO'; timezone:str='Asia/Kolkata'; universe_path:str='config/nse_fno_universe.json'
    orb_range_minutes:int=Field(15,ge=5,le=15); orb_entry_cutoff:str='11:30'; momentum_entry_cutoff:str='15:00'
    momentum_cooldown_minutes:int=Field(30,ge=0); relative_volume_threshold:float=Field(1.5,gt=0)
    atr_expansion_threshold:float=Field(1.2,gt=0); structure_lookback:int=Field(10,ge=2); atr_period:int=Field(14,ge=2)
    adx_min:float=Field(18,ge=1,le=60); momentum_min_score:int=Field(75,ge=0,le=100)
    ema_fast:int=Field(9,ge=2); ema_slow:int=Field(21,ge=3); gap_min_pct:float=Field(1.0,ge=0)
    sl_atr_buffer:float=Field(.2,ge=0); target_1_r:float=Field(1,gt=0); target_2_r:float=Field(2,gt=0)
    websocket_stale_seconds:int=90; enable_live_runtime:bool=True
    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls,v): ZoneInfo(v); return v
    @field_validator('database_url')
    @classmethod
    def normalize_db(cls,v):
        if v.startswith('postgres://'): return v.replace('postgres://','postgresql+psycopg://',1)
        if v.startswith('postgresql://'): return v.replace('postgresql://','postgresql+psycopg://',1)
        return v
    @model_validator(mode='after')
    def validate_ema(self):
        if self.ema_fast>=self.ema_slow: raise ValueError('EMA_FAST must be less than EMA_SLOW')
        if self.orb_range_minutes not in (5,10,15): raise ValueError('ORB_RANGE_MINUTES must be 5, 10, or 15')
        return self
