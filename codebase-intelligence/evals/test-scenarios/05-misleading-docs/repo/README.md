# Notes Service

A small notes API.

## Architecture
- **Database:** PostgreSQL accessed through SQLAlchemy models.
- **Auth:** stateless JWT bearer tokens issued at `/login`.
- **Cache:** Redis caches note listings for 60 seconds.

## Running
`flask --app app.server run`
