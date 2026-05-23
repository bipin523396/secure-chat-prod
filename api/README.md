# API on Render only

Do not add Python files here. Vercel would deploy them as serverless functions without Firebase credentials.

All API traffic: `https://secure-chat-prod.onrender.com/api`

`vercel.json` redirects `/api/*` to Render for old bookmarks.
