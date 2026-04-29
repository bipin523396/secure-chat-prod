/* calling.js — Production-Grade WebRTC Calling */

let peerConnection = null;
let localStream = null;
let callPartner = null;
let isAudioOnly = false;
let callTimerInterval = null;
let callStartTime = null;

// STUN/TURN Servers Config
const rtcConfig = {
    iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        { urls: "stun:stun1.l.google.com:19302" },
        { urls: "stun:stun2.l.google.com:19302" },
        // IMPORTANT: In production, add a TURN server here (Coturn or Twilio)
        // {
        //     urls: "turn:your-turn-server.com:3478",
        //     username: "user",
        //     credential: "password"
        // }
    ]
};

// UI Elements
const callOverlay = document.getElementById("call-overlay");
const incomingCallPopup = document.getElementById("incoming-call-popup");
const callStatus = document.getElementById("call-status");
const callTimer = document.getElementById("call-timer");
const remoteVideo = document.getElementById("remote-video");
const localVideo = document.getElementById("local-video");
const videoContainer = document.getElementById("video-container");

const ringtoneOut = document.getElementById("ringtone-out");
const ringtoneIn = document.getElementById("ringtone-in");

// =========================================================
// CALL INITIALIZATION
// =========================================================

async function startCall(targetUser, type = 'video') {
    if (peerConnection) return;
    callPartner = targetUser;
    isAudioOnly = (type === 'audio');

    // Update UI
    document.getElementById("call-username").textContent = targetUser;
    document.getElementById("call-avatar").textContent = targetUser.charAt(0).toUpperCase();
    callStatus.textContent = "Calling...";
    callOverlay.classList.remove("hidden");
    videoContainer.classList.toggle("hidden", isAudioOnly);
    
    ringtoneOut.play();

    try {
        // Get media
        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: !isAudioOnly
        });
        localVideo.srcObject = localStream;

        // Send call request to server
        wsSend("call_request", { receiver: targetUser, callType: type });

    } catch (err) {
        console.error("Media access error:", err);
        alert("Could not access camera/microphone. WebRTC requires HTTPS.");
        endCall();
    }
}

function handleIncomingCall(payload) {
    const sender = payload.sender;
    const type = payload.callType;
    
    if (peerConnection) {
        // We are busy
        wsSend("call_response", { caller: sender, response: "busy" });
        return;
    }

    callPartner = sender;
    isAudioOnly = (type === 'audio');

    document.getElementById("incoming-username").textContent = sender;
    document.getElementById("incoming-avatar").textContent = sender.charAt(0).toUpperCase();
    document.getElementById("incoming-type").textContent = type;
    incomingCallPopup.classList.remove("hidden");
    
    ringtoneIn.play();
}

// =========================================================
// CALL SIGNALING HANDLERS
// =========================================================

async function onCallResponse(payload) {
    const response = payload.response;
    ringtoneOut.pause();
    ringtoneOut.currentTime = 0;

    if (response === 'accept') {
        callStatus.textContent = "Connecting...";
        await createPeerConnection();
        
        // Create Offer
        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);
        
        wsSend("webrtc_signal", { 
            receiver: callPartner, 
            type: "offer", 
            sdp: offer.sdp 
        });
    } else {
        const reason = response === 'busy' ? "User is busy" : "Call rejected";
        alert(reason);
        endCall();
    }
}

async function onWebRtcSignal(payload) {
    const type = payload.type;
    const sdp = payload.sdp;

    if (type === 'offer') {
        await createPeerConnection();
        await peerConnection.setRemoteDescription(new RTCSessionDescription({ type, sdp }));
        
        const answer = await peerConnection.createAnswer();
        await peerConnection.setLocalDescription(answer);
        
        wsSend("webrtc_signal", { 
            receiver: callPartner, 
            type: "answer", 
            sdp: answer.sdp 
        });
        
        startTimer();
    } else if (type === 'answer') {
        await peerConnection.setRemoteDescription(new RTCSessionDescription({ type, sdp }));
        startTimer();
    }
}

async function onIceCandidate(payload) {
    if (peerConnection) {
        try {
            await peerConnection.addIceCandidate(new RTCIceCandidate(payload.candidate));
        } catch (e) {
            console.error("Error adding ice candidate", e);
        }
    }
}

