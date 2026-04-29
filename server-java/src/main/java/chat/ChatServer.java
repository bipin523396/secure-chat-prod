package chat;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.google.api.core.ApiFuture;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.firestore.*;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.cloud.FirestoreClient;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.FileInputStream;
import java.net.InetSocketAddress;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class ChatServer extends WebSocketServer {

    private final String JWT_SECRET = System.getenv("JWT_SECRET") != null ? 
        System.getenv("JWT_SECRET") : "JdXw3ypy3KXjLxfRpNW2LWV4ie3WyxrzCN7YUNAAxvE";

    private final Map<String, WebSocket> activeUsers = new ConcurrentHashMap<>();
    private final Map<WebSocket, String> socketToUser = new ConcurrentHashMap<>();

    private Firestore db;
    private CollectionReference usersCollection;
    private CollectionReference messagesCollection;

    public ChatServer(int port) {
        super(new InetSocketAddress(port));
        initFirebase();
    }

    private void initFirebase() {
        try {
            String credPath = System.getenv("FIREBASE_SERVICE_ACCOUNT") != null ? 
                System.getenv("FIREBASE_SERVICE_ACCOUNT") : "firebase-key.json";

            if (new java.io.File(credPath).exists()) {
                FileInputStream serviceAccount = new FileInputStream(credPath);
                FirebaseOptions options = FirebaseOptions.builder()
                        .setCredentials(GoogleCredentials.fromStream(serviceAccount))
                        .setStorageBucket("telemedicine-a28a0.firebasestorage.app")
                        .build();

                if (FirebaseApp.getApps().isEmpty()) {
                    FirebaseApp.initializeApp(options);
                }
                System.out.println("Firebase Admin SDK initialized successfully in Java Server.");
            } else {
                System.err.println("CRITICAL: firebase-key.json not found. Firebase will use default credentials.");
                if (FirebaseApp.getApps().isEmpty()) {
                    FirebaseApp.initializeApp();
                }
            }
            
            db = FirestoreClient.getFirestore();
            usersCollection = db.collection("users");
            messagesCollection = db.collection("messages");
            System.out.println("Connected to Firestore from Java Server.");
        } catch (Exception e) {
            e.printStackTrace();
        }
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

            System.out.println("User connected: " + username);

            // Update Firestore online status in background — does NOT close connection on failure
            final String uname = username;
            Thread t = new Thread(() -> {
                try {
                    QuerySnapshot query = usersCollection.whereEqualTo("username", uname).limit(1).get().get();
                    if (!query.isEmpty()) {
                        query.getDocuments().get(0).getReference().update("is_online", true, "last_seen", new Date());
                    }
                    broadcastStatusToFriends(uname, true);
                } catch (Exception ex) {
                    System.err.println("[Firestore] Could not update online status for " + uname + ": " + ex.getMessage());
                }
            });
            t.setDaemon(true);
            t.start();

        } catch (Exception e) {
            System.err.println("Auth error on connect: " + e.getMessage());
            conn.close(4001, "Authentication error: Invalid token");
        }
    }

    @Override
    public void onClose(WebSocket conn, int code, String reason, boolean remote) {
        String username = socketToUser.remove(conn);
        if (username != null) {
            activeUsers.remove(username);
            System.out.println("User disconnected: " + username);
            final String uname = username;
            Thread t = new Thread(() -> {
                try {
                    QuerySnapshot query = usersCollection.whereEqualTo("username", uname).limit(1).get().get();
                    if (!query.isEmpty()) {
                        query.getDocuments().get(0).getReference().update("is_online", false, "last_seen", new Date());
                    }
                    broadcastStatusToFriends(uname, false);
                } catch (Exception e) {
                    System.err.println("[Firestore] Could not update offline status for " + uname + ": " + e.getMessage());
                }
            });
            t.setDaemon(true);
            t.start();
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
                case "call_request":
                    handleCallRequest(username, conn, payload);
                    break;
                case "call_response":
                    handleCallResponse(username, conn, payload);
                    break;
                case "webrtc_signal":
                    handleWebRtcSignal(username, payload);
                    break;
                case "ice_candidate":
                    handleIceCandidate(username, payload);
                    break;
                case "call_end":
                    handleCallEnd(username, payload);
                    break;
                default:
                    System.out.println("Unknown event type: " + type);
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void broadcastStatusToFriends(String username, boolean isOnline) {
        try {
            QuerySnapshot userQuery = usersCollection.whereEqualTo("username", username).limit(1).get().get();
            if (userQuery.isEmpty()) return;
            // Use string document ID — matches how Python backend stores friend records
            String userId = userQuery.getDocuments().get(0).getId();

            QuerySnapshot friendsQuery = db.collection("friends").whereEqualTo("user_id", userId).get().get();

            JSONObject statusMsg = new JSONObject();
            statusMsg.put("type", "status_update");
            JSONObject payload = new JSONObject();
            payload.put("username", username);
            payload.put("is_online", isOnline);
            statusMsg.put("payload", payload);

            for (QueryDocumentSnapshot f : friendsQuery) {
                String friendId = f.getString("friend_id");
                if (friendId != null) {
                    DocumentSnapshot friendDoc = db.collection("users").document(friendId).get().get();
                    if (friendDoc.exists()) {
                        WebSocket conn = activeUsers.get(friendDoc.getString("username"));
                        if (conn != null) {
                            conn.send(statusMsg.toString());
                        }
                    }
                }
            }
        } catch (Exception e) { e.printStackTrace(); }
    }

    private void handleKeyUpdate(String username, JSONObject payload) {
        try {
            String newKey = payload.getString("public_key");
            QuerySnapshot userQuery = usersCollection.whereEqualTo("username", username).limit(1).get().get();
            if (userQuery.isEmpty()) return;
            String userId = userQuery.getDocuments().get(0).getId();

            QuerySnapshot friendsQuery = db.collection("friends").whereEqualTo("user_id", userId).get().get();

            JSONObject msg = new JSONObject();
            msg.put("type", "key_broadcast");
            JSONObject p = new JSONObject();
            p.put("username", username);
            p.put("public_key", newKey);
            msg.put("payload", p);

            for (QueryDocumentSnapshot f : friendsQuery) {
                String friendId = f.getString("friend_id");
                if (friendId != null) {
                    DocumentSnapshot friendDoc = db.collection("users").document(friendId).get().get();
                    if (friendDoc.exists()) {
                        WebSocket conn = activeUsers.get(friendDoc.getString("username"));
                        if (conn != null) {
                            conn.send(msg.toString());
                        }
                    }
                }
            }
        } catch (Exception e) { e.printStackTrace(); }
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
        try {
            String sender = payload.getString("sender");
            String msgId = payload.optString("message_id");
            
            if (msgId != null && !msgId.isEmpty()) {
                messagesCollection.document(msgId).update("status", "read");
            } else {
                // Mark all messages from sender to username as read
                QuerySnapshot unreadQuery = messagesCollection
                    .whereEqualTo("sender", sender)
                    .whereEqualTo("receiver", username)
                    .whereEqualTo("status", "delivered")
                    .get().get();
                
                WriteBatch batch = db.batch();
                for (QueryDocumentSnapshot doc : unreadQuery) {
                    batch.update(doc.getReference(), "status", "read");
                }
                batch.commit();
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
        } catch (Exception e) { e.printStackTrace(); }
    }

    private void handleSendMessage(String sender, WebSocket conn, JSONObject payload) {
        try {
            String receiver = payload.getString("receiver");
            long timestamp = System.currentTimeMillis();
            boolean isFileMessage = payload.has("file_id");

            Map<String, Object> data = new HashMap<>();
            data.put("sender", sender);
            data.put("receiver", receiver);
            data.put("timestamp", timestamp);
            data.put("status", "sent");
            data.put("deleted", false);
            data.put("edited", false);

            JSONObject rxPayload = new JSONObject();
            rxPayload.put("sender", sender);
            rxPayload.put("timestamp", timestamp);
            rxPayload.put("deleted", false);
            rxPayload.put("edited", false);

            if (isFileMessage) {
                String fileId = payload.getString("file_id");
                String fileName = payload.getString("file_name");
                String fileType = payload.getString("file_type");
                data.put("file_id", fileId);
                data.put("file_name", fileName);
                data.put("file_type", fileType);
                rxPayload.put("file_id", fileId);
                rxPayload.put("file_name", fileName);
                rxPayload.put("file_type", fileType);
            } else {
                List<Object> ciphertext = payload.getJSONArray("ciphertext").toList();
                List<Object> iv = payload.getJSONArray("iv").toList();
                data.put("ciphertext", ciphertext);
                data.put("iv", iv);
                rxPayload.put("ciphertext", new JSONArray(ciphertext));
                rxPayload.put("iv", new JSONArray(iv));
            }

            ApiFuture<DocumentReference> addedDocRef = messagesCollection.add(data);
            String msgId = addedDocRef.get().getId();
            rxPayload.put("_id", msgId);
            rxPayload.put("receiver", receiver);

            WebSocket receiverConn = activeUsers.get(receiver);
            if (receiverConn != null) {
                messagesCollection.document(msgId).update("status", "delivered");
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
        } catch (Exception e) { e.printStackTrace(); }
    }

    private void handleEditMessage(String sender, WebSocket conn, JSONObject payload) {
        try {
            String msgId = payload.getString("message_id");
            List<Object> newCiphertext = payload.getJSONArray("ciphertext").toList();
            List<Object> newIv = payload.getJSONArray("iv").toList();

            DocumentSnapshot msgDoc = messagesCollection.document(msgId).get().get();
            if (!msgDoc.exists() || !msgDoc.getString("sender").equals(sender)) return;

            messagesCollection.document(msgId).update(
                "ciphertext", newCiphertext,
                "iv", newIv,
                "edited", true
            );

            String receiver = msgDoc.getString("receiver");
            JSONObject editEvent = new JSONObject();
            editEvent.put("type", "message_edited");
            JSONObject p = new JSONObject();
            p.put("message_id", msgId);
            p.put("ciphertext", new JSONArray(newCiphertext));
            p.put("iv", new JSONArray(newIv));
            editEvent.put("payload", p);

            WebSocket receiverConn = activeUsers.get(receiver);
            if (receiverConn != null) receiverConn.send(editEvent.toString());
            conn.send(editEvent.toString());
        } catch (Exception e) { e.printStackTrace(); }
    }

    private void handleDeleteMessage(String sender, WebSocket conn, JSONObject payload) {
        try {
            String msgId = payload.getString("message_id");
            String deleteType = payload.optString("delete_type", "for_everyone");

            DocumentSnapshot msgDoc = messagesCollection.document(msgId).get().get();
            if (!msgDoc.exists() || !msgDoc.getString("sender").equals(sender)) return;
            
            String receiver = msgDoc.getString("receiver");
            
            if (deleteType.equals("for_everyone")) {
                messagesCollection.document(msgId).update("deleted", true);
                
                JSONObject delEvent = new JSONObject();
                delEvent.put("type", "message_deleted");
                JSONObject p = new JSONObject();
                p.put("message_id", msgId);
                delEvent.put("payload", p);
                
                WebSocket receiverConn = activeUsers.get(receiver);
                if (receiverConn != null) receiverConn.send(delEvent.toString());
                conn.send(delEvent.toString());
            } else {
                JSONObject delEvent = new JSONObject();
                delEvent.put("type", "message_deleted");
                JSONObject p = new JSONObject();
                p.put("message_id", msgId);
                delEvent.put("payload", p);
                conn.send(delEvent.toString());
            }
        } catch (Exception e) { e.printStackTrace(); }
    }

    private void handleFetchHistory(String username, WebSocket conn, JSONObject payload, String reqId) {
        try {
            String withUser = payload.getString("withUser");
            
            // Firestore doesn't support complex OR queries across multiple fields easily with ordering
            // We'll perform two queries and merge, or use a composite index if configured
            // For simplicity, we'll fetch both directions and sort manually
            
            QuerySnapshot q1 = messagesCollection.whereEqualTo("sender", username).whereEqualTo("receiver", withUser).get().get();
            QuerySnapshot q2 = messagesCollection.whereEqualTo("sender", withUser).whereEqualTo("receiver", username).get().get();
            
            List<QueryDocumentSnapshot> allDocs = new ArrayList<>(q1.getDocuments());
            allDocs.addAll(q2.getDocuments());
            allDocs.sort(Comparator.comparingLong(d -> d.getLong("timestamp")));
            
            JSONArray history = new JSONArray();
            for (QueryDocumentSnapshot d : allDocs) {
                JSONObject m = new JSONObject();
                m.put("_id", d.getId());
                m.put("sender", d.getString("sender"));
                m.put("receiver", d.getString("receiver"));
                m.put("timestamp", d.getLong("timestamp"));
                m.put("status", d.contains("status") ? d.getString("status") : "sent");
                m.put("edited", d.getBoolean("edited"));
                m.put("deleted", d.getBoolean("deleted"));
                
                if (d.contains("ciphertext")) {
                    m.put("ciphertext", new JSONArray((List<?>) d.get("ciphertext")));
                    m.put("iv", new JSONArray((List<?>) d.get("iv")));
                }
                if (d.contains("file_id")) {
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
        } catch (Exception e) { e.printStackTrace(); }
    }

    private void handleCallRequest(String sender, WebSocket conn, JSONObject payload) {
        String receiver = payload.getString("receiver");
        String callType = payload.getString("callType"); // audio/video

        WebSocket receiverConn = activeUsers.get(receiver);
        if (receiverConn == null) {
            JSONObject msg = new JSONObject();
            msg.put("type", "call_error");
            msg.put("payload", new JSONObject().put("message", "User is offline"));
            conn.send(msg.toString());
            return;
        }

        // Forward call request to receiver
        JSONObject msg = new JSONObject();
        msg.put("type", "incoming_call");
        JSONObject p = new JSONObject();
        p.put("sender", sender);
        p.put("callType", callType);
        msg.put("payload", p);
        receiverConn.send(msg.toString());
        System.out.println("Call request from " + sender + " to " + receiver);
    }

    private void handleCallResponse(String responder, WebSocket conn, JSONObject payload) {
        String caller = payload.getString("caller");
        String response = payload.getString("response"); // accept/reject/busy

        WebSocket callerConn = activeUsers.get(caller);
        if (callerConn != null) {
            JSONObject msg = new JSONObject();
            msg.put("type", "call_response");
            JSONObject p = new JSONObject();
            p.put("responder", responder);
            p.put("response", response);
            msg.put("payload", p);
            callerConn.send(msg.toString());
        }
    }

    private void handleWebRtcSignal(String sender, JSONObject payload) {
        String receiver = payload.getString("receiver");
        WebSocket receiverConn = activeUsers.get(receiver);
        if (receiverConn != null) {
            JSONObject msg = new JSONObject();
            msg.put("type", "webrtc_signal");
            JSONObject p = new JSONObject(payload.toString());
            p.put("sender", sender);
            msg.put("payload", p);
            receiverConn.send(msg.toString());
        }
    }

    private void handleIceCandidate(String sender, JSONObject payload) {
        String receiver = payload.getString("receiver");
        WebSocket receiverConn = activeUsers.get(receiver);
        if (receiverConn != null) {
            JSONObject msg = new JSONObject();
            msg.put("type", "ice_candidate");
            JSONObject p = new JSONObject(payload.toString());
            p.put("sender", sender);
            msg.put("payload", p);
            receiverConn.send(msg.toString());
        }
    }

    private void handleCallEnd(String sender, JSONObject payload) {
        String receiver = payload.getString("receiver");
        WebSocket receiverConn = activeUsers.get(receiver);
        if (receiverConn != null) {
            JSONObject msg = new JSONObject();
            msg.put("type", "call_end");
            msg.put("payload", new JSONObject().put("sender", sender));
            receiverConn.send(msg.toString());
        }
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
