# WSO2 products

Product 1 and Product 2 use one WSO2 Asgardeo application, one client, and one user. Both pages read the same `sub` from the ID token.

Open http://localhost:5173

| Product | Address |
|---|---|
| Product 1 | http://localhost:5173 |
| Product 2 | http://localhost:5173/product-2 |

Client ID: `ahQZlLlBeI8NlRDwTBHkGqSfXqUa`

Organization: `orgkrx7r`

Base URL: `https://api.eu.asgardeo.io/t/orgkrx7r`

The Asgardeo application allows the redirect `http://localhost:5173`. Both products stay on that address, so sign-in returns to the app instead of an error page. Sign in on either product. The other product opens with the same WSO2 session and the same `sub`.

## Run

```powershell
cd C:\Users\USER\OneDrive\Desktop\Wso2\apps\product-1
npm install
npm run dev
```

The values are already in `apps/product-1/.env`.

Sign-in is the WSO2 page for this application. It offers passkey and email OTP. This app does not ask for its own password.

## Architecture

The browser loads `@asgardeo/react`. `signIn()` starts the authorization-code flow with PKCE and does not send `prompt=login`. Asgardeo redirects back to `http://localhost:5173`. The SDK stores the tokens for that origin. Product 1 and Product 2 are two areas of that session, so opening the other product does not ask for credentials again. Each profile calls `getDecodedIdToken()` and shows `sub`.

Sign-out uses the SDK. It clears the local tokens and sends the browser to the Asgardeo sign-out endpoint, which ends the organization session. The user comes back to `http://localhost:5173`.

## Vercel

Deploy `apps/product-1`. `vercel.json` sends every path to `index.html`.

| Variable | Value |
|---|---|
| `VITE_ASGARDEO_CLIENT_ID` | `ahQZlLlBeI8NlRDwTBHkGqSfXqUa` |
| `VITE_ASGARDEO_BASE_URL` | `https://api.eu.asgardeo.io/t/orgkrx7r` |
| `VITE_APP_ORIGIN` | the Vercel origin, with no path |
| `VITE_OTHER_PRODUCT_URL` | that origin plus `/product-2` |

Add the Vercel origin to the Asgardeo application's authorized redirect URL and post-logout redirect URL. It must match `VITE_APP_ORIGIN` exactly.

## Later WSO2 options

These stay in the Asgardeo console. The products do not implement them.

Email OTP and passkey are already on this application's sign-in page. MFA, TOTP, passwordless login, and email verification are further login-flow or account settings in the same organization. User provisioning is the SCIM2 Users API from a confidential management application. That secret does not belong in this React app.

## Test results

Checked on 27 November 2026.

| Check | Result |
|---|---|
| Product 1 at http://localhost:5173 | Pass. Title WSO2 Products, sign-in button visible. |
| Product 2 at http://localhost:5173/product-2 | Pass. Own heading, dashboard, profile, and link back to Product 1. |
| Protected dashboard while signed out | Pass. `/dashboard` returned to the Product 1 home. |
| Sign-in | Pass. The button opened `https://accounts.eu.asgardeo.io/t/orgkrx7r/authenticationendpoint/login.do` for client `ahQZlLlBeI8NlRDwTBHkGqSfXqUa`, redirect `http://localhost:5173`, scope `openid profile`, PKCE S256. The page offered Sign In With Passkey and Sign In With Email OTP. No application error. |
| Same `sub` after a completed login | Waiting on a passkey or email OTP sign-in. The profile page shows `sub` from the ID token as soon as that finishes. |
