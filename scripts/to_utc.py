import json
from dataclasses import dataclass
import sshtunnel
import psycopg
import trio
from datetime import datetime, timezone


@dataclass
class Keys:
    api_key: str
    base_url: str
    ssh_username: str
    ssh_password: str
    pg_user: str
    pg_password: str
    pg_database: str


async def main():
    with open("key.json", "r") as f:
        keys = Keys(**json.load(f))

    with sshtunnel.SSHTunnelForwarder(
        "81.70.133.142",
        ssh_username=keys.ssh_username,
        ssh_password=keys.ssh_password,
        remote_bind_address=("localhost", 5432),
    ) as tunnel:
        assert tunnel is not None, "Failed to start SSH tunnel"
        tunnel.start()
        with (
            psycopg.connect(
                f"host=localhost hostaddr=127.0.0.1 "
                f"dbname={keys.pg_database} "
                f"user={keys.pg_user} "
                f"password={keys.pg_password} "
                f"port={tunnel.local_bind_port}"
            ) as conn,
            conn.cursor() as cur,
        ):
            print(conn.info.timezone)
            cur.execute("SELECT id, submitted_at, evaluated_at, score FROM submissions")
            rows = cur.fetchall()
            for row in rows:
                evaluated_at: datetime | None = row[2]
                if evaluated_at is not None:
                    evaluated_at_utc = evaluated_at.astimezone(tz=timezone.utc)
                    cur.execute(
                        """
                        UPDATE submissions SET evaluated_at = %s
                        WHERE id = %s
                        """,
                        (evaluated_at_utc, row[0]),
                    )
                    print(
                        f"ID: {row[0]}, submitted_at: {row[1]}, "
                        f"evaluated_at: {row[2]} -> {evaluated_at_utc}, score: {row[3]}"
                    )
            conn.commit()


if __name__ == "__main__":
    trio.run(main)
