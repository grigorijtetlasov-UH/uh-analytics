from finance.db.connection import connect
import collections

cm = connect(); c = cm.__enter__(); cur = c.cursor()

cur.execute("SELECT table_schema, count(*) FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
            "GROUP BY table_schema ORDER BY 1")
print("=== SCHEMAS ===")
for s, n in cur.fetchall():
    print("  ", s, ":", n, "таблиць")

cur.execute("SELECT table_schema, table_name, column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_schema NOT IN ('pg_catalog','information_schema','financial','mci') "
            "ORDER BY table_schema, table_name, ordinal_position")
t = collections.defaultdict(list)
for sch, tn, cn, dt in cur.fetchall():
    t[(sch, tn)].append(cn + ":" + dt)
print("\n=== TABLES (крім financial/mci) ===")
for (sch, tn), cols in t.items():
    print("\n#", sch + "." + tn)
    print("   " + ", ".join(cols))
cm.__exit__(None, None, None)
