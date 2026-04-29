package chat;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Updates;
import org.bson.Document;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;
import org.json.JSONArray;
import org.json.JSONObject;

import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ChatServer extends WebSocketServer {

    private final String JWT_SECRET = "JdXw3ypy3KXjLxfRpNW2LWV4ie3WyxrzCN7YUNAAxvE";
    private final Map<String, WebSocket> activeUsers = new ConcurrentHashMap<>();
    private final Map<WebSocket, String> socketToUser = new ConcurrentHashMap<>();

    private MongoClient mongoClient;
    private MongoDatabase database;
    private MongoCollection<Document> usersCollection;
    private MongoCollection<Document> messagesCollection;

    public ChatServer(int port) {
        super(new InetSocketAddress(port));
        initMongo();
    }

    private void initMongo() {
        mongoClient = MongoClients.create("mongodb://localhost:27017");
        database = mongoClient.getDatabase("securechat");
        usersCollection = database.getCollection("users");
        messagesCollection = database.getCollection("messages");
        System.out.println("Connected to MongoDB from Java Server.");
    }

    @Override
    public void onOpen(WebSocket conn, ClientHandshake handshake) {
        String resource = handshake.getResourceDescriptor();
        String token = null;

        if (resource.contains("token=")) {
            token = resource.split("token=")[1].split("&")[0];
        }

        if (token == null) {
            conn.close(4001, "Authentication error: No token");
            return;
        }

        try {
            DecodedJWT jwt = JWT.require(Algorithm.HMAC256(JWT_SECRET)).build().verify(token);
            String username = jwt.getClaim("username").asString();
            
            activeUsers.put(username, conn);
            socketToUser.put(conn, username);
            
            // Update online status in DB
            usersCollection.updateOne(Filters.eq("username", username), 
                Updates.combine(Updates.set("is_online", true), Updates.set("last_seen", new java.util.Date())));
            
            System.out.println("User connected: " + username);
            broadcastStatusToFriends(username, true);

        } catch (Exception e) {
            conn.close(4001, "Authentication error: Invalid token");
        }
    }

    @Override
    public void onClose(WebSocket conn, int code, String reason, boolean remote) {
        String username = socketToUser.remove(conn);
        if (username != null) {
            activeUsers.remove(username);
            
            // Update offline status in DB
            usersCollection.updateOne(Filters.eq("username", username), 
                Updates.combine(Updates.set("is_online", false), Updates.set("last_seen", new java.util.Date())));
            
            System.out.println("User disconnected: " + username);
            broadcastStatusToFriends(username, false);
        }
    }

    @Override
    public void onMessage(WebSocket conn, String message) {
        String username = socketToUser.get(conn);
        if (username == null) return;

        try {
            JSONObject req = new JSONObject(message);
            String type = req.getString("type");
            JSONObject payload = req.optJSONObject("payload");
            if (payload == null) payload = new JSONObject();

            switch (type) {
                case "send_message":
                    handleSendMessage(username, conn, payload);
                    break;
                case "typing":
                    handleTyping(username, payload);
                    break;
                case "mark_read":
                    handleMarkRead(username, payload);
                    break;
                case "fetch_history":
                    handleFetchHistory(username, conn, payload, req.optString("reqId"));
                    break;
                case "key_update":
                    handleKeyUpdate(username, payload);
                    break;
                case "edit_message":
                    handleEditMessage(username, conn, payload);
                    break;
                case "delete_message":
                    handleDeleteMessage(username, conn, payload);
                    break;
                default:
                    System.out.println("Unknown event type: " + type);
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void broadcastStatusToFriends(String username, boolean isOnline) {
        Document user = usersCollection.find(Filters.eq("username", username)).first();
        if (user == null) return;
        
        // Find friends (bidirectional check is done in Python, but let's just find where user is friend)
        MongoCollection<Document> friendsCollection = database.getCollection("friends");
        List<Document> friends = new ArrayList<>();
        friendsCollection.find(Filters.eq("user_id", user.getObjectId("_id"))).into(friends);
        
        JSONObject statusMsg = new JSONObject();
        statusMsg.put("type", "status_update");
        JSONObject payload = new JSONObject();
        payload.put("username", username);
        payload.put("is_online", isOnline);
        statusMsg.put("payload", payload);
        
        for (Document f : friends) {
            Document friendDoc = usersCollection.find(Filters.eq("_id", f.getObjectId("friend_id"))).first();
            if (friendDoc != null) {
                WebSocket conn = activeUsers.get(friendDoc.getString("username"));
                if (conn != null) {
                    conn.send(statusMsg.toString());
                }
            }
        }
    }

    private void handleKeyUpdate(String username, JSONObject payload) {
        String newKey = payload.getString("public_key");
        Document user = usersCollection.find(Filters.eq("username", username)).first();
        if (user == null) return;
        
        MongoCollection<Document> friendsCollection = database.getCollection("friends");
        List<Document> friends = new ArrayList<>();
        friendsCollection.find(Filters.eq("user_id", user.getObjectId("_id"))).into(friends);
        
        JSONObject msg = new JSONObject();
        msg.put("type", "key_broadcast");
        JSONObject p = new JSONObject();
        p.put("username", username);
        p.put("public_key", newKey);
        msg.put("payload", p);
        
        for (Document f : friends) {
            Document friendDoc = usersCollection.find(Filters.eq("_id", f.getObjectId("friend_id"))).first();
            if (friendDoc != null) {
                WebSocket conn = activeUsers.get(friendDoc.getString("username"));
                if (conn != null) {
                    conn.send(msg.toString());
                }
            }
        }
    }

    private void handleTyping(String username, JSONObject payload) {
        String receiver = payload.getString("receiver");
        boolean isTyping = payload.getBoolean("is_typing");
        
        WebSocket receiverConn = activeUsers.get(receiver);
        if (receiverConn != null) {
            JSONObject msg = new JSONObject();
            msg.put("type", "typing_event");
            JSONObject p = new JSONObject();
            p.put("sender", username);
            p.put("is_typing", isTyping);
            msg.put("payload", p);
            receiverConn.send(msg.toString());
        }
    }

    private void handleMarkRead(String username, JSONObject payload) {
        String sender = payload.getString("sender"); // The person who sent the original message
        String msgId = payload.optString("message_id");
        
        if (msgId != null && !msgId.isEmpty()) {
            messagesCollection.updateOne(Filters.eq("_id", new org.bson.types.ObjectId(msgId)), Updates.set("status", "read"));
        } else {
            // Mark all messages from sender to username as read
            messagesCollection.updateMany(
                Filters.and(Filters.eq("sender", sender), Filters.eq("receiver", username), Filters.eq("status", "delivered")),
                Updates.set("status", "read")
            );
        }
        
        WebSocket senderConn = activeUsers.get(sender);
        if (senderConn != null) {
            JSONObject msg = new JSONObject();
            msg.put("type", "read_receipt");
            JSONObject p = new JSONObject();
            p.put("reader", username);
            if (msgId != null) p.put("message_id", msgId);
            msg.put("payload", p);
            senderConn.send(msg.toString());
        }
    }

    private void handleSendMessage(String sender, WebSocket conn, JSONObject payload) {
        String receiver = payload.getString("receiver");
        long timestamp = System.currentTimeMillis();
        boolean isFileMessage = payload.has("file_id");

        Document newMsg = new Document()
                .append("sender", sender)
                .append("receiver", receiver)
                .append("timestamp", timestamp)
                .append("status", "sent")
                .append("deleted", false)
                .append("edited", false);

        JSONObject rxPayload = new JSONObject();
        rxPayload.put("sender", sender);
        rxPayload.put("timestamp", timestamp);
        rxPayload.put("deleted", false);
        rxPayload.put("edited", false);

        if (isFileMessage) {
            String fileId = payload.getString("file_id");
            String fileName = payload.getString("file_name");
            String fileType = payload.getString("file_type");
            newMsg.append("file_id", fileId).append("file_name", fileName).append("file_type", fileType);
            rxPayload.put("file_id", fileId);
            rxPayload.put("file_name", fileName);
            rxPayload.put("file_type", fileType);
        } else {
            // Encrypted message
            JSONArray ciphertext = payload.getJSONArray("ciphertext");
            JSONArray iv = payload.getJSONArray("iv");
            newMsg.append("ciphertext", ciphertext.toList()).append("iv", iv.toList());
            rxPayload.put("ciphertext", ciphertext);
            rxPayload.put("iv", iv);
        }

        messagesCollection.insertOne(newMsg);
        String msgId = newMsg.getObjectId("_id").toHexString();
        rxPayload.put("_id", msgId);
        rxPayload.put("receiver", receiver);

        WebSocket receiverConn = activeUsers.get(receiver);
        if (receiverConn != null) {
            messagesCollection.updateOne(Filters.eq("_id", newMsg.getObjectId("_id")), Updates.set("status", "delivered"));
            rxPayload.put("status", "delivered");
            JSONObject rxMsg = new JSONObject();
            rxMsg.put("type", "receive_message");
            rxMsg.put("payload", rxPayload);
            receiverConn.send(rxMsg.toString());

            JSONObject receipt = new JSONObject();
            receipt.put("type", "delivery_receipt");
            JSONObject dPayload = new JSONObject();
            dPayload.put("message_id", msgId);
            receipt.put("payload", dPayload);
            conn.send(receipt.toString());
        }
    }

    private void handleEditMessage(String sender, WebSocket conn, JSONObject payload) {
        String msgId = payload.getString("message_id");
        JSONArray newCiphertext = payload.getJSONArray("ciphertext");
        JSONArray newIv = payload.getJSONArray("iv");

        Document msg = messagesCollection.find(Filters.and(
            Filters.eq("_id", new org.bson.types.ObjectId(msgId)),
            Filters.eq("sender", sender)
        )).first();
        if (msg == null) return;

        messagesCollection.updateOne(
            Filters.eq("_id", new org.bson.types.ObjectId(msgId)),
            Updates.combine(
                Updates.set("ciphertext", newCiphertext.toList()), 
                Updates.set("iv", newIv.toList()), 
                Updates.set("edited", true)
            )
        );

        String receiver = msg.getString("receiver");
        JSONObject editEvent = new JSONObject();
        editEvent.put("type", "message_edited");
        JSONObject p = new JSONObject();
        p.put("message_id", msgId);
        p.put("ciphertext", newCiphertext);
        p.put("iv", newIv);
        editEvent.put("payload", p);

        WebSocket receiverConn = activeUsers.get(receiver);
        if (receiverConn != null) receiverConn.send(editEvent.toString());
        conn.send(editEvent.toString());
    }

    private void handleDeleteMessage(String sender, WebSocket conn, JSONObject payload) {
        String msgId = payload.getString("message_id");
        String deleteType = payload.optString("delete_type", "for_everyone"); // "for_me" | "for_everyone"
        
        // Only allow deleting own messages for "for_everyone"
        Document msg = messagesCollection.find(Filters.and(
            Filters.eq("_id", new org.bson.types.ObjectId(msgId)),
            Filters.eq("sender", sender)
        )).first();
        
        if (msg == null) return;
        
        String receiver = msg.getString("receiver");
        
        if (deleteType.equals("for_everyone")) {
            messagesCollection.updateOne(
                Filters.eq("_id", new org.bson.types.ObjectId(msgId)),
                Updates.set("deleted", true)
            );
            
            JSONObject delEvent = new JSONObject();
            delEvent.put("type", "message_deleted");
            JSONObject p = new JSONObject();
            p.put("message_id", msgId);
            delEvent.put("payload", p);
            
            WebSocket receiverConn = activeUsers.get(receiver);
            if (receiverConn != null) receiverConn.send(delEvent.toString());
            conn.send(delEvent.toString());
        } else {
            // For me only - just notify sender
            JSONObject delEvent = new JSONObject();
            delEvent.put("type", "message_deleted");
            JSONObject p = new JSONObject();
            p.put("message_id", msgId);
            delEvent.put("payload", p);
            conn.send(delEvent.toString());
        }
    }

    private void handleFetchHistory(String username, WebSocket conn, JSONObject payload, String reqId) {
        String withUser = payload.getString("withUser");
        
        List<Document> msgs = new ArrayList<>();
        messagesCollection.find(
            Filters.or(
                Filters.and(Filters.eq("sender", username), Filters.eq("receiver", withUser)),
                Filters.and(Filters.eq("sender", withUser), Filters.eq("receiver", username))
            )
        ).sort(Sorts.ascending("timestamp")).into(msgs);
        
        JSONArray history = new JSONArray();
        for (Document d : msgs) {
            JSONObject m = new JSONObject();
            m.put("_id", d.getObjectId("_id").toHexString());
            m.put("sender", d.getString("sender"));
            m.put("receiver", d.getString("receiver"));
            m.put("timestamp", d.getLong("timestamp"));
            m.put("status", d.containsKey("status") ? d.getString("status") : "sent");
            m.put("edited", d.getBoolean("edited", false));
            m.put("deleted", d.getBoolean("deleted", false));
            // Encrypted text
            if (d.containsKey("ciphertext")) {
                m.put("ciphertext", new JSONArray(d.getList("ciphertext", Object.class)));
                m.put("iv", new JSONArray(d.getList("iv", Object.class)));
            }
            // File
            if (d.containsKey("file_id")) {
                m.put("file_id", d.getString("file_id"));
                m.put("file_name", d.getString("file_name"));
                m.put("file_type", d.getString("file_type"));
            }
            history.put(m);
        }
        
        JSONObject msg = new JSONObject();
        msg.put("type", "history_response");
        msg.put("reqId", reqId);
        msg.put("payload", history);
        conn.send(msg.toString());
    }

    @Override
    public void onError(WebSocket conn, Exception ex) {
        System.err.println("An error occurred on connection");
        ex.printStackTrace();
    }

    @Override
    public void onStart() {
        System.out.println("Java WebSocket server started successfully on port " + getPort());
    }
}
