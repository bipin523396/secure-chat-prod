import { chromium } from "playwright";

const BASE = process.env.CHAT_URL || "http://localhost:8765";
const API = "https://secure-chat-prod.onrender.com/api";
const user = `e2e_${Date.now().toString(36)}`;
const pass = "E2eTestPass123!";

const consoleErrors = [];
const failedRequests = [];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("requestfailed", (req) => {
    failedRequests.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`);
  });
  page.on("response", (res) => {
    const url = res.url();
    if (url.includes("secure-chat") && res.status() >= 400) {
      failedRequests.push(`${res.request().method()} ${url} — HTTP ${res.status()}`);
    }
  });

  console.log("1. Register + login as", user);
  await page.goto(BASE, { waitUntil: "networkidle" });

  await page.fill("#username", user);
  await page.fill("#password", pass);
  await page.click("#register-btn");
  await page.waitForTimeout(2000);

  await page.fill("#username", user);
  await page.fill("#password", pass);
  await page.click("#login-btn");

  try {
    await page.waitForSelector("#chat-container:not(.hidden)", { timeout: 30000 });
  } catch {
    const err = await page.textContent("#auth-error").catch(() => "");
    const logs = consoleErrors.slice(-5).join(" | ");
    throw new Error(`Login UI failed. auth-error: ${err || "(empty)"}. console: ${logs}`);
  }
  console.log("   OK: Chat UI visible after login");

  const token = await page.evaluate(() => localStorage.getItem("chat_access_token"));
  const sessPass = await page.evaluate(() => sessionStorage.getItem("chat_password"));
  if (!token) throw new Error("No access token in localStorage");
  if (!sessPass) throw new Error("No password in sessionStorage");
  console.log("   OK: Session stored (token + sessionStorage password)");

  console.log("2. API: send message with JSON Content-Type");
  const sendResult = await page.evaluate(
    async ({ api, receiver }) => {
      const token = localStorage.getItem("chat_access_token");
      const res = await fetch(`${api}/messages/send`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ receiver, ciphertext: "hello-e2e", iv: "plain" }),
      });
      const body = await res.json().catch(() => ({}));
      return { status: res.status, body };
    },
    { api: API, receiver: user }
  );
  if (sendResult.status === 415) throw new Error("415 on send — Content-Type fix not applied");
  if (sendResult.status >= 400) console.log("   WARN send to self:", sendResult.status, sendResult.body);
  else console.log("   OK: POST /messages/send status", sendResult.status);

  console.log("3. API: history with since param");
  const since = new Date().toISOString();
  const histResult = await page.evaluate(
    async ({ api, partner, since }) => {
      const token = localStorage.getItem("chat_access_token");
      const url = `${api}/messages/history?withUser=${encodeURIComponent(partner)}&since=${encodeURIComponent(since)}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      const text = await res.text();
      return { status: res.status, preview: text.slice(0, 200) };
    },
    { api: API, partner: user, since }
  );
  if (histResult.status === 500) throw new Error(`500 on history?since= — ${histResult.preview}`);
  console.log("   OK: GET history?since= status", histResult.status);

  console.log("4. Page refresh — must stay in chat");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(3000);

  const authHidden = await page.evaluate(() =>
    document.getElementById("auth-container")?.classList.contains("hidden")
  );
  const chatVisible = await page.evaluate(() =>
    !document.getElementById("chat-container")?.classList.contains("hidden")
  );
  if (!authHidden || !chatVisible) {
    throw new Error("After refresh: returned to login (session restore failed)");
  }
  console.log("   OK: Still in chat after refresh");

  const restoredLog = consoleErrors.some((e) => e.includes("[SESSION] Restored"));
  if (restoredLog) console.log("   OK: [SESSION] Restored log seen");

  console.log("5. Wait for WS reconnect attempts (8s)...");
  await page.waitForTimeout(8000);

  const wsFails = consoleErrors.filter((e) => e.includes("WebSocket connection"));
  const api415 = failedRequests.filter((e) => e.includes("415"));
  const api500 = failedRequests.filter((e) => e.includes("500") && e.includes("history"));

  console.log("\n=== SUMMARY ===");
  console.log("User tested:", user);
  console.log("Session restore after refresh:", authHidden && chatVisible ? "PASS" : "FAIL");
  console.log("415 errors:", api415.length, api415.length ? api415.slice(0, 3) : "(none)");
  console.log("500 history errors:", api500.length, api500.length ? api500.slice(0, 3) : "(none)");
  console.log("WebSocket console errors:", wsFails.length, wsFails.length ? "(Java server may be down)" : "(none)");
  if (consoleErrors.length) {
    console.log("\nOther console errors:", [...new Set(consoleErrors)].slice(0, 8).join("\n  "));
  }
  if (failedRequests.length) {
    console.log("\nFailed HTTP (sample):", [...new Set(failedRequests)].slice(0, 8).join("\n  "));
  }

  await browser.close();

  if (api415.length) process.exit(1);
  if (!authHidden) process.exit(1);
}

main().catch((e) => {
  console.error("TEST FAILED:", e.message);
  process.exit(1);
});
