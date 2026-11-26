# WSO2 Asgardeo SSO Demo

A proof-of-concept application demonstrating centralized authentication and product-level access management using **WSO2 Asgardeo**.

The demo provides a single sign-in experience for two sample applications — **Finance Management System (FMS)** and **Point of Sale (POS)** — with an administrative portal to manage customer accounts and product permissions.

> **Project status:** Local proof of concept (PoC). This project uses dummy product data and SQLite. It is not connected to any production database or business application.

## Run the app

Use two terminals. Start the backend first and leave it running.

**Backend** (from the project folder):

```powershell
cd C:\Users\USER\OneDrive\Desktop\Wso2
backend\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The API listens at http://127.0.0.1:8000.

**Frontend** (second terminal):

```powershell
cd C:\Users\USER\OneDrive\Desktop\Wso2\frontend
npm run dev
```

Open http://localhost:5173. Do not use port 8000 in the browser. Vite proxies `/api` to the backend so the session cookie stays on one origin.

The first time you set the machine up, create the virtual environment, install packages, and copy `.env.example` to `.env`. Those steps are in [Getting Started](#getting-started). A local `.env` with no Asgardeo client id is enough to run in mock mode. Asgardeo values are only needed for a real login.

Sign in with `DemoPass123!`:

| Account | Email | FMS | POS |
|---|---|---|---|
| Customer A | customer.a@demo.local | Allowed | Denied |
| Customer B | customer.b@demo.local | Allowed | Allowed |
| Customer C | customer.c@demo.local | Denied | Allowed |
| Portal Admin | admin@demo.local | Allowed | Allowed |

The sign-in page is only an email and password form. It does not list these accounts, show the password, show a mock-mode banner, or link to the security report. After sign-in, the header still has the security report, and the portal shows a mock-mode notice while Asgardeo is not configured.

## Key Features

- **Centralized Authentication:** One login experience for FMS and POS using a single OIDC client.
- **WSO2 Asgardeo Integration:** Authorization Code Flow with PKCE.
- **Mock Authentication:** Local dummy authentication for development and testing.
- **Product-Level Access Control:** Grant or revoke FMS and POS access independently.
- **Admin Portal:** Activate, deactivate, and manage customer accounts.
- **Email Verification Awareness:** Displays the `email_verified` claim returned by Asgardeo.
- **MFA Awareness:** Displays authentication methods (`amr`) returned in the ID token.
- **Session Management:** Supports session expiration and logout.
- **Security Testing:** Automated security checks with a generated security report.
- **Dynamic Authorization:** Product permissions are checked against SQLite on every API request.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React |
| Frontend tooling | Vite |
| Backend | Python, FastAPI |
| Authentication | WSO2 Asgardeo, OpenID Connect |
| Authorization | JWT validation and server-side access checks |
| Database | SQLite |
| Security | Authorization Code Flow, PKCE, session management |
| Testing | Python security test script |

## System Architecture

```text
                  User
                   |
                   v
          React Web Application
             (localhost:5173)
                   |
                   v
             FastAPI Backend
             (localhost:8000)
                   |
          +--------+--------+
          |                 |
          v                 v
    WSO2 Asgardeo       SQLite Database
    Authentication     User & Permissions
          |                 |
          +--------+--------+
                   |
                   v
           Authorization Check
                   |
             +-----+-----+
             |           |
             v           v
           FMS           POS
```

Both FMS and POS are protected routes within the same demo application and use the same OIDC client and demo session.

## Project Structure

```text
wso2-identity-platform-demo/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   └── ...
│   ├── requirements.txt
│   ├── run_security_tests.py
│   └── demo.db
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── ...
│
├── .env.example
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

Install the following:

- Python 3.10 or later
- Node.js and npm
- Git
- A WSO2 Asgardeo organization (only required for real authentication)

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/wso2-identity-platform-demo.git
```

Navigate to the project:

```bash
cd wso2-identity-platform-demo
```

### 2. Set Up the Backend

Create a Python virtual environment:

```powershell
python -m venv backend\.venv
```

Install the dependencies:

```powershell
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
```

Create the environment configuration:

```powershell
copy .env.example .env
```

Update the `.env` file with the required configuration.

### 3. Run Security Tests

```powershell
backend\.venv\Scripts\python backend\run_security_tests.py
```

The generated report is saved to:

```text
backend/security-report.json
```

### 4. Start the Backend Server

```powershell
backend\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Backend URL:

