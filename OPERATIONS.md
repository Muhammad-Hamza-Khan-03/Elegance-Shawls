# Operations runbook

## Launch gate

- CI is green for the exact commit being deployed.
- Production environment values are present and use final HTTPS origins.
- MongoDB is private, authenticated, TLS-enabled and not exposed to the internet.
- Quill authentication, create/update/publish/unpublish/archive and inventory changes are verified in staging.
- Browse, filter, product selection, inventory display and WhatsApp order text are verified on desktop and mobile.
- Delivery, returns, privacy, terms and contact wording has been approved by the business owner.
- DNS, TLS, reverse proxy limits and backups have been tested.

## Health and monitoring

Monitor the frontend `/api/health` for liveness and `/api/ready` for configuration/backend connectivity. Monitor backend `/health/` for process liveness and `/ready/` for MongoDB connectivity. Alert after two consecutive readiness failures and on elevated 5xx responses, latency, CPU, memory, disk use or restart count.

Retain reverse-proxy and container logs centrally with timestamps, request method/path, status, duration and a request identifier. Never log `X-Admin-Key`, MongoDB credentials, customer WhatsApp messages, addresses or payment details. Configure retention appropriate to operational and legal needs and restrict log access.

## Backup and restore

- Take encrypted MongoDB backups at least daily, with retention agreed by the owner.
- Store backups in a separate account/location from the running database.
- Limit backup credentials to the required database and operations.
- Perform and record a restore drill before launch and regularly thereafter.
- A backup is not considered valid until a restore into an isolated environment succeeds and product/variant counts are checked.

## Incident response

1. Confirm impact using health endpoints and recent deployment/log data.
2. Stop further risky changes; revoke exposed credentials immediately.
3. Roll back application images when the incident follows a deployment.
4. Restore data only from a verified backup and preserve evidence before destructive action.
5. Record timeline, impact, resolution and preventative action. Notify affected parties where applicable.

## Key rotation

Create a new random `ADMIN_API_KEY`, update backend and Quill secret stores in a coordinated maintenance window, deploy/restart the backend, verify one authenticated request, then revoke the old value. Rotate MongoDB credentials through the provider without embedding them in images or commits.

## Routine maintenance

Review Dependabot pull requests weekly. Merge only after CI and compatibility review. Apply security updates promptly, avoid unreviewed major upgrades, review rate-limit behavior and logs monthly, and rehearse rollback and restore procedures before high-traffic campaigns.
