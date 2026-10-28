# EnvShare

EnvShare is a centralized, secure environment configuration manager built for modern engineering teams[cite: 1, 2]. It streamlines the distribution of environment variables across development, staging, and production tiers while ensuring sensitive secrets are protected using AES-256 Fernet symmetric encryption[cite: 1, 2].

---

## Key Features

- **Role-Based Access Control (RBAC):** Granular access management for project owners and collaborators, backed by JSON Web Token (JWT) stateless authentication[cite: 1, 2].
- **Multi-Environment Isolation:** Dedicated variable separation across Development, Staging, and Production stages for each project[cite: 1, 2].
- **Zero-Exposure Secret Management:** Sensitive credentials and API tokens are encrypted at rest with AES-256 (Fernet)[cite: 1, 2]. The frontend displays masked placeholders (`••••••••`) by default, with on-demand authenticated server-side decryption[cite: 1, 2].
- **Smart Diff & Bulk Import Engine:** Parses raw `.env` files directly in the browser, cleans comments and extraneous spacing, visualizes changes (`NEW`, `UPDATE`, `UNCHANGED`) before committing, and flags sensitive values dynamically.
- **One-Click `.env` Export:** Exports live project configurations formatted for instant local development setup.
- **Audit Timeline:** Complete chronological ledger documenting all configuration changes, including timestamps, modified keys, old vs. new values, and actor identities[cite: 1, 2].
- **Email Notifications:** Automated delivery of invitation alerts powered by the Resend REST API.

---

## Tech Stack

### Frontend
- **Framework:** React 19 + TypeScript (bundled with Vite)[cite: 1, 2]
- **Styling:** Tailwind CSS
- **Icons:** Lucide React
- **Client Networking:** Axios (configured with automated JWT interceptors)
- **Deployment:** Vercel (Edge CDN)

### Backend
- **Framework:** FastAPI (Python 3.11+)[cite: 1, 2]
- **Server:** Uvicorn / Gunicorn ASGI
- **Database & ORM:** SQLAlchemy with SQLite (configured for portability and straightforward migration to PostgreSQL)[cite: 1, 2]
- **Security & Cryptography:** Passlib (Bcrypt password hashing), PyJWT, Cryptography (Fernet AES-256)[cite: 1, 2]
- **Email Dispatch:** Resend SDK[cite: 1]
- **Deployment:** Render (Containerized Web Service)[cite: 1]

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
|  SQLite Storage |    |  Fernet Engine    |    | Resend API Client |
| (Users, Audit,  |    | (AES-256 Secret   |    | (Member Invites)  |
|  Environments)  |    |  Masking/Reveal)  |    |                   |
+-----------------+    +-------------------+    +-------------------+
