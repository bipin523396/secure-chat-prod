import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from dotenv import load_dotenv

load_dotenv()

# Firebase Initialization
# Expects a service account key JSON file path in .env as FIREBASE_SERVICE_ACCOUNT
# Or looks for firebase-key.json in the current directory
cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT", "firebase-key.json")

if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': os.getenv("FIREBASE_STORAGE_BUCKET", "telemedicine-a28a0.firebasestorage.app")
    })
    print(f"Firebase Admin SDK initialized using {cred_path}")
else:
    # Fallback to default credentials (works in GCP environments or if GOOGLE_APPLICATION_CREDENTIALS is set)
    try:
        firebase_admin.initialize_app()
        print("Firebase Admin SDK initialized using default credentials")
    except Exception as e:
        print(f"CRITICAL: Firebase could not be initialized. Please provide a service account key. Error: {e}")

db = firestore.client()
bucket = storage.bucket()

# Collections (Helper names to maintain compatibility)
class CollectionWrapper:
    def __init__(self, name):
        self.name = name
        self.coll = db.collection(name)

    def find_one(self, filter):
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
        if "_id" in data:
            doc_id = str(data.pop("_id"))
            self.coll.document(doc_id).set(data)
            return doc_id
        else:
            _, doc_ref = self.coll.add(data)
            return doc_ref.id

    def update_one(self, filter, update):
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
