from fastapi import Depends

from app.config import Settings, get_settings
from app.database import get_db

DBSession = Depends(get_db)
AppSettings = Depends(get_settings)

