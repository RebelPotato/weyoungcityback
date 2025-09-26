import json
from dataclasses import dataclass
import sshtunnel
import psycopg
import trio
import argparse
from datetime import datetime


@dataclass
class Keys:
    api_key: str
    base_url: str
    ssh_username: str
    ssh_password: str
    pg_user: str
    pg_password: str
    pg_database: str


@dataclass
class Submission:
    id: int
    user_id: int
    problem_id: str
    code: str
    submitted_at: datetime
    score: int


async def main():
    with open("key.json", "r") as f:
        keys = Keys(**json.load(f))

    parser = argparse.ArgumentParser(
        description="Judge submissions within a time range"
    )
    parser.add_argument(
        "-s",
        "--start",
        required=True,
        help="Start time in ISO format (e.g., 2025-09-25T00:00:00)",
    )
    parser.add_argument(
        "-e", "--end", help="End time in ISO format (e.g., 2025-09-28T23:59:59)"
    )
    args = parser.parse_args()

    start_time = datetime.fromisoformat(args.start).astimezone()
    end_time = (
        datetime.fromisoformat(args.end).astimezone()
        if args.end
        else datetime.now().astimezone()
    )

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
            cur.execute(
                """
                SELECT id, problemID, user_id, code, submitted_at, score FROM submissions
                WHERE submitted_at >= %s AND submitted_at <= %s
                ORDER BY submitted_at""",
                (start_time, end_time),
            )
            submissions = [
                Submission(
                    id=row[0],
                    problem_id=row[1],
                    user_id=row[2],
                    code=row[3],
                    submitted_at=row[4],
                    score=row[5],
                )
                for row in cur.fetchall()
            ]
    print(f"Found {len(submissions)} submissions to judge.")

    # # for each user and each problem, only keep the latest submission and mark the rest as ignored
    # latest = {}
    # for s in submissions:
    #     key = (s.user_id, s.problem_id)
    #     if key not in latest or s.submitted_at > latest[key].submitted_at:
    #         latest[key] = s
    # with sshtunnel.SSHTunnelForwarder(
    #     "81.70.133.142",
    #     ssh_username=keys.ssh_username,
    #     ssh_password=keys.ssh_password,
    #     remote_bind_address=("localhost", 5432),
    # ) as tunnel:
    #     assert tunnel is not None, "Failed to start SSH tunnel"
    #     tunnel.start()
    #     with (
    #         psycopg.connect(
    #             f"host=localhost hostaddr=127.0.0.1 "
    #             f"dbname={keys.pg_database} "
    #             f"user={keys.pg_user} "
    #             f"password={keys.pg_password} "
    #             f"port={tunnel.local_bind_port}"
    #         ) as conn,
    #         conn.cursor() as cur,
    #     ):
    #         for s in submissions:
    #             key = (s.user_id, s.problem_id)
    #             if key in latest and latest[key].id != s.id:
    #                 cur.execute(
    #                     "UPDATE submissions SET eval_status = '已忽略' WHERE id = %s",
    #                     (s.id,),
    #                 )
    #         conn.commit()
    # ignored_count = len(submissions) - len(latest)
    # submissions = list(latest.values())
    # print(
    #     f"Ignored {ignored_count} submissions from the same user, {len(submissions)} submissions left to judge"
    # )

    # save submissions to .scraps/submissions.json
    with open(".scraps/submissions.json", "w") as f:
        json.dump([s.__dict__ for s in submissions], f, default=str)


if __name__ == "__main__":
    trio.run(main)