http://localhost:8000

### 5. Set Up the Frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend URL:

http://localhost:5173

> **Important:** Open the frontend using port `5173`, not port `8000`. Vite proxies API requests to the backend so the session cookie remains on the same browser origin.

## Authentication Modes

The application supports two authentication modes.

### 1. WSO2 Asgardeo Mode

When valid Asgardeo configuration is provided and mock mode is not enabled, users are redirected to WSO2 Asgardeo for authentication.

The implementation uses:

- OpenID Connect (OIDC)
- Authorization Code Flow
- Proof Key for Code Exchange (PKCE)
- ID token validation
- Email claim handling
- Authentication method claim handling (`amr`)

The client secret, if required, is stored and used only by the backend.

### 2. Mock Authentication Mode

Mock mode allows developers to test the application without configuring an Asgardeo organization.

- Uses local dummy accounts.
- Validates a local demo password.
- Shows a mock-mode notice on the portal after sign-in. The sign-in form itself does not show that notice.
- Does not perform real Asgardeo authentication.

**Important:** Successful mock authentication does not demonstrate real SSO, email verification, email OTP, or TOTP.

Setting `MOCK_MODE=false` disables mock authentication. The application will not fall back to dummy sign-in.

## WSO2 Asgardeo Configuration

To enable real authentication:

### Step 1: Create an OIDC Application

1. Sign in to your WSO2 Asgardeo Console.
2. Create a new OIDC application.
3. Enable the Authorization Code grant.
4. Enable PKCE.

### Step 2: Configure Redirect URLs

**Authorized Redirect URL**

```text
http://localhost:5173/api/auth/callback
```

**Post Logout Redirect URL**

```text
http://localhost:5173/
```

### Step 3: Configure User Attributes

Release the `email` attribute so the application can identify authenticated users.

### Step 4: Configure Environment Variables

Update the backend `.env` file:

```env
ASGARDEO_CLIENT_ID=your_client_id
ASGARDEO_ORGANIZATION=your_organization_handle

ASGARDEO_CLIENT_SECRET=your_client_secret

MOCK_MODE=auto
```

Alternatively, configure `ASGARDEO_BASE_URL` if you want to provide the organization base URL directly.

Use the client secret only for a confidential application that requires it.

**Security:** Never expose client secrets or other credentials in frontend code or commit them to GitHub.

### Step 5: Enable Email Verification and MFA

Configure the required authentication steps in the Asgardeo login flow.

Possible authentication steps include:

- Email verification
- Email OTP
- TOTP-based authentication

These authentication challenges are handled by Asgardeo, not recreated by this demo.

After successful authentication, the portal displays the available `email_verified` and `amr` claims returned by Asgardeo. Missing claims are reported as not present rather than assumed to have passed.

Restart the backend after changing environment variables.

## User and Product Access Management

The admin portal manages customer accounts and product permissions.

Each user has three important authorization properties:

| Property | Description |
|---|---|
| `active` | Determines whether the account is active |
| `fms_access` | Controls access to FMS |
| `pos_access` | Controls access to POS |

### Demo Accounts

All seeded accounts use the following dummy password:

```text
DemoPass123!
```

| Account | Email | FMS | POS |
|---|---|---|---|
| Customer A | customer.a@demo.local | Allowed | Denied |
| Customer B | customer.b@demo.local | Allowed | Allowed |
| Customer C | customer.c@demo.local | Denied | Allowed |
| Portal Admin | admin@demo.local | Allowed | Allowed |

The sign-in page does not display the seeded account list.

### Access Control Behaviour

- Customer A can access FMS but cannot access POS.
- Customer B can access both FMS and POS.
- Customer C can access POS but cannot access FMS.
- Administrators can manage customer access through the admin portal.
- Inactive accounts cannot access protected product APIs.

