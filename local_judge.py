# judge a problem locally. This is sent to the contestant to judge their answer.
import trio


def it():
    yield None
    return 2


async def main():
    proc = it()
    proc.send(None)  # start the generator
    try:
        await trio.to_thread.run_sync(proc.send, None)
    except RuntimeError as e:
        assert isinstance(e.__cause__, StopIteration)
        print("Stop Iteration catched!", e.__cause__.value)
    except StopIteration as e:
        print("Stop Iteration catched natively!", e.value)


trio.run(main)
