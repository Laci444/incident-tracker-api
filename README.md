# Cloud-Native Incident & Release Management REST API

A Level 3 RESTful Web API built with **Python (Litestar)** and **SQLAlchemy (SQLite)** for tracking cloud-native microservices, software releases, and production incidents.

---

## 1. How the API Satisfies Roy Fielding's REST Architectural Constraints

This project strictly adheres to the architectural constraints defined in Roy Fielding's dissertation (*Architectural Styles and the Design of Network-based Software Architectures*, Chapter 5):

### 1.1 Client–Server Separation
* **Separation of Concerns:** The server exclusively manages persistent domain state (services, releases, incidents), business validation, and hypermedia generation, while clients (browsers, Bruno CLI, or frontends) handle user interface rendering and workflow orchestration.
* **Cross-Origin Interoperability:** Full CORS support (`app/config.py`) decouples client hosting from API hosting, exposing hypermedia (`Link`), caching (`ETag`, `Last-Modified`, `Cache-Control`), and creation (`Location`) headers to independent client applications.

### 1.2 Statelessness
* **Zero Server-Side Session State:** The server does not create, store, or reference any session cookies, in-memory session stores, or client navigation context (`app/security/auth.py`).
* **Self-Contained Requests:** Every request to a protected operation carries complete authentication state via the standard `Authorization: Basic <credentials>` HTTP header. Pagination (`?limit=&offset=`) and filtering state (`?status=&severity=`) are passed entirely within the request URI.

### 1.3 Cacheability
* **Explicit Cache Control:** Every `GET` and `HEAD` response includes an explicit `Cache-Control` header (`public, max-age=..., must-revalidate` for public resources; `private, max-age=60, must-revalidate` for user-aware representations) alongside `Vary: Accept, Authorization`. Error responses explicitly carry `Cache-Control: no-store`.
* **Conditional Requests & Revalidation:** All resources compute strong SHA-256 `ETag` identifiers and provide `Last-Modified` timestamps (`app/core/caching.py`). Clients revalidating cached representations with `If-None-Match` or `If-Modified-Since` receive an empty `304 Not Modified` response when state has not changed.

### 1.4 Uniform Interface
The API implements all four sub-constraints of the Uniform Interface and reaches **Level 3 of the Richardson Maturity Model**:

1. **Identification of Resources:**
   * The API exposes **8 distinct resource types** across 3 related domain entities (`Service`, `Release`, `Incident`), each identified by a canonical, hierarchical URI pattern (see Section 2).
   * Resource identity is decoupled from representation format: `/api/services/1` identifies the same service whether negotiated as `application/hal+json`, `application/json`, or `application/xml`.
2. **Manipulation of Resources Through Representations:**
   * Clients create, replace, partially update, and delete resources using standard representations (`application/json` for `POST`/`PUT`, and **RFC 7396 `application/merge-patch+json`** for `PATCH`, including explicit `null` field clearing).
   * Concurrent update safety (preventing the "Lost Update" problem) is enforced via conditional `If-Match` headers yielding `412 Precondition Failed` on state mismatch.
3. **Self-Descriptive Messages:**
   * Every request and response declares its exact syntax and semantics via standard media types (`application/hal+json`, `application/json`, `application/xml`, `application/merge-patch+json`, `application/problem+json`, `application/problem+xml`).
   * HTTP methods follow **RFC 9110** semantics (`GET`, `HEAD`, `OPTIONS` are safe and idempotent; `PUT` and `DELETE` are idempotent; `POST` creates subordinate resources and returns `201 Created` with a `Location` header).
   * All error responses conform to **RFC 9457 (Problem Details for HTTP APIs)** with machine-readable `type`, `title`, `status`, `detail`, and `instance` fields.
4. **Hypermedia as the Engine of Application State (HATEOAS):**
   * Starting from the single entry point (`/api`), clients discover all collections, subordinate resources, and available state transitions dynamically without hardcoding URI templates.
   * Hypermedia controls are provided both inside the response body using **HAL (`_links` and `_embedded`)** and in the **RFC 8288 `Link` HTTP response header**.
   * Links use **IANA-registered link relation types** (`self`, `collection`, `item`, `up`, `related`, `author`, `first`, `next`, `prev`, `create-form`, `edit`, `delete`, `describedby`, `help`) and are dynamically filtered based on the authenticated user's role and resource ownership.

### 1.5 Layered System
* The application is structured as an ASGI pipeline (`ProtocolComplianceMiddleware` $\rightarrow$ `StatelessBasicAuthMiddleware` $\rightarrow$ Litestar Router) and relies on standard HTTP caching (`Cache-Control`, `Vary`, `ETag`) and security headers (`Content-Security-Policy`), allowing reverse proxies, CDNs, or API gateways to be placed in front of the service transparently.

### 1.6 Code-On-Demand (Optional)
* As permitted by Fielding's dissertation and the project specification, Code-On-Demand is optional. While pure API responses enforce `Content-Security-Policy: default-src 'none'`, the interactive `/schema/swagger` endpoint delivers executable JavaScript to browser clients to render the OpenAPI specification dynamically.

---

## 2. Exposed Resource Types & URI Matrix (8 Resource Types)

| # | Resource Type | URI Pattern | Supported HTTP Methods | Related Entities |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **API Entry Point** | `/api` | `GET`, `HEAD`, `OPTIONS` | Links to Services, Incidents, Profile, OpenAPI |
| **2** | **Service Collection** | `/api/services` | `GET`, `HEAD`, `POST`, `OPTIONS` | Contains `Service` items |
| **3** | **Service Item** | `/api/services/{service_id}` | `GET`, `HEAD`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | Has many `Releases` and `Incidents` |
| **4** | **Service Releases Collection** | `/api/services/{service_id}/releases` | `GET`, `HEAD`, `POST`, `OPTIONS` | Belongs to `Service`; contains `Release` items |
| **5** | **Release Item** | `/api/releases/{release_id}` | `GET`, `HEAD`, `PATCH`, `DELETE`, `OPTIONS` | Belongs to `Service`; linked to `Incidents` |
| **6** | **Incident Collection** | `/api/incidents` | `GET`, `HEAD`, `POST`, `OPTIONS` | Contains `Incident` items |
| **7** | **Incident Item** | `/api/incidents/{incident_id}` | `GET`, `HEAD`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | References `Service`, optional `Release`, and `User` |
| **8** | **Authenticated User Profile** | `/api/me` | `GET`, `HEAD`, `OPTIONS` | Links to Incidents reported by the current user |

---

## 3. Stateless Authentication & RBAC Users

Authentication uses **HTTP Basic Authentication** over stateless requests. Three built-in accounts demonstrate role-based and ownership-based access restrictions:

| Username | Password | Role | Permissions |
| :--- | :--- | :--- | :--- |
| `admin` | `admin123` | `admin` | Full read/write access; can modify or delete any resource (including `DELETE /api/services/{id}`). |
| `dev_alice` | `alice123` | `developer` | Can create services, releases, and incidents; can `PUT`/`PATCH`/`DELETE` **only** releases and incidents she created (`403 Forbidden` on others' resources or service deletion). |
| `viewer_bob` | `bob123` | `viewer` | Read-only (`GET`, `HEAD`, `OPTIONS`); receives `403 Forbidden` on any state-changing operation. |

---

## 4. Setup & Running the Application

### Prerequisites
* Python 3.11+

### Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
