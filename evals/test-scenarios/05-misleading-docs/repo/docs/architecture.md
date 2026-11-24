# Architecture

The service is strictly layered: HTTP handlers call the service layer, and only the
repository layer touches the database. Handlers must never import the database module.
