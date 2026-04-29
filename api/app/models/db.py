import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from dotenv import load_dotenv

load_dotenv()

# Firebase Initialization
# Supports three modes:
# 1. FIREBASE_SERVICE_ACCOUNT_JSON env var (for Vercel/Cloud)
# 2. FIREBASE_SERVICE_ACCOUNT file path env var
# 3. Default firebase-key.json file

service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
cred = None

if service_account_json:
    import json
    import tempfile
    # Vercel doesn't like local file paths for certs, but we can pass the dict
    try:
        service_account_info = json.loads(service_account_json)
        cred = credentials.Certificate(service_account_info)
        print("Firebase Admin SDK initialized using environment JSON")
    except Exception as e:
        print(f"Error parsing FIREBASE_SERVICE_ACCOUNT_JSON: {e}")

if not cred:
    # Try multiple possible locations for firebase-key.json
    possible_paths = [
        os.getenv("FIREBASE_SERVICE_ACCOUNT", "firebase-key.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "firebase-key.json"),
        os.path.join(os.path.dirname(__file__), "..", "firebase-key.json"),
        os.path.join(os.path.dirname(__file__), "firebase-key.json"),
        "/var/task/api/firebase-key.json", # Common Vercel path
        "/var/task/firebase-key.json"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                cred = credentials.Certificate(path)
                print(f"Firebase Admin SDK initialized using {path}")
                break
            except Exception as e:
                print(f"Error loading creds from {path}: {e}")

if cred:
    try:
        firebase_admin.initialize_app(cred, {
            'storageBucket': os.getenv("FIREBASE_STORAGE_BUCKET", "telemedicine-a28a0.firebasestorage.app")
        })
    except ValueError:
        # App already initialized
        pass
    except Exception as e:
        print(f"Error initializing Firebase app: {e}")
else:
    try:
        # Try default credentials (ADC)
        firebase_admin.initialize_app()
        print("Firebase Admin SDK initialized using default credentials")
    except Exception as e:
        print(f"CRITICAL: Firebase could not be initialized. No key found and ADC failed. Error: {e}")

# Global db and bucket objects
try:
    db = firestore.client()
    bucket = storage.bucket()
except Exception as e:
    print(f"CRITICAL ERROR initializing Firestore/Storage: {e}")
    db = None
    bucket = None

# Collections (Helper names to maintain compatibility)
class CollectionWrapper:
    def __init__(self, name):
        self.name = name
        try:
            self.coll = db.collection(name) if db else None
        except:
            self.coll = None

    def find_one(self, filter):
        if not self.coll:
            return None
        if "_id" in filter:
            doc_ref = self.coll.document(str(filter["_id"]))
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                data["_id"] = doc.id
                return data
            return None
            
        query = self.coll
        for k, v in filter.items():
            query = query.where(k, "==", v)
        docs = list(query.limit(1).stream())
        if docs:
            data = docs[0].to_dict()
            data["_id"] = docs[0].id
            return data
        return None

    def insert_one(self, data):
        if not self.coll:
            return None
        if "_id" in data:
            doc_id = str(data.pop("_id"))
            self.coll.document(doc_id).set(data)
            return doc_id
        else:
            _, doc_ref = self.coll.add(data)
            return doc_ref.id

    def update_one(self, filter, update):
        if not self.coll:
            return None
        target_doc = None
        if "_id" in filter:
            target_doc = self.coll.document(str(filter["_id"]))
        else:
            query = self.coll
            for k, v in filter.items():
                query = query.where(k, "==", v)
            docs = list(query.limit(1).stream())
            if docs:
                target_doc = docs[0].reference

        if target_doc:
            if "$set" in update:
                target_doc.update(update["$set"])
            else:
                target_doc.update(update)


users_collection = CollectionWrapper("users")
friend_requests_collection = CollectionWrapper("friend_requests")
friends_collection = CollectionWrapper("friends")
blocked_users_collection = CollectionWrapper("blocked_users")
media_files_collection = CollectionWrapper("media_files")

def init_db():
    print("Firestore collections ready.")
