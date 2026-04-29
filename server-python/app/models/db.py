import os
from pymongo import MongoClient
import gridfs
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/securechat")
client = MongoClient(MONGO_URI)
db = client.get_database()

# Collections
users_collection = db.users
friend_requests_collection = db.friend_requests
friends_collection = db.friends
blocked_users_collection = db.blocked_users
media_files_collection = db.media_files

# GridFS for large binary data
fs = gridfs.GridFS(db)

def init_db():
    # Create indexes for optimization
    users_collection.create_index("username", unique=True)
    friend_requests_collection.create_index([("sender_id", 1), ("receiver_id", 1)], unique=True)
    friends_collection.create_index([("user_id", 1), ("friend_id", 1)], unique=True)
    blocked_users_collection.create_index([("blocker_id", 1), ("blocked_id", 1)], unique=True)
