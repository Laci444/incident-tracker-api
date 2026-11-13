# Cloud-Native Incident & Release Management REST API

A versioned, Level 3 RESTful Web API built with **Python (Litestar)** and **SQLAlchemy 2.0 (Async SQLite)** for managing cloud-native microservices, software releases, and operational incidents.

---

## 1. Satisfaction of Roy Fielding's REST Architectural Constraints

This API strictly satisfies all architectural constraints defined in Roy Fielding's dissertation (*Architectural Styles and the Design of Network-based Software Architectures*, Chapter 5):

### 1.1 Client–Server Separation
* **Separation of Concerns:** The server manages persistent domain state, relational integrity, and hypermedia controls, while clients independently handle presentation and workflow navigation.
* **Cross-Origin Resource Sharing (CORS):** Configured in `app/config.py` for all operations (including authenticated routes), exposing hypermedia (`Link`), caching (`ETag`, `Last-Modified`, `Cache-Control`), creation (`Location`), and method-discovery (`Allow`, `Accept-Patch`) headers to browser and CLI clients.

### 1.2 Statelessness
* **No Server-Side Session State:** The application stores zero session state in memory, cookies, or database tables (`app/security/auth.py`).
* **Self-Contained Requests:** Every protected request carries its own `Authorization: Basic <credentials>` header. Collection pagination (`?limit=&offset=`) and filtering (`?status=&severity=&service_id=&release_id=`) are expressed entirely via URI query parameters.

### 1.3 Cacheability
* **Explicit Caching Directives:** Every `GET` and `HEAD` response carries an explicit `Cache-Control` header (`public, max-age=..., must-revalidate` for public resources; `private, max-age=60, must-revalidate` for user-contextual representations) and `Vary: Accept, Authorization`. Error responses enforce `Cache-Control: no-store`.
* **Early Conditional Request Evaluation (`304` & `412`):** The `ResourceStateRegistry` (`app/core/caching.py`) stays synchronized with SQLAlchemy ORM lifecycle events (`after_insert`, `after_update`, `after_delete`). A `before_request` hook evaluates `If-None-Match` and `If-Modified-Since` headers *before* controller execution, returning `304 Not Modified` without redundant database queries, and enforces optimistic concurrency control via `If-Match` (`412 Precondition Failed`).

### 1.4 Uniform Interface (Richardson Maturity Model Level 3)
1. **Identification of Resources:**
   * The API exposes **9 distinct resource types** across a version-agnostic discovery root (`/api`), a versioned entry point (`/api/v1`), an authenticated user profile (`/api/v1/me`), and **3 related domain entities** (`Service`, `Release`, `Incident`).
   * Resource identity is independent of representation format (`application/hal+json`, `application/json`, or `application/xml`).
2. **Manipulation of Resources Through Representations:**
   * Clients create (`POST`), replace (`PUT`), partially modify (`PATCH`), and remove (`DELETE`) resources using standard representations.
   * Partial updates strictly follow **RFC 7396 (JSON Merge Patch)** with `Content-Type: application/merge-patch+json`, distinguishing omitted fields (`msgspec.UNSET`) from explicit `null` values that clear nullable fields (`release_id`, `resolution_notes`, `release_notes`).
3. **Self-Descriptive Messages:**
   * Requests and responses declare explicit media types (`application/hal+json`, `application/json`, `application/xml`, `application/merge-patch+json`, `application/problem+json`, `application/problem+xml`).
   * HTTP methods follow **RFC 9110** semantics (`GET`, `HEAD`, `OPTIONS` on all resources; `POST` returning `201 Created` with `Location`; idempotent `PUT` and `DELETE`).
   * Every error response (`400`, `401`, `403`, `404`, `405`, `406`, `409`, `412`, `415`, `422`) conforms to **RFC 9457 (Problem Details for HTTP APIs)** in JSON or XML format based on the client's `Accept` header.
4. **Hypermedia as the Engine of Application State (HATEOAS):**
   * Starting from `/api`, clients discover API versions (`latest-version` -> `/api/v1`), collections, related entities, and allowed state transitions dynamically.
   * The `HypermediaAssembler` (`app/core/hypermedia.py`) inspects SQLAlchemy relationships and declarative resource metadata to generate both **HAL (`_links`, `_embedded`)** body controls and **RFC 8288 `Link` HTTP headers** using IANA-registered relations (`self`, `collection`, `item`, `up`, `related`, `author`, `about`, `first`, `next`, `prev`, `create-form`, `edit`, `delete`, `latest-version`, `describedby`, `help`).
   * State-changing links (`create-form`, `edit`, `delete`) are dynamically included or omitted based on the authenticated user's role and resource ownership.

### 1.5 Layered System
* Implemented via an ASGI middleware and presentation pipeline (`SecurityHeadersMiddleware` -> `ProtocolNegotiationMiddleware` -> `StatelessBasicAuthMiddleware` -> `early_conditional_request_hook` -> Thin Controllers -> `Service` Layer -> `BaseRepository` -> `HalNegotiatedResponse`).
* Strict `Content-Security-Policy` headers (`default-src 'none'; frame-ancestors 'none'`) are applied to all API responses, while a tailored policy is served on `/schema/*` so interactive Swagger UI assets can execute safely.

