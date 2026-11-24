# Data flow analysis (Layer E)

## Contents
- What to establish for each important datum
- Finding the data that matters
- Trust boundaries
- Validation and authorization
- Ownership
- Sensitive data
- Output format

## What to establish for each important datum

For each piece of data that matters to the question (a user record, an order, a token, a game save, a model input), answer:

1. **Origin**: where does it enter the system? (user input, file, API response, database, sensor, another service)
2. **Transformations**: where is it parsed, normalised, enriched, converted? Which functions?
3. **Storage**: where is it persisted or cached, in what shape, with what lifetime?
4. **Consumers**: which components read it, and which assumptions do they make about its shape and validity?
5. **Validation**: where is it checked, and is that the only place?
6. **Authorization**: where is access to it decided?
7. **Error propagation**: what happens to it when a step fails?
8. **Owner**: which component is the single source of truth, and who else writes to it?

## Finding the data that matters

Start from model/schema definitions (ORM models, migrations, type definitions, protobuf/GraphQL schemas), then search for their names to find producers and consumers. The dependency graph shows which files import a model; reading shows whether they read it, write it, or only pass it through. For configuration data, the model's `env:` nodes list environment variables read in source and the files that read them.

## Trust boundaries

A trust boundary is where data crosses from a less-trusted to a more-trusted context: network → process, user → server, client → server, external API → internal logic, plugin → host, file system → parser. Identify each boundary on a flow and ask what is enforced there. Typical signs of missing enforcement: input used in a query, path, shell command, template or deserializer without validation; a client-supplied identifier used to select a record with no ownership check; a client-trusted value (price, role, score) used for a decision on the server.

## Validation and authorization

List the points where each occurs, with `file:symbol`. Then look for gaps:
- validation only in the UI, not at the boundary that matters;
- validation in one entry point but not a second path to the same logic (for example an admin route or a background job);
- an authorization check present on most routes with one exception;
- the same rule implemented in two places with different strictness.

A gap is VERIFIED only when you read the unchecked path. If you only see that a check is absent in the code you read, say what you did not read.

## Ownership

Each important datum should have one component that owns it. Signs of unclear ownership: several modules write the same table or key; derived values stored in more than one place with no update rule; caches with no invalidation owner. State what you saw and why it creates risk (inconsistency, race, drift) at this project's scale.

## Sensitive data

Identify where credentials, tokens, personal data and payment data flow, by reading the code that handles them. Do **not** open files likely to hold real secret values (`.env`, key files, credentials); the scripts skip them and so should you. If you need to know which variables are required, read the `.env.example` or the code that reads them. If you encounter a secret in a file you had to read, refer to it by name and location only, and do not repeat the value in output.

## Output format

A compact table per flow of interest:

| Datum | Origin | Transformed in | Stored in | Consumed by | Validated at | Authorized at | Owner |
|---|---|---|---|---|---|---|---|

Use `—` for "none found" and `?` for "not determined". Cells that are not directly read take an `(inferred)` suffix. Follow the table with the specific gaps found, each with evidence and confidence.
