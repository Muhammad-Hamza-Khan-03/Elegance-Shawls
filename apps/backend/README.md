# Elegance Shawls product API

Public storefront reads use `GET /products/` and `GET /products/slug/{slug}`.
Administrative operations require the `X-Admin-Key` header. Configure the same
long random `ADMIN_API_KEY` in the API and trusted Quill Panel server. Never put
this secret in a `NEXT_PUBLIC_` variable or browser bundle.

Run contract and security tests with `pip install -r requirements-dev.txt`
followed by `pytest`.
