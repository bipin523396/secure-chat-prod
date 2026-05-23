const REST_URL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000/api"
    : window.location.origin + "/api";
// WebSocket Configuration
// On Vercel (Production), you must host the Java WebSocket server separately (e.g., Render/Railway).
const WS_URL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? `ws://${window.location.hostname}:5001`
    : `wss://secure-chat-java-server.onrender.com`;

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
