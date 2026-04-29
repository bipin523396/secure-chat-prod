package chat;

import java.io.IOException;

public class Main {
    public static void main(String[] args) throws IOException {
        int port = 5001; 
        ChatServer server = new ChatServer(port);
        server.start();
        System.out.println("Java WebSocket server starting on port: " + port);
    }
}
