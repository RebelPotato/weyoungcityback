import json
from dataclasses import dataclass
import sshtunnel
import psycopg
import trio


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
            cur.execute("SELECT id, eval_status FROM submissions")
            rows = cur.fetchall()
            for row in rows:
                print(f"ID: {row[0]}, Status: {row[1]}")
            cur.execute(
                """
                UPDATE submissions SET eval_status = '未评测'
                WHERE id = 84
                """
            )
            conn.commit()


if __name__ == "__main__":
    trio.run(main)
