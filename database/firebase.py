import firebase_admin
from firebase_admin import credentials, db
from config import get_settings
from logger import logger

class FirebaseManager:
    _instance, _initialized = None, False

    def __new__(cls):
        if cls._instance is None: cls._instance = super(FirebaseManager, cls).__new__(cls)
        return cls._instance

    def initialize(self):
        if self._initialized: return
        settings = get_settings()
        cred = credentials.Certificate(settings.get_firebase_credentials())
        firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_DATABASE_URL})
        self._initialized = True
        logger.info("Connected to Firebase Realtime Database.")

    def get_ref(self, path: str):
        if not self._initialized: self.initialize()
        return db.reference(path)

    def safe_get(self, path: str):
        try: return self.get_ref(path).get()
        except Exception as e: raise RuntimeError(f"Read error: {e}")

    def safe_set(self, path: str, val):
        try: self.get_ref(path).set(val)
        except Exception as e: raise RuntimeError(f"Write error: {e}")

    def safe_update(self, path: str, val: dict):
        try: self.get_ref(path).update(val)
        except Exception as e: raise RuntimeError(f"Update error: {e}")

    def run_transaction(self, path: str, fn):
        try: return self.get_ref(path).transaction(fn)
        except Exception as e: raise RuntimeError(f"Transaction error: {e}")

firebase_manager = FirebaseManager()