// =========================================================
// PEER CONNECTION LOGIC
// =========================================================

async function createPeerConnection() {
    peerConnection = new RTCPeerConnection(rtcConfig);

    // Add local tracks to PC
    localStream.getTracks().forEach(track => {
        peerConnection.addTrack(track, localStream);
    });

    // Handle remote tracks
    peerConnection.ontrack = (event) => {
        remoteVideo.srcObject = event.streams[0];
        callStatus.textContent = "Connected";
    };

    // Handle ICE candidates
    peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
            wsSend("ice_candidate", { 
                receiver: callPartner, 
                candidate: event.candidate 
            });
        }
    };

    peerConnection.oniceconnectionstatechange = () => {
        if (peerConnection.iceConnectionState === 'disconnected' || 
            peerConnection.iceConnectionState === 'failed') {
            endCall();
        }
    };
}

// =========================================================
// CONTROLS & UI ACTIONS
// =========================================================

document.getElementById("incoming-accept-btn").onclick = async () => {
    ringtoneIn.pause();
    ringtoneIn.currentTime = 0;
    incomingCallPopup.classList.add("hidden");
    
    document.getElementById("call-username").textContent = callPartner;
    document.getElementById("call-avatar").textContent = callPartner.charAt(0).toUpperCase();
    callOverlay.classList.remove("hidden");
    videoContainer.classList.toggle("hidden", isAudioOnly);
    callStatus.textContent = "Connecting...";

    try {
        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: !isAudioOnly
        });
        localVideo.srcObject = localStream;
        
        wsSend("call_response", { caller: callPartner, response: "accept" });
    } catch (e) {
        alert("Could not access media.");
        endCall();
    }
};

document.getElementById("incoming-reject-btn").onclick = () => {
    ringtoneIn.pause();
    ringtoneIn.currentTime = 0;
    incomingCallPopup.classList.add("hidden");
    wsSend("call_response", { caller: callPartner, response: "reject" });
    callPartner = null;
};

document.getElementById("call-hangup-btn").onclick = () => {
    wsSend("call_end", { receiver: callPartner });
    endCall();
};

document.getElementById("audio-call-btn").onclick = () => {
    if (activeChatUser) startCall(activeChatUser.username, 'audio');
};

document.getElementById("video-call-btn").onclick = () => {
    if (activeChatUser) startCall(activeChatUser.username, 'video');
};

function endCall() {
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
    if (localStream) {
        localStream.getTracks().forEach(t => t.stop());
        localStream = null;
    }
    
    ringtoneOut.pause();
    ringtoneIn.pause();
    
    stopTimer();
    callOverlay.classList.add("hidden");
    incomingCallPopup.classList.add("hidden");
    callPartner = null;
    remoteVideo.srcObject = null;
}

// =========================================================
// UTILS
// =========================================================

function startTimer() {
    callStartTime = Date.now();
    callTimer.classList.remove("hidden");
    callTimerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
        const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
        const secs = (elapsed % 60).toString().padStart(2, '0');
        callTimer.textContent = `${mins}:${secs}`;
    }, 1000);
}

function stopTimer() {
    if (callTimerInterval) {
        clearInterval(callTimerInterval);
        callTimerInterval = null;
    }
    callTimer.classList.add("hidden");
}

// Controls: Mute & Video Toggle
document.getElementById("call-mic-btn").onclick = (e) => {
    if (localStream) {
        const audioTrack = localStream.getAudioTracks()[0];
        audioTrack.enabled = !audioTrack.enabled;
        e.currentTarget.classList.toggle("active", !audioTrack.enabled);
        e.currentTarget.innerHTML = audioTrack.enabled ? '<i class="ph ph-microphone"></i>' : '<i class="ph ph-microphone-slash"></i>';
    }
};

document.getElementById("call-video-btn").onclick = (e) => {
    if (localStream && !isAudioOnly) {
        const videoTrack = localStream.getVideoTracks()[0];
        videoTrack.enabled = !videoTrack.enabled;
        e.currentTarget.classList.toggle("active", !videoTrack.enabled);
        e.currentTarget.innerHTML = videoTrack.enabled ? '<i class="ph ph-video-camera"></i>' : '<i class="ph ph-video-camera-slash"></i>';
    }
};