### 1.6 Code-On-Demand (Optional)
* Pure API endpoints return static data representations, whereas `/schema/swagger` delivers executable JavaScript to browser clients to render interactive API documentation.

---

## 2. Layered Architecture Overview

```text
app/
├── config.py                # CORS, CSP policies, DB path, and OpenAPI configuration
├── main.py                  # Litestar app assembly, v1 Router, and DI wiring
├── core/
│   ├── enums.py             # Composite StrEnums (paths, routes, media types, headers, IANA rels)
│   ├── exceptions.py        # Semantic RFC 9457 ProblemException hierarchy & handler
│   ├── caching.py           # SQLAlchemy-synced ResourceStateRegistry & early 304/412 hook
│   ├── hypermedia.py        # Relationship-driven HypermediaAssembler (HAL + RFC 8288 Link header)
│   ├── renderers.py         # HalNegotiatedResponse (JSON/HAL/XML negotiation & HEAD handling)
│   ├── middleware.py        # SecurityHeadersMiddleware (CSP) & ProtocolNegotiationMiddleware (406/415/OPTIONS)
│   └── openapi.py           # OpenAPI header definitions, ProblemDetailsDTO, and error catalogs
├── security/
│   ├── auth.py              # Stateless HTTP Basic Authentication middleware
│   └── guards.py            # Role-based (Admin/Developer/Viewer) and ownership authorization
├── db/
│   ├── base.py              # Async SQLAlchemy engine with SQLite foreign key enforcement
│   ├── models.py            # ORM models with SQL CHECK/Enum constraints & ResourceMetadata
│   └── seed.py              # Idempotent initial database seeder
├── schemas/                 # msgspec validation DTOs, RFC 7396 MergePatchBase & OpenAPI response DTOs
├── repositories/
│   └── base.py              # Generic BaseRepository (get_or_404, pagination, constraint handling)
├── services/                # HTTP-agnostic business logic (ServiceCatalogService, ReleaseService, IncidentService)
└── controllers/             # Thin versioned route handlers (/api and /api/v1/*)

```

---

## 3. Exposed Resource Types & URI Matrix (9 Resource Types)

| # | Resource Type | URI Pattern | Supported HTTP Methods | Related Entities |
| --- | --- | --- | --- | --- |
| **1** | **API Discovery Root** | `/api` | `GET`, `HEAD`, `OPTIONS` | Links to `latest-version` (`/api/v1`), collections, and OpenAPI |
| **2** | **Versioned Entry Point (v1)** | `/api/v1` | `GET`, `HEAD`, `OPTIONS` | Links to Discovery Root, Services, Incidents, Profile, OpenAPI |
| **3** | **Service Collection** | `/api/v1/services` | `GET`, `HEAD`, `POST`, `OPTIONS` | Contains `Service` items |
| **4** | **Service Item** | `/api/v1/services/{service_id}` | `GET`, `HEAD`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | Has many `Releases` and `Incidents` |
| **5** | **Service Releases Collection** | `/api/v1/services/{service_id}/releases` | `GET`, `HEAD`, `POST`, `OPTIONS` | Belongs to `Service`; contains `Release` items |
| **6** | **Release Item** | `/api/v1/releases/{release_id}` | `GET`, `HEAD`, `PATCH`, `DELETE`, `OPTIONS` | Belongs to `Service`; links to associated `Incidents` |
| **7** | **Incident Collection** | `/api/v1/incidents` | `GET`, `HEAD`, `POST`, `OPTIONS` | Contains `Incident` items (filterable by service, release, status, severity) |
| **8** | **Incident Item** | `/api/v1/incidents/{incident_id}` | `GET`, `HEAD`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` | References `Service`, optional `Release`, and reporter (`author`) |
| **9** | **Authenticated User Profile** | `/api/v1/me` | `GET`, `HEAD`, `OPTIONS` | Links to Incidents reported by the authenticated user |

---

## 4. Stateless Authentication & RBAC Accounts

| Username | Password | Role | Access Permissions |
| --- | --- | --- | --- |
| `admin` | `admin123` | `admin` | Full read/write access; may modify or delete any resource (including `DELETE /api/v1/services/{id}`). |
| `dev_alice` | `alice123` | `developer` | Can create services, releases, and incidents; may `PUT`/`PATCH`/`DELETE` **only** releases and incidents she created (`403 Forbidden` on others' resources or service deletion). |
| `viewer_bob` | `bob123` | `viewer` | Read-only access (`GET`, `HEAD`, `OPTIONS`); receives `403 Forbidden` on any state-changing operation. |

---

## 5. Setup, Execution & Testing

### Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

```

### Docker Compose Execution

```bash
docker compose up --build -d

```

* **Discovery Root:** `http://localhost:8000/api`
* **API v1 Root:** `http://localhost:8000/api/v1`
* **Interactive Swagger UI:** `http://localhost:8000/schema/swagger`
* **Live OpenAPI JSON / YAML:** `http://localhost:8000/schema/openapi.json` (also exported statically in `openapi_schema.json`)

### Running the Bruno OpenCollection Test Suite

```bash
cd bruno
bru run --env local

```
