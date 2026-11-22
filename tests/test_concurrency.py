import threading

from hakiki import INTACT, Ledger, verify


def test_concurrent_writes_keep_the_chain_intact(keys, log_path):
    ledger = Ledger(log_path, keys[0])

    @ledger.tool
    def work(worker, i):
        return worker * 1000 + i

    def run(worker):
        for i in range(25):
            work(worker, i)

    threads = [threading.Thread(target=run, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = verify(log_path, keys[1])
    assert result.status == INTACT, result.problems
    assert len(result.entries) == 8 * 25 * 2
    assert [e["seq"] for e in result.entries] == list(range(400))
