const REST_URL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000/api"
    : window.location.origin + "/api";
// On Vercel, we might need to connect to a different WebSocket server.
// For now, we use the same host but warn if it's likely to fail.
const WS_URL = window.location.hostname.includes("vercel.app") 
    ? `wss://secure-chat-java-server.onrender.com` // You should update this after deploying Java server
    : `ws://${window.location.hostname}:5001`;

if (window.location.hostname.includes("vercel.app")) {
    console.warn("WebSocket connections to port 5001 usually fail on Vercel. Ensure your Java server is hosted elsewhere and update WS_URL in app.js.");
}

let socket = null;
let currentUsername = null;
let currentPassword = null; // Kept in memory to derive keys
let accessToken = null;
let refreshToken = null;

let mySeed = null;
let myIdentity = null;

let activeChatUser = null;
const sharedKeys = {}; // cache: username -> CryptoKey
let friendsList = [];
const unreadCounts = {};
let settingsOpen = false;
let notifEnabled = true;
let soundEnabled = true;
let editingMessageId = null;
