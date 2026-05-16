Synthetic fixture: a mini Prisma schema and a mini SQLModel module that
share a table name (`SharedThing` / `shared_thing`) but disagree on
column nullability. `test_parity_drift_fixture_fails` runs the parity
logic against this fixture and asserts that the structured diff names
the divergent column.
