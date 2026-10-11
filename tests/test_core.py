import sys, pathlib, uuid, pytest
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "windows-agent"))
from clipbridge import protocol as P
from clipbridge.history import History
from clipbridge.security import PairingManager, mac

A, B = str(uuid.uuid4()), str(uuid.uuid4())


def test_item_roundtrip_and_integrity():
    it = P.make_item(A, 1, 1, "hello")
    assert P.validate_item(it, 100)["text"] == "hello"
    it["text"] = "tampered"
    with pytest.raises(P.ProtocolError):
        P.validate_item(it, 100)


def test_size_limit_and_kind():
    with pytest.raises(P.ProtocolError):
        P.validate_item(P.make_item(A, 1, 1, "x" * 50), 10)
    assert P.make_item(A, 1, 1, "https://a.b/c")["kind"] == "url"


def test_ordering_independent_of_clock():
    a, b = P.make_item(A, 1, 5, "a"), P.make_item(B, 1, 5, "b")
    assert (P.order_key(a) > P.order_key(b)) == (A > B)
    assert P.order_key(P.make_item(A, 2, 6, "n")) > P.order_key(b)


def test_history_dedupe_search_prune(tmp_path):
    h = History(tmp_path / "h.db")
    it = P.make_item(A, 1, 1, "needle in haystack")
    assert h.add(it, "local", "local") and not h.add(it, "local", "local")
    assert len(h.search("need")) == 1
    h.delete(it["id"])
    assert h.search("needle") == []


def test_pairing_token_single_use():
    pm = PairingManager()
    t = pm.create()
    assert pm.consume(t) and not pm.consume(t)
    assert not pm.consume("nope")


def test_mac_differs_per_nonce():
    assert mac(b"k" * 32, b"1", A) != mac(b"k" * 32, b"2", A)