New Asgardeo users who are not listed in `ADMIN_EMAILS` are created as inactive customers with no product access until an administrator activates them.

### Dynamic Permission Checking

Product permissions are retrieved from SQLite on every API request.

They are not copied into the session JWT.

This ensures that when an administrator revokes FMS or POS access, the change applies to an existing session on its next protected API request.

## Session Management

The application includes basic session management.

| Feature | Behaviour |
|---|---|
| Session duration | Configurable using `SESSION_MINUTES` |
| Default duration | 15 minutes |
| Expire Session Now | Marks the server-side session as expired |
| Log Out | Deletes the session |
| Expired session | Further requests are rejected |
| Unknown session | Rejected by the backend |

The portal provides two different actions:

- **Expire Session Now:** Keeps the session record but marks it expired.
- **Log Out:** Deletes the session so the previous token is rejected as an unknown session.

## Security Testing and Reporting

The project includes an automated security testing script:

```text
backend/run_security_tests.py
```

Run it using:

```powershell
backend\.venv\Scripts\python backend\run_security_tests.py
```

The script generates:

```text
backend/security-report.json
```

After sign-in, open **Security report** in the header. That page displays the generated results. The sign-in page does not link to it.

### Important Testing Limitations

The automated security test script runs API tests in mock mode using a temporary database.

Therefore:

- Mock-mode tests can pass without an Asgardeo organization.
- Hosted Asgardeo checks remain `not_tested` until a real organization is configured.
- A successful Asgardeo discovery request does not prove successful login.
- Automated mock tests do not prove email OTP, TOTP, or MFA functionality.

### Manual Security Testing

After configuring Asgardeo, perform the following checks:

1. Incorrect passwords are rejected by Asgardeo.
2. Users with `email_verified: false` do not receive a demo session.
3. Email OTP appears only when the relevant authenticator is configured.
4. TOTP appears only when the relevant authenticator is configured.
5. Logout returns through Asgardeo when an ID token is stored for the session.
6. Customer A receives `product_denied` when accessing the POS summary API.
7. Customer C receives `product_denied` when accessing the FMS API.
8. Customer B can access both products.
9. Revoking product access blocks the next protected API request.
10. Deactivating an account blocks the next protected API request.

## Security Considerations

Before sharing or deploying the project:

- Replace the default `SESSION_SECRET` with a long, randomly generated secret.
- Keep `.env` out of version control.
- Never expose Asgardeo client secrets in frontend code.
- Use HTTPS in production.
- Configure secure cookie attributes for production.
- Use a production-ready database instead of the local SQLite demo database.
- Review session expiration and token validation settings.
- Configure appropriate CORS and redirect URL restrictions.

This project is designed for local demonstration and technical evaluation, not production deployment.

## Current Limitations

- FMS and POS are dummy applications.
- Product data is not connected to a production database.
- Both applications use one OIDC client rather than separate Asgardeo applications.
- The demo does not implement its own email OTP or TOTP challenges.
- SQLite is used for local account and permission storage.
- The project does not establish production-grade enterprise SSO readiness.

**SSO clarification:** This demo demonstrates one authentication session providing access to two protected product routes. It does not demonstrate federation between two independently registered Asgardeo applications.

## Future Improvements

Potential improvements include:

- Centralized identity management for multiple business applications.
- Integration with real FMS and POS backends.
- Role-Based Access Control (RBAC).
- Multi-tenant customer management.
- Improved audit logging and security monitoring.
- Production database integration.
- Enterprise session and identity lifecycle management.
- Deployment with HTTPS and production security configurations.

## Author

**Nagendran Sanjeevan**

Final-Year BICT (Hons) Undergraduate  
Department of Information and Communication Technology  
Faculty of Technological Studies  
University of Vavuniya, Sri Lanka

## Disclaimer

This project is an educational and technical proof of concept developed to explore centralized authentication, OpenID Connect, WSO2 Asgardeo integration, session management, and product-level authorization.

It is not an official WSO2 product or a production-ready identity management solution.