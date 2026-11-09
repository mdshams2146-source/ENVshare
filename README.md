# EnvShare

EnvShare is a centralized, secure environment configuration manager built for modern engineering teams. It streamlines the distribution of environment variables across development, staging, and production tiers while ensuring sensitive secrets are protected using AES-256-GCM authenticated symmetric encryption.

---

## Key Features

- **Role-Based Access Control (RBAC):** Granular access management for project owners and collaborators, backed by JSON Web Token (JWT) stateless authentication with session revocation and rate limiting.
- **Multi-Environment Isolation:** Dedicated variable separation across Development, Staging, and Production stages for each project.
- **Zero-Exposure Secret Management:** Sensitive credentials and API tokens are encrypted at rest with AES-256-GCM with unique initialization vectors (IV). The frontend displays masked placeholders (`••••••••`) by default, with on-demand authenticated server-side decryption.
- **Smart Diff & Bulk Import Engine:** Parses raw `.env` files with server-authoritative diff generation and duplicate-key detection. Visualizes changes (`NEW`, `UPDATE`, `UNCHANGED`) before committing, automatically classifies secret keys, and redacts sensitive plaintext from diff responses.
- **One-Click `.env` Export:** Exports live project configurations with safety warnings for masked sensitive secrets.
- **Audit Timeline & Revert:** Complete chronological ledger documenting configuration changes with masked secret values, actor identities, and owner-only rollback protections.
- **Environment Snapshots & Recovery:** Point-in-time encrypted snapshot backups and owner-controlled atomic rollbacks.
- **Direct Project Invitations:** Cryptographically secure, single-use, time-limited shareable invitation links for adding team members.
- **Password Reset Service:** Rate-limited password reset flow with single-use tokens and active session invalidation on password change.

---

## Role-Permission Matrix (RBAC)

| Capability | OWNER | MEMBER |
|---|:---:|:---:|
| View Variables (masked secrets) | Yes | Yes |
| Reveal Sensitive Variables (on-demand) | Yes | Yes |
| Create / Update Variables | Yes | Yes |
| Delete Variables | Yes | Yes |
| Smart Import (.env) | Yes | Yes |
| Export .env Configuration | Yes | Yes |
| View Environment Audit History | Yes | Yes |
| Revert Individual Audit Log Entries | Yes | No |
| Create Environment Snapshots | Yes | Yes |
| Rollback Environment to Snapshot | Yes | No |
| Generate Project Invitation Links | Yes | No |
| View Project Members | Yes | Yes |

---

## Tech Stack

### Frontend
- **Framework:** React 19 + TypeScript (bundled with Vite)
- **Styling:** Tailwind CSS
- **Icons:** Lucide React
- **Client Networking:** Axios (configured with automated JWT interceptors)
- **Deployment:** Vercel (Edge CDN)

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **Server:** Uvicorn / Gunicorn ASGI
- **Database & ORM:** SQLAlchemy with SQLite (configured with WAL mode, busy timeout, and connection pooling for concurrent reliability)
- **Security & Cryptography:** pwdlib (Bcrypt password hashing), PyJWT, Cryptography (AES-256-GCM)
- **Email Dispatch:** SMTP TLS Dispatcher
- **Deployment:** Render (Containerized Web Service)

---

## System Architecture

```text
               +----------------------------------+
               |        React + Vite SPA          |
               |        (Hosted on Vercel)        |
               +-----------------+----------------+
                                 |
                          HTTPS Requests
                     (Bearer JWT Authorization)
                                 |
                                 v
               +----------------------------------+
               |         FastAPI Gateway          |
               |        (Hosted on Render)        |
               +--------+--------+--------+-------+
                        |        |        |
         +--------------+        |        +---------------+
         |                       |                        |
         v                       v                        v
+-----------------+    +-------------------+    +-------------------+
|  SQLite Storage |    |  AES-256-GCM      |    | SMTP Mail Service |
| (Users, Audit,  |    |  Crypto Engine    |    | (Password Resets) |
|  Environments)  |    | (Secret Masking)  |    |                   |
+-----------------+    +-------------------+    +-------------------+
```